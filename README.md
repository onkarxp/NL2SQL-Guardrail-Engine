# SafeQuery — Guardrailed NL2SQL Engine

A production-oriented **Text-to-SQL system** that translates natural language questions into SQL, validated through a seven-layer guardrail pipeline, executed in a sandboxed read-only environment, and checked for hallucinations and semantic ambiguity before an answer ever reaches a user. Built to answer the real question in enterprise NL2SQL: not "can an LLM write SQL?" (it can), but "can you trust it enough to point it at a real database?"

Every layer in this project exists because something concrete broke without it, not because of upfront guesswork. That distinction — and the real bugs that drove each addition — is documented throughout this README.

---

## Why this project exists

LLMs are already good at writing SQL. The hard, unsolved part is everything around that: making sure the query references real tables and columns, never mutates data, can't be used to probe or disable the database it's running on, doesn't blow up a system with an unbounded scan, and — critically — that the final answer shown to a user is actually grounded in the query result rather than a confident-sounding hallucination, structural or semantic.

SafeQuery is built around that problem. It treats the LLM as a capable but untrusted collaborator, and wraps it in retrieval, multi-layer validation, sandboxed execution, and confidence checking so it's safe to point at a real database.

---

## Architecture

```
Natural language question
        │
        ▼
  Schema retrieval          RAG over table/column embeddings, built from the
                             live database catalog, not hand-maintained docs
        │
        ▼
  SQL generation             Claude (Haiku by default), chain-of-thought
                             reasoning before the query, structured output
        │
        ▼
  Guardrail validation       Seven layers, runs in order, stops at first failure:
    1. Syntax parsing         sqlglot parses the query; rejects anything malformed
                               or more than one statement
    2. Data source check      rejects any query with no FROM clause — catches a
                               model disguising a plain-text refusal as fake data
    3. Vacuous filter check    rejects a WHERE clause that references no real
                               columns (WHERE FALSE, WHERE 1=0) — catches a model
                               faking an "empty result" instead of refusing cleanly
    4. Operation allowlist     SELECT only, checked on the parsed tree, not text;
                               walks every node so a write hidden in a subquery
                               is also caught
    5. Function allowlist      rejects any function sqlglot doesn't recognize as
                               standard SQL — catches pg_sleep, set_config,
                               pg_read_file, dblink
    6. Schema existence check  tables/columns checked against the live catalog;
                               correctly skips CTE and derived-subquery aliases
    7. EXPLAIN validation      Postgres itself plans the query without running
                               it — backstop for anything the first six miss
        │
        ▼
  Retry loop                 On failure, the specific error and which layer
                             caught it is sent back to the model as a new
                             message; up to 3 attempts total
        │
        ▼
  Sandboxed execution         Dedicated read-only Postgres role, SELECT-only on
                              named tables, 5s statement timeout, row limit
                              injected into the parse tree, fresh connection
                              per query
        │
        ▼
  Result-level checks         Three independent mechanisms, each catching a
    (Step 6)                  different failure none of the above can see:
    - Plausibility checks       empty results, all-NULL columns
    - Grounded final answer     every number in the generated summary is
                                 checked against the real result; ungrounded
                                 numbers are named explicitly
    - Self-consistency check    same question run multiple times; flags both
                                 numeric disagreement and structural instability
                                 (different SQL shapes) even when the numbers
                                 happen to agree
        │
        ▼
  Answer returned to user
```

Each stage is a discrete, independently-testable unit, built and verified with real attacks and real ambiguous questions against a real Postgres database, not assumed to work from design alone.

---

## Guardrail design philosophy: defense in depth, found through testing

No layer in this project shipped because it was planned upfront and never revisited. Every layer beyond the original three (syntax, allowlist, schema) exists because a specific, real failure got through the layers that came before it:

| Found | Gap | Fix |
|---|---|---|
| Generated query used `interval '1 quarter'`, an invalid Postgres unit | `sqlglot` parsed it fine and silently normalized it — a parser knows SQL grammar in general, not what one specific database accepts | Added EXPLAIN validation, asking Postgres itself before anything runs |
| `SELECT pg_sleep(10)` / `SELECT set_config(...)` passed every check | Syntax, allowlist, and schema checks only look at statement type and table/column names — a function call has neither | Added a function allowlist, exploiting the same distinction `sqlglot` already draws between recognized and unrecognized functions |
| A validated query could disable its own session timeout | Guardrails are application code; a database role enforces limits independently of it | Added a dedicated read-only role with a database-enforced timeout, plus a fresh connection per query |
| Valid CTE and subquery queries were rejected with "unknown table/alias" | The schema checker correctly skipped CTEs as tables but never added them as known aliases either — a false positive, not a missed hallucination | Fixed by treating CTE/subquery columns as trusted rather than checked, with EXPLAIN as the backstop for genuinely fake columns inside them |
| A refusal was disguised as a real one-row result (`SELECT 'cannot compute...' AS error`) | A query referencing no real table or column has nothing for the schema checker to flag | Added a check rejecting any query with no `FROM` clause |
| The same evasion reappeared as `SELECT id, name, NULL AS profit_margin FROM products WHERE FALSE` | A `NULL`-literal alias isn't a real column reference, so the schema checker still had nothing to flag | Added a check rejecting any `WHERE` clause containing no real column references — a condition built entirely of literals can't be a genuine data filter |

---

## Key features

- **RAG-based schema retrieval** — only the most relevant tables are retrieved per question instead of dumping the full schema into every prompt, reducing both token cost and hallucination surface area; tuned using real retrieval failures, not assumed correct
- **Seven-layer guardrail pipeline** — every layer validates the parsed SQL tree, not raw text, so comments, casing tricks, and functions hidden in subqueries can't bypass it
- **Sandboxed execution** — a dedicated, least-privilege Postgres role (not just application-level checks) enforces read-only access, a query timeout, and row limits independently of the guardrail code
- **Retry loop** — a validation failure is turned into a second attempt by sending the specific error back to the model, rather than simply rejecting and stopping
- **Hallucination and ambiguity detection** — plausibility checks on raw results, independently-verified grounded final answers, and self-consistency checking that measures both numeric agreement and structural stability across repeated runs
- **Upload validation (prototyped)** — the same parse-tree-allowlisting technique used to validate generated SQL, applied to a user's own uploaded schema-and-data file: only `CREATE TABLE` and `INSERT` are permitted, and every `INSERT` is checked to ensure it only touches tables created by that same file, blocking data exfiltration via `INSERT ... SELECT` from existing tables

---

## Real findings from building this (not hypothetical test cases)

- **Structural hallucination** is caught at two points: the schema checker (tables/columns that don't exist) and EXPLAIN (anything hidden inside a CTE the schema checker deliberately doesn't inspect)
- **"Average order value" is genuinely ambiguous** — two independent runs produced valid SQL averaging per line item vs. averaging per order, with results differing by roughly 2.5x; neither query was "wrong"
- **"Last quarter" is genuinely ambiguous** in a different way — a rolling 90-day window vs. the previous full calendar quarter, confirmed with two independently different real queries
- **Numeric agreement does not imply structural stability** — running one ambiguous question through a 5-run consistency check returned 100% numeric agreement alongside five completely different generated SQL queries; a 2-run check on the same question would not have revealed this
- **A rigid output format can be gamed honestly** — forced to respond in `REASONING: / SQL:` format, the model twice found syntactically valid ways to express "I can't answer this" that looked identical to a real result at the data-structure level, rather than refusing cleanly; both were closed with new guardrail layers, not prompt pleading alone

---

## Tech stack

| Layer | Tools |
|---|---|
| Database | Postgres 16 (Docker), `pgvector` extension |
| SQL parsing / validation | [`sqlglot`](https://github.com/tobymao/sqlglot) |
| Schema embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), local and free, stored in `pgvector` |
| LLM generation | Claude Haiku via the Anthropic API |
| Execution sandbox | Dedicated read-only Postgres role, scoped grants, statement timeout |
| Evaluation | In progress — see Roadmap |

---

## Project structure

```
safequery/
├── data/
│   ├── schema.sql        # pgvector extension, tables, schema_embeddings
│   ├── seed.sql           # generated fake data (Faker, reproducible seed)
│   └── roles.sql           # the safequery_reader least-privilege role
├── retrieval/
│   ├── catalog.py          # live schema introspection via information_schema
│   ├── config.py            # categorical-column config, table hints
│   ├── index.py              # builds and stores table-description embeddings
│   └── retrieve.py            # question → relevant tables (vector search)
├── generation/
│   ├── generate.py          # prompt building, the Claude call
│   ├── retry.py               # the retry loop
│   └── answer.py                # grounded final-answer generation + verification
├── guardrails/
│   ├── extract.py            # pulls SQL out of the model's structured reply
│   ├── validators.py          # all seven validation layers
│   └── pipeline.py              # runs the layers in order, stops at first failure
├── execution/
│   ├── sandbox.py             # the only path that actually runs validated SQL
│   ├── plausibility.py          # result-level sanity checks
│   └── consistency.py             # 2-run and N-run self-consistency checking
├── ask.py                   # primary entry point: question → answer
├── ask_with_answer.py        # adds plausibility notes + a grounded summary
├── check.py                    # entry point for deliberate consistency checking
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## How it works — a traced example

**Question:** *"What was the revenue by region last quarter?"*

1. **Retrieval** embeds the question and pulls the closest-matching tables from `schema_embeddings` — `orders`, `order_items`, `regions`
2. **Generation** produces reasoning, then SQL:
   ```sql
   SELECT r.name, SUM(oi.amount) AS revenue
   FROM orders o
   JOIN order_items oi ON o.id = oi.order_id
   JOIN regions r ON o.region_id = r.id
   WHERE o.created_at >= DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '3 months')
     AND o.created_at < DATE_TRUNC('quarter', CURRENT_DATE)
   GROUP BY r.id, r.name
   ORDER BY revenue DESC
   ```
3. **Guardrails** confirm every table/column is real, the statement is SELECT-only, every function used is recognized, the WHERE clause genuinely filters on real data, and Postgres itself accepts the plan
4. **Execution** runs it as the read-only `safequery_reader` role, with a row limit applied and a 5-second timeout in force
5. **Result checks** confirm the result isn't empty or full of NULLs, and that the generated summary sentence only cites numbers actually present in it
6. **Answer**: *"Last quarter, the North region generated the highest revenue, followed by West, East, and South."* — every figure traceable back to the actual query result

---

## Roadmap

- [ ] Step 7: formal evaluation set (30–50 questions, including the ambiguous and adversarial ones already found), measuring accuracy, which guardrail layer catches what, and retry success rate
- [ ] Full integration of schema-and-data upload (currently prototyped and tested, not yet wired into the live pipeline)
- [ ] Cost-based rejection using EXPLAIN's estimated query cost, not just row limits and timeouts
- [ ] A simple web interface (Streamlit) over the existing `ask_with_answer()` function
- [ ] Row-level / tenant filtering — not built; the current schema is single-tenant, so it isn't applicable, but the design (injecting a tenant filter the same way row limits are injected, or Postgres Row-Level Security policies) is documented as a known extension point

---

## Evaluation

Formal evaluation (Step 7) is in progress. In the meantime, the system has been tested against:
- A set of deliberately adversarial questions (asking for data that doesn't exist, prompting evasive non-answers) — all currently caught by the guardrail layers listed above
- Repeated runs of known-ambiguous questions, using the consistency-checking tools in `check.py`, measuring both numeric agreement and structural (SQL-shape) stability
- Manual verification of generated SQL against independently-computed expected answers from the seed data

Planned formal metrics:
- **Execution accuracy** — does the query return the same result as a correct reference query?
- **Guardrail effectiveness** — which layer catches what share of invalid or unsafe queries
- **Retry success rate** — how often a validation failure is corrected within the 3-attempt budget
- **Consistency rate** — agreement rate and structural-diversity rate across repeated runs of known-ambiguous questions

---

## License

2026 Onkar Pathak
