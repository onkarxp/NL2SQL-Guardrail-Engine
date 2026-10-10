
from guardrails.extract import extract_sql_queries
from guardrails.validators import check_syntax, check_select_only, check_schema, check_explain, check_functions, check_data_source, check_where_is_not_vacuous, check_no_empty_limit
from retrieval.catalog import get_schema_catalog

def validate_sql(raw_output: str, conn):
    sql = extract_sql_queries(raw_output)
    if not sql:
        return {"passed": False, "sql": None, "failed_at": "extract",
                "errors": ["No SQL found in model output"]}
    if sql.strip().upper().startswith("CANNOT_ANSWER"):
        reason = sql.strip()[len("CANNOT_ANSWER"):].lstrip(" -:") or "No reason given"
        return {"passed": False, "sql": None, "failed_at": "refused", "errors": [reason]}
    
    tree, err = check_syntax(sql)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "syntax", "errors": [err]}

    err = check_select_only(tree)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "allowlist", "errors": [err]}

    errs = check_schema(tree, get_schema_catalog(conn))
    ## here we are passing the catalog dictionary to the check_schema function, which will validate the SQL query against the known schema.
    if errs:
        return {"passed": False, "sql": sql, "failed_at": "schema", "errors": errs}

    err = check_explain(sql, conn)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "explain", "errors": [err]}
    
    err = check_functions(tree)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "functions", "errors": [err]}

    err = check_data_source(tree)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "no_data_source", "errors": [err]}
    
    err = check_where_is_not_vacuous(tree)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "vacuous_filter", "errors": [err]}

    err = check_no_empty_limit(tree)
    if err:
        return {"passed": False, "sql": sql, "failed_at": "empty_limit", "errors": [err]}
    return {"passed": True, "sql": sql, "failed_at": None, "errors": []}

    