# NL2SQL Guardrail Engine

# SafeQuery — Guardrailed NL2SQL Engine

A production-oriented **Text-to-SQL system** that translates natural language questions into SQL, validated through a multi-layer guardrail pipeline and checked for hallucinations before results ever reach a user. Built to answer the real question in enterprise NL2SQL: not "can an LLM write SQL?" (it can), but "can you trust it enough to point it at a real database?"

---

## Why this project exists

LLMs are already good at writing SQL. The hard, unsolved part is everything around that: making sure the query references real tables and columns, never mutates data, respects tenant boundaries, doesn't blow up your database with an unbounded scan, and — critically — that the final answer shown to the user is actually grounded in the query result rather than a confident-sounding hallucination.

SafeQuery is built around that problem. It assumes the LLM is a capable but untrusted intern, and wraps it in retrieval, validation, sandboxing, and confidence scoring so it's safe to put in front of real users and a real database.

---

## Architecture

```
Natural language question
        |
        v
  Schema retrieval  (RAG over table/column embeddings + sample values)
        |
        v
  SQL generation    (LLM, chain-of-thought, dialect-aware)
        |
        v
  Guardrail validation
    - SQL syntax parsing
    - Schema existence check (catches hallucinated tables/columns)
    - Operation allowlist (SELECT-only, blocks DML/DDL)
    - Row-level security / tenant filter injection
    - Cost & row limit enforcement
        |
        v
  Sandboxed execution (read-only replica, scoped DB role, query timeout)
        |
        v
  Result & hallucination check (plausibility checks, self-consistency, confidence scoring)
        |
        v
  Answer returned to user (grounded strictly in real query results)
```

Each stage is a discrete, testable unit — this makes the system easy to eval, easy to extend, and easy to reason about when something goes wrong.

---

## Key features

- **RAG-based schema retrieval** — only relevant tables/columns are retrieved per question instead of dumping the full schema into the prompt, reducing both token cost and hallucination surface area
- **Guardrail pipeline** — SQL parsing, schema validation, operation allowlisting, and row-level security enforced *before* any query touches the database
- **Sandboxed execution** — queries run against a read-only replica with a minimal-permission role, enforced row limits, and query timeouts
- **Hallucination detection** — plausibility checks on results, self-consistency checks across generations, and a combined confidence score; low-confidence answers are flagged instead of shown as fact
- **Grounded answer generation** — the final natural-language answer is constrained to reference only numbers actually present in the query result

---

## Tech stack

| Layer | Tools |
|---|---|
| SQL parsing / validation | [`sqlglot`](https://github.com/tobymao/sqlglot) |
| Schema embeddings | pgvector / Chroma |
| LLM generation | Claude / GPT-4 / open-source LLM via API |
| Execution sandbox | Read-only Postgres replica, scoped DB role |
| Evaluation | [Spider](https://yale-lily.github.io/spider) / [BIRD](https://bird-bench.github.io/) benchmarks + domain-specific eval set |

---

## Project structure

```
safequery/
├── retrieval/          # Schema cataloging, embedding index, retrieval function
│   ├── catalog.py
│   ├── index.py
│   └── retrieve.py
├── generation/          # Prompt templates, SQL generation, answer grounding
│   ├── prompts.py
│   ├── generate.py
│   └── answer.py
├── guardrails/          # Validation pipeline, safety checks
│   ├── parser.py
│   ├── validators.py
│   └── rls.py
├── execution/           # Sandbox connection, timeout/limit enforcement
│   └── sandbox.py
├── eval/                # Eval harness, benchmark + custom test sets
│   └── run_eval.py
└── README.md
```

---

## How it works — example

**Question:** *"What was our revenue by region last quarter?"*

1. **Retrieval** pulls the `orders`, `regions`, and `order_items` tables (not the other 200+ tables in the schema), along with sample values for `region.name` and the date range for "last quarter"
2. **Generation** produces:
   ```sql
   SELECT r.name AS region, SUM(oi.amount) AS revenue
   FROM orders o
   JOIN order_items oi ON oi.order_id = o.id
   JOIN regions r ON r.id = o.region_id
   WHERE o.created_at >= '2026-04-01' AND o.created_at < '2026-07-01'
   GROUP BY r.name;
   ```
3. **Guardrails** confirm all tables/columns exist, the query is `SELECT`-only, injects the tenant filter, and adds a `LIMIT` as a safety net
4. **Execution** runs against the read-only replica
5. **Hallucination check** confirms the result is plausible and the query matches the stated intent
6. **Answer**: *"Revenue by region last quarter: North $482K, South $391K, East $276K, West $198K."* — every number pulled directly from the result set

---

## Roadmap

- [ ] Fine-tune a smaller open-source model (LoRA) on domain-specific schema and query style
- [ ] Add a lightweight classifier as a secondary "is this SQL safe?" guardrail layer
- [ ] Expand eval harness with production log-derived edge cases
- [ ] Multi-dialect support (Postgres, Snowflake, BigQuery)

---

## Evaluation

Correctness is measured against:
- **Execution accuracy** — does the query return the same result as a human-written reference query?
- **Exact/logical match** — using Spider/BIRD-style evaluation methodology
- **Guardrail effectiveness** — % of hallucinated/unsafe queries caught before execution
- **Hallucination rate on final answers** — % of natural-language answers containing numbers not present in the query result

---

## License

MIT