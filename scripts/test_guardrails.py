from retrieval.catalog import get_connection
from guardrails.pipeline import validate_sql

conn = get_connection()

bad_interval = "REASONING: test\nSQL: SELECT o.id FROM orders o WHERE o.created_at >= date_trunc('quarter', CURRENT_DATE - interval '1 quarter')"
good = "REASONING: test\nSQL: SELECT status, COUNT(*) FROM orders GROUP BY status"
fake_col = "REASONING: test\nSQL: SELECT customer_email FROM orders"
delete = "REASONING: test\nSQL: DELETE FROM orders"

for name, raw in [("interval bug", bad_interval), ("good", good), ("fake column", fake_col), ("delete", delete)]:
    r = validate_sql(raw, conn)
    print(f"{name}: passed={r['passed']} failed_at={r['failed_at']} errors={r['errors']}")

conn.close()