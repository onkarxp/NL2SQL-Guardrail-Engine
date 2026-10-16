# SafeQuery — Guardrailed NL2SQL Engine

A production-oriented **Text-to-SQL system** that translates natural language questions into SQL, validated through an eight-layer guardrail pipeline with an explicit refusal path, executed in a sandboxed read-only environment, and checked for hallucinations and semantic ambiguity before an answer ever reaches a user. Built to answer the real question in enterprise NL2SQL: not "can an LLM write SQL?" (it can), but "can you trust it enough to point it at a real database?"

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
  Guardrail validation       Eight layers plus an explicit refusal path, runs in order, stops at first failure:
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
    8. Empty-limit check       rejects LIMIT 0 — a query that can never return a
                               row is a disguised refusal
  Explicit refusal path       the model answers `SQL: CANNOT_ANSWER - <reason>` for
                               write requests or missing data; the pipeline stops
                               immediately instead of retrying
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
    - Self-consistency check    same question run multiple times; runs are
                                 clustered by numeric answer. If they disagree the
                                 response is flagged low-confidence and every
                                 distinct answer is listed with its SQL. Triggered
                                 automatically by ambiguity-prone wording
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
- **Eight-layer guardrail pipeline plus an explicit refusal path** — every layer validates the parsed SQL tree, not raw text, so comments, casing tricks, and functions hidden in subqueries can't bypass it
- **Sandboxed execution** — a dedicated, least-privilege Postgres role (not just application-level checks) enforces read-only access, a query timeout, and row limits independently of the guardrail code
- **Retry loop** — a validation failure is turned into a second attempt by sending the specific error back to the model, rather than simply rejecting and stopping
- **Hallucination and ambiguity detection** — plausibility checks on raw results, independently-verified grounded final answers, and self-consistency checking that clusters repeated runs by answer, flags low confidence and lists every distinct answer found
- **Explicit refusal** — the model can decline (`CANNOT_ANSWER`) instead of disguising a refusal as SQL; refusals stop the retry loop immediately
- **Evaluation harness** — graded on result equivalence against reference queries, each case repeated, plus a separate model-free test of the validators
- **Upload validation (prototyped)** — the same parse-tree-allowlisting technique used to validate generated SQL, applied to a user's own uploaded schema-and-data file: only `CREATE TABLE` and `INSERT` are permitted, and every `INSERT` is checked to ensure it only touches tables created by that same file, blocking data exfiltration via `INSERT ... SELECT` from existing tables

---

## Real findings from building this (not hypothetical test cases)

- **Structural hallucination** is caught at two points: the schema checker (tables/columns that don't exist) and EXPLAIN (anything hidden inside a CTE the schema checker deliberately doesn't inspect)
- **"Average order value" is genuinely ambiguous** — two independent runs produced valid SQL averaging per line item vs. averaging per order, with results differing by roughly 2.5x; neither query was "wrong"
- **"Last quarter" is genuinely ambiguous** in a different way — a rolling 90-day window vs. the previous full calendar quarter, confirmed with two independently different real queries
- **Numeric agreement does not imply structural stability** — running one ambiguous question through a 5-run consistency check returned 100% numeric agreement alongside five completely different generated SQL queries; a 2-run check on the same question would not have revealed this
- **Consistency checks must be tested on real result shapes** — scalar aggregates (`AVG`) were initially not comparable at all, and the first fix produced a false "disagreement" because the model aliased the same column differently across runs; both only appeared on the live database
- **Sampling can't prove completeness** — with 3 runs, an interpretation that appears 20% of the time is missed about half the time; the system reports "readings seen in these runs", not "all readings"
- **The evaluation harness exposed an unstable behavior hand-testing missed** — blocked requests sometimes returned a disguised refusal (`... 'Cost data not available' AS profit_margin ... LIMIT 0`) that passed every guardrail. Root cause: the model had no valid way to refuse. Adding an explicit `CANNOT_ANSWER` path took blocked cases from unstable (3 attempts each) to 4/4 refused in 1 attempt, with no change on answerable questions
- **An end-to-end eval can overstate the guardrails** — in 138 evaluated runs the model refused every unsafe request itself, so no validator ever rejected anything; a separate model-free eval of the validators was needed to measure them (29/29 dangerous blocked, 11/11 valid allowed)
- **Wording can collide with column values** — "How many orders have been placed?" produced `WHERE status = 'placed'`, a legitimate reading since `'placed'` is a real status; the case was reclassified as ambiguous rather than counted as a model error
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
| Evaluation | Custom harness: end-to-end (46 cases × 3 runs) and guardrails-only (40 hand-written cases), see Evaluation |

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
│   ├── validators.py          # all eight validation layers
│   └── pipeline.py              # runs the layers in order, stops at first failure
├── execution/
│   ├── sandbox.py             # the only path that actually runs validated SQL
│   ├── plausibility.py          # result-level sanity checks
│   └── consistency.py             # 2-run and N-run self-consistency checking
├── evaluation/
│   ├── cases.py            # eval questions + reference queries
│   ├── run_eval.py         # end-to-end eval: model + guardrails, graded against reference queries
│   └── guardrail_eval.py   # guardrails only: hand-written dangerous/valid SQL, no LLM
├── ask.py                   # question → validated, executed SQL result
├── respond.py                # primary entry point: ask + plausibility + grounded
│                              # answer + auto consistency check + low-confidence flag
├── check.py                    # manual consistency checking
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

## Usage

```bash
docker compose up -d                     # Postgres 16 + pgvector
python -m retrieval.index                # build schema embeddings (once, or after schema changes)
python -m respond "What is the total revenue by region?"
python -m evaluation.run_eval            # end-to-end evaluation (calls the LLM, a few rupees)
python -m evaluation.guardrail_eval      # validators only, no LLM, free
```

Requires an Anthropic API key (workspace-scoped) in the environment.

---

## Roadmap

- [x] Step 7: evaluation harness, refusal path, guardrail-only evaluation (final rerun numbers pending, see Evaluation)
- [ ] A simple web interface (Streamlit) over the existing `respond()` function
- [ ] Full integration of schema-and-data upload (currently prototyped and tested, not yet wired into the live pipeline)
- [ ] Cost-based rejection using EXPLAIN's estimated query cost, not just row limits and timeouts
- [ ] Optional: reject `SELECT ... INTO` explicitly (currently blocked incidentally by the schema check and by the database role's lack of `CREATE`)
- [ ] Optional: Haiku vs Sonnet comparison on the evaluation set
- [ ] Row-level / tenant filtering — not built; the current schema is single-tenant, so it isn't applicable, but the design (injecting a tenant filter the same way row limits are injected, or Postgres Row-Level Security policies) is documented as a known extension point

---

## Evaluation

Two separate evaluations, because they measure different things.

**1. End-to-end (`evaluation/run_eval.py`)** — 46 questions, each run 3 times, graded by comparing the generated query's *result* to a hand-written reference query (not by comparing SQL text): 28 answerable, 12 unsafe or unanswerable, 6 genuinely ambiguous (recorded, not graded).

| Metric (first full run, 138 runs) | Result |
|---|---|
| Execution accuracy (28 answerable × 3) | 77 / 84 before grader corrections |
| Answered on the first attempt | 84 / 84 |
| Unsafe or unanswerable requests returning no result | 36 / 36, all cleanly refused in one attempt |
| Tables unchanged after the run | True |

All 7 misses were diagnosed: 3 runs (one question, "customers with more than 3 orders") were a **genuine, consistent model error** (nested aggregation: it returned one row per qualifying customer instead of counting them); 4 runs were a grader limit (year returned as a date instead of a number) or an ambiguous schema (two valid region links), now handled with alternate accepted reference queries. A rerun with those corrections is pending, so the corrected accuracy is not reported here.

**2. Guardrails only (`evaluation/guardrail_eval.py`)** — no LLM. 40 hand-written SQL strings go straight into the validators: **29/29 dangerous inputs blocked, 11/11 valid queries allowed, 0 fail-open, 0 false positives**, and every layer caught at least one case. The valid queries (CTEs, subqueries, window functions, comments) are false-positive controls.

Why two: in the end-to-end run the model refused every unsafe request itself, so no validator ever had to reject anything. The first evaluation therefore measures the prompt and model; only the second measures the guardrails.

**Known limitations of this evaluation**
- The guardrail suite is a regression suite written by the author, several cases being the exact attacks the layers were built for. It is not an independent red team.
- Consistency checking is sampling-based: 3 runs can miss an interpretation that appears 20% of the time about half the time, and a consistent bias looks like agreement (e.g. "orders placed" was never flagged, all runs chose the same reading).
- Undefined terms ("best customers", "conversion rate") are refused rather than flagged; refusal and low-confidence are separate behaviors.
- Single model (Haiku); no Sonnet comparison yet.

---

## License

Copyright (c) 2026 Onkar Pathak
