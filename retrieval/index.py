from sentence_transformers import SentenceTransformer
from retrieval.catalog import get_connection, get_schema_catalog, get_foreign_keys, get_sample_values
from retrieval.config import CATEGORICAL_COLUMNS,TABLE_HINTS

model = SentenceTransformer("all-MiniLM-L6-v2")

def build_table_description(table, columns, foreign_keys, sample_values_by_col,hint=None):
    col_lines = []
    for c in columns:
        line = f"- {c['column']} ({c['type']})"
        if c['column'] in sample_values_by_col:
            line += f" — sample values: {sample_values_by_col[c['column']]}"
        col_lines.append(line)

    fk_lines = [f"- {t}.{col} references {ft}.{fc}"
                for (t, col, ft, fc) in foreign_keys if t == table]

    text = f"Table: {table}\nColumns:\n" + "\n".join(col_lines)
    if fk_lines:
        text += "\nRelationships:\n" + "\n".join(fk_lines)
    if hint:
        text += f"\nDescription: {hint}"
    return text

def build_and_store_embeddings():
    conn = get_connection()
    catalog = get_schema_catalog(conn)
    foreign_keys = get_foreign_keys(conn)

    cur = conn.cursor()
    for table, columns in catalog.items():
        sample_values_by_col = {}
        for col in CATEGORICAL_COLUMNS.get(table, []):
            sample_values_by_col[col] = get_sample_values(conn, table, col)

        description = build_table_description(table, columns, foreign_keys, sample_values_by_col, hint = TABLE_HINTS.get(table))
        embedding = model.encode(description).tolist()

        cur.execute("""
            INSERT INTO schema_embeddings (table_name, description, embedding)
            VALUES (%s, %s, %s)
            ON CONFLICT (table_name) DO UPDATE
            SET description = EXCLUDED.description,
                embedding = EXCLUDED.embedding;
        """, (table, description, embedding))

        print(f"Indexed: {table}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    build_and_store_embeddings()