from guardrails.extract import extract_sql_queries
from guardrails.validators import check_syntax, check_select_only, check_schema, check_explain
from retrieval.catalog import get_schema_catalog

def validate_sql(raw_output: str, conn):
    sql = extract_sql_queries(raw_output)
    if not sql:
        return {"passed": False, "sql": None, "failed_at": "extract",
                "errors": ["No SQL found in model output"]}

    tree, err = check_syntax(sql)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "syntax", "errors": [err]}

    err = check_select_only(tree)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "allowlist", "errors": [err]}

    errs = check_schema(tree, get_schema_catalog(conn))
    if errs:
        return {"passed": False, "sql": sql, "failed_at": "schema", "errors": errs}

    err = check_explain(sql, conn)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "explain", "errors": [err]}

    return {"passed": True, "sql": sql, "failed_at": None, "errors": []}