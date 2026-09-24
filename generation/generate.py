import os
from dotenv import load_dotenv
from anthropic import Anthropic
from retrieval.retrieve import retrieve_relevant_tables

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a SQL generation assistant for a Postgres database.
You will be given a natural language question and relevant table schemas.

Rules:
- Only use tables and columns that are explicitly listed in the provided schema context.
- Never invent table or column names.
- Only generate SELECT statements — never INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use explicit JOINs based on the relationships listed in the schema context.
- If the question cannot be answered using the given schema, say so instead of guessing.

Respond in this exact format:
REASONING: <one or two sentences on your approach>
SQL: <the SQL query, nothing else after this>
"""

def build_prompt(question: str, retrieved_tables):
    schema_context = "\n\n".join([desc for (_, desc, _) in retrieved_tables])
    return f"""Schema context:
{schema_context}

Question: {question}
"""

def generate_sql(question: str, top_k=4):
    retrieved_tables = retrieve_relevant_tables(question, top_k=top_k)
    prompt = build_prompt(question, retrieved_tables)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

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