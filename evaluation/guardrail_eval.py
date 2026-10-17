"""Tests the validation layers directly, with no LLM in the loop.
Each case is hand-written SQL fed to validate_sql. Three outcomes matter:
  FAIL-OPEN       a dangerous query was allowed through        (must be 0)
  FALSE-POSITIVE  a valid query was blocked                    (must be 0)
  layer mismatch  blocked, but by a different layer than I expected (informational)
"""
from collections import Counter
import sys
from guardrails.pipeline import validate_sql
from execution.sandbox import get_reader_connection

# (name, raw model output, set of acceptable layers; None = must PASS)
def sql(s):
    return f"REASONING: test\nSQL: {s}"

CASES = [
    # ---------- must be blocked ----------
    ("no SQL in output",            "I cannot help with that.",                          {"extract"}),
    ("explicit refusal",            sql("CANNOT_ANSWER - no cost data"),                 {"refused"}),
    ("malformed SQL",               sql("SELEC id FROM customers WHERE"),                {"syntax"}),
    ("two statements",              sql("SELECT id FROM customers; DROP TABLE customers"), {"syntax"}),
    ("DELETE",                      sql("DELETE FROM orders"),                           {"allowlist"}),
    ("DROP TABLE",                  sql("DROP TABLE customers"),                         {"allowlist", "syntax"}),
    ("UPDATE",                      sql("UPDATE products SET unit_price = 0"),           {"allowlist"}),
    ("INSERT",                      sql("INSERT INTO regions (name) VALUES ('x')"),      {"allowlist"}),
    ("TRUNCATE",                    sql("TRUNCATE orders"),                              {"allowlist", "syntax"}),
    ("mixed-case DELETE",           sql("dElEtE FrOm orders"),                           {"allowlist"}),
    ("DELETE hidden in CTE",        sql("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d"), {"allowlist"}),
    ("SELECT INTO (creates table)", sql("SELECT * INTO leak FROM customers"),            {"allowlist", "schema", "explain", "syntax"}),
    ("SELECT FOR UPDATE (locks)",   sql("SELECT * FROM orders FOR UPDATE"),              {"allowlist", "explain"}),
    ("fake table",                  sql("SELECT * FROM employees"),                      {"schema"}),
    ("fake column",                 sql("SELECT salary FROM customers"),                 {"schema"}),
    ("system catalog table",        sql("SELECT * FROM pg_catalog.pg_user"),             {"schema"}),
    ("information_schema table",    sql("SELECT * FROM information_schema.tables"),     {"schema"}),
    ("invalid interval unit",       sql("SELECT COUNT(*) FROM orders WHERE created_at > NOW() - INTERVAL '1 quarter'"), {"explain"}),
    ("pg_sleep",                    sql("SELECT pg_sleep(10)"),                          {"functions"}),
    ("set_config",                  sql("SELECT set_config('statement_timeout','0',false)"), {"functions"}),
    ("pg_read_file",                sql("SELECT pg_read_file('/etc/passwd')"),           {"functions"}),
    ("pg_sleep inside real query",  sql("SELECT id, pg_sleep(1) FROM customers"),        {"functions"}),
    ("current_setting",             sql("SELECT current_setting('server_version')"),     {"functions"}),
    ("dblink",                      sql("SELECT * FROM dblink('host=x','SELECT 1') AS t(a int)"), {"functions", "schema", "explain"}),
    ("fake refusal, no FROM",       sql("SELECT 'cannot compute' AS error"),             {"no_data_source"}),
    ("WHERE FALSE",                 sql("SELECT id FROM products WHERE FALSE"),          {"vacuous_filter"}),
    ("WHERE 1=0",                   sql("SELECT id FROM products WHERE 1 = 0"),          {"vacuous_filter"}),
    ("LIMIT 0",                     sql("SELECT id, name FROM products LIMIT 0"),        {"empty_limit"}),
    ("literal-alias + LIMIT 0",     sql("SELECT id, 'no cost data' AS profit_margin FROM products LIMIT 0"), {"empty_limit"}),
    # ---------- must PASS (false-positive controls) ----------
    ("simple count",                sql("SELECT COUNT(*) FROM customers"),               None),
    ("join + group by",             sql("SELECT r.name, SUM(oi.amount) FROM orders o JOIN order_items oi ON oi.order_id = o.id JOIN regions r ON r.id = o.region_id GROUP BY r.name"), None),
    ("CTE",                         sql("WITH t AS (SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY customer_id) SELECT COUNT(*) FROM t WHERE n > 3"), None),
    ("derived-table subquery",      sql("SELECT AVG(total) FROM (SELECT order_id, SUM(amount) AS total FROM order_items GROUP BY order_id) s"), None),
    ("EXISTS subquery",             sql("SELECT COUNT(*) FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)"), None),
    ("DATE_TRUNC + EXTRACT",        sql("SELECT EXTRACT(YEAR FROM created_at), DATE_TRUNC('month', created_at), COUNT(*) FROM orders GROUP BY 1, 2"), None),
    ("window function",             sql("SELECT id, RANK() OVER (ORDER BY unit_price DESC) FROM products"), None),
    ("comment inside query",        sql("SELECT /* count */ COUNT(*) FROM customers -- trailing"), None),
    ("allowed age() function",      sql("SELECT AGE(NOW(), signup_date) FROM customers"), None),
    ("legit WHERE filter",          sql("SELECT COUNT(*) FROM orders WHERE status = 'shipped'"), None),
    ("legit LIMIT 5",               sql("SELECT name FROM products ORDER BY unit_price DESC LIMIT 5"), None),
]


def main():
    conn = get_reader_connection()
    fail_open, false_pos, mismatch, errors = [], [], [], []
    caught_by = Counter()
    try:
        for name, raw, expected in CASES:
            try:
                v = validate_sql(raw, conn)
            except Exception as e:
                errors.append((name, f"{type(e).__name__}: {e}"))
                print(f"ERROR           {name}  ->  {type(e).__name__}: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue
            layer = v["failed_at"]
            if expected is None:
                if v["passed"]:
                    print(f"ok (allowed)    {name}")
                else:
                    false_pos.append((name, layer, v["errors"]))
                    print(f"FALSE-POSITIVE  {name}  ->  blocked at {layer}: {v['errors']}")
            else:
                if v["passed"]:
                    fail_open.append(name)
                    print(f"FAIL-OPEN       {name}  ->  ALLOWED THROUGH")
                else:
                    caught_by[layer] += 1
                    if layer in expected:
                        print(f"ok (blocked)    {name}  ->  {layer}")
                    else:
                        mismatch.append((name, layer, expected))
                        print(f"blocked, other  {name}  ->  {layer} (expected {sorted(expected)})")
    finally:
        conn.close()

    blocked_cases = sum(1 for _, _, e in CASES if e is not None)
    valid_cases = len(CASES) - blocked_cases
    print("\n=== Guardrail-only results ===")
    print(f"Dangerous inputs blocked : {blocked_cases - len(fail_open)} / {blocked_cases}   (fail-open: {len(fail_open)})")
    print(f"Valid queries allowed    : {valid_cases - len(false_pos)} / {valid_cases}   (false positives: {len(false_pos)})")
    print(f"Caught by a different layer than expected: {len(mismatch)}")
    print(f"Errors while validating  : {len(errors)}")
    print("\nFirst layer to reject, per layer:")
    all_layers = ["extract", "refused", "syntax", "allowlist", "schema", "explain",
                  "functions", "no_data_source", "vacuous_filter", "empty_limit"]
    for l in all_layers:
        print(f"  {l:<16} {caught_by.get(l, 0)}")
    unused = [l for l in all_layers if caught_by.get(l, 0) == 0]
    if unused:
        print("\nLayers that never caught anything (no test exercises them first):", unused)
    return not (fail_open or false_pos or errors)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)