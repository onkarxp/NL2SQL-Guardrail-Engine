from sentence_transformers import SentenceTransformer
from retrieval.catalog import get_connection

model = SentenceTransformer("all-MiniLM-L6-v2")

def retrieve_relevant_tables(question: str, top_k=4):
    embedding = model.encode(question).tolist()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, description, embedding <-> %s::vector AS distance
        FROM schema_embeddings
        ORDER BY distance ASC
        LIMIT %s;
    """, (embedding, top_k))
    results = cur.fetchall()
    conn.close()

    return results

if __name__ == "__main__":
    test_questions = [
        "What was the revenue by region last quarter?",
        "What products are in the Electronics category?",
        "How many customers signed up in the last 6 months?",
        "List all cancelled orders",
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        results = retrieve_relevant_tables(question)
        for table, desc, distance in results:
            print(f"  [{distance:.4f}] {table}")
            
## Just adding a comment for git
