from execution.sandbox import execute_query

def T(label, sql):
    r = execute_query("REASONING: t\nSQL: " + sql)
    if r["executed"]:
        print(f"{label:20s} EXECUTED rows={r['row_count']} truncated={r['truncated']} cols={r['columns']} {r['elapsed_ms']}ms")
    else:
        print(f"{label:20s} BLOCKED  at={r['failed_at']:9s} {r['errors'][0][:80]}")

T("group by", "SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY n DESC")
T("join revenue", "SELECT r.name, SUM(oi.amount) AS revenue FROM regions r JOIN orders o ON r.id=o.region_id JOIN order_items oi ON o.id=oi.order_id GROUP BY r.name ORDER BY revenue DESC")
T("no LIMIT", "SELECT * FROM orders")
T("interval bug", "SELECT id FROM orders WHERE created_at >= date_trunc('quarter', CURRENT_DATE - interval '1 quarter')")
T("delete", "DELETE FROM orders")
T("set_config", "SELECT set_config('statement_timeout','0',false)")
T("embeddings table", "SELECT * FROM schema_embeddings")
T("slow cross join", "SELECT COUNT(*) FROM order_items a, order_items b, order_items c, order_items d")