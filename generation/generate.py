import os

import time #to check latency and all
from dotenv import load_dotenv
from anthropic import Anthropic
from retrieval.retrieve import retrieve_relevant_tables

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
USAGE_LOG = []   # one entry per model call: tokens in/out and seconds taken

def _record(response, t0):
    USAGE_LOG.append({
        "in": response.usage.input_tokens,
        "out": response.usage.output_tokens,
        "sec": time.perf_counter() - t0,
    })
    
SYSTEM_PROMPT = """You are a SQL generation assistant for a Postgres database.
You will be given a natural language question and relevant table schemas.

Rules:
- Only use tables and columns that are explicitly listed in the provided schema context.
- Never invent table or column names.
- Only generate SELECT statements — never INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use explicit JOINs based on the relationships listed in the schema context.
- If the question asks to modify data, or needs data that does not exist in the
  provided schema, do NOT write a placeholder query. Respond with exactly:
  SQL: CANNOT_ANSWER - <one-sentence reason>
  Never use LIMIT 0, WHERE FALSE, or a text literal as a stand-in for an answer.
- When a metric could be computed at more than one level of aggregation
  (for example, averaging per line item vs. averaging per order), state
  which level you are using in REASONING, and prefer aggregating at the
  level implied by the noun in the question ("order value" implies
  per-order totals, not per-line-item amounts).
- For "last quarter" or "last month", use the previous full calendar period
  (for example DATE_TRUNC), not a rolling window, and say so in REASONING.
- Postgres has no 'quarter' interval unit. For "last quarter" use
  DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '3 months') as the start and
  DATE_TRUNC('quarter', CURRENT_DATE) as the end. Never write INTERVAL '1 quarter'.

Respond in this exact format:
REASONING: <one or two sentences on your approach>
SQL: <the SQL query, nothing else after this>
"""
def ask_claude(messages):
    t0 = time.perf_counter()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    _record(response, t0)
    return response.content[0].text

def build_prompt(question: str, retrieved_tables):
    schema_context = "\n\n".join([desc for (_, desc, _) in retrieved_tables])
    return f"""Schema context:
{schema_context}

Question: {question}
"""

def generate_sql(question: str, top_k=4):
    retrieved_tables = retrieve_relevant_tables(question, top_k=top_k)
    prompt = build_prompt(question, retrieved_tables)

    t0 = time.perf_counter()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    _record(response, t0)

    raw_output = response.content[0].text
    return {
        "question": question,
        "retrieved_tables": [t[0] for t in retrieved_tables],
        "raw_output": raw_output
    }

if __name__ == "__main__":
    test_questions = [
        "What was the revenue by region last quarter?",
        "List all cancelled orders",
        "What products are in the Electronics category?",
    ]

    for q in test_questions:
        result = generate_sql(q)
        print(f"\n{'='*60}")
        print(f"Question: {result['question']}")
        print(f"Retrieved tables: {result['retrieved_tables']}")
        print(f"\n{result['raw_output']}")