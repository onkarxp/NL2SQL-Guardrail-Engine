import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

## gives a connection object which connects python with postgres
def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        user="safequery",
        password="safequery_dev",
        dbname="safequery_db"
    )

## We take a cursor object from the connection 
# object and then execute queries using that cursor object. 
# The cursor object is used to interact with the database and execute SQL commands.
def get_schema_catalog(conn): # used as a description to give to the LLM
    
    # Returns {table_name: [{column, type}, ...]} for all tables in public schema.
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name != 'schema_embeddings'
        ORDER BY table_name, ordinal_position;
    """)
    rows = cur.fetchall()

    ## Creating a dictionary to store the schema catalog, where each table name is a key and its value is a list of dictionaries containing column names and their data types.
    catalog = {}
    for table, column, dtype in rows:
        ## Set default is used for creating a new key in the catalog dictionary if it doesn't already exist.
        ## while its value is a tuple containing the column name and its data type.
        catalog.setdefault(table, []).append({"column": column, "type": dtype})
    return catalog


## For every foreign key in my database, tell me on which table/column it is defined on and which table/column it points to
def get_foreign_keys(conn):
    # Returns list of (table, column, references_table, references_column)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            tc.table_name, kcu.column_name,
            ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY';
    """)
    return cur.fetchall()

def get_sample_values(conn, table, column, limit=10):
    """Pulls distinct sample values for a column — use only on low-cardinality columns."""
    cur = conn.cursor()
    cur.execute(f'SELECT DISTINCT "{column}" FROM "{table}" LIMIT {limit};')
    return [r[0] for r in cur.fetchall()]

if __name__ == "__main__":
    conn = get_connection()
    catalog = get_schema_catalog(conn)
    for table, cols in catalog.items():
        print(f"\n{table}:")
        for c in cols:
            print(f"  - {c['column']} ({c['type']})")

    print("\nForeign keys:")
    for fk in get_foreign_keys(conn):
        print(f"  {fk[0]}.{fk[1]} -> {fk[2]}.{fk[3]}")

    conn.close()
    
