import time
import psycopg2
import sqlglot
from guardrails.pipeline import validate_sql

MAX_ROWS = 100

def get_reader_connection():
    return psycopg2.connect(
        host="localhost", port=5432,
        user="safequery_reader", password="reader_dev", dbname="safequery_db",
    )

def apply_row_limit(tree, max_rows):
    limit = tree.args.get("limit")
    if limit is not None:
        try:
            if int(limit.expression.name) <= max_rows:
                return tree
        except (ValueError, AttributeError):
            pass
    return tree.limit(max_rows, copy=True)

def execute_query(raw_output: str, max_rows: int = MAX_ROWS):
    conn = get_reader_connection()
    try:
        verdict = validate_sql(raw_output, conn)
        if not verdict["passed"]:
            return {"executed": False, **verdict}

        tree = sqlglot.parse_one(verdict["sql"], read="postgres")
        final_sql = apply_row_limit(tree, max_rows + 1).sql(dialect="postgres")

        cur = conn.cursor()
        start = time.time()
        try:
            cur.execute(final_sql)
            rows = cur.fetchall()
        except psycopg2.errors.QueryCanceled:
            conn.rollback()
            return {"executed": False, "passed": True, "sql": final_sql,
                    "failed_at": "timeout",
                    "errors": ["Query exceeded the time limit and was cancelled"]}
        except psycopg2.Error as e:
            conn.rollback()
            return {"executed": False, "passed": True, "sql": final_sql,
                    "failed_at": "execution", "errors": [str(e).splitlines()[0]]}

        truncated = len(rows) > max_rows
        return {
            "executed": True, "passed": True, "sql": final_sql, "failed_at": None,
            "errors": [], "columns": [d[0] for d in cur.description],
            "rows": rows[:max_rows], "row_count": min(len(rows), max_rows),
            "truncated": truncated, "elapsed_ms": round((time.time() - start) * 1000),
        }
    finally:
        conn.close()