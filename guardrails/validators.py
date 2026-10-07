import sqlglot # sqlglot is used for parsing and analyzing SQL queries. 
# It provides a way to work with SQL expressions in a structured manner, allowing for validation, transformation, 
# and optimization of SQL code.
import psycopg2 # Used for connecting to PostgreSQL databases and executing SQL queries. It provides a Python interface for interacting with PostgreSQL, enabling the execution of SQL commands and retrieval of results.
from sqlglot import exp # exp is a module within sqlglot that provides classes and functions for working with SQL expressions. 
# It allows for the creation, manipulation, and analysis of SQL queries in a structured way.

def check_syntax(sql: str):
    try:
        trees = sqlglot.parse(sql, read="postgres")
        # Parse the SQL query into an abstract syntax tree (AST)
    except Exception as e:
        return None, f"Syntax error: {str(e)[:120]}" # [:120] limits the error message to 120 characters for brevity
    if len(trees) != 1  or trees[0] is None:
        return None, "Exactly one SQL statement is allowed."
    return trees[0], None # Return the parsed SQL tree and no error message


def check_select_only(tree):
    if not isinstance(tree, (exp.Select, exp.Union)):
        # checks if the parsed SQL tree is either a SELECT statement or a UNION of SELECT statements.
        return f"Only SELECT is allowed, got {type(tree).__name__.upper()}"
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create)
    # forbidden is a tuple containing SQL operation types that are not allowed in the query.
    for node in tree.walk():
        # The walk() method traverses the parsed SQL tree, allowing inspection of each node in the tree.
        if isinstance(node, forbidden):
            return f"Forbidden operation inside query: {type(node).__name__.upper()}"
    return None


# def check_schema(tree, catalog: dict):
#     errors = []
#     # returns any validation errors as a list of strings
#     cte_names = {c.alias for c in tree.find_all(exp.CTE)}
#     # Scans the SQL tree for Common Table Expressions (WITH cte AS ...) and saves their aliases into a set. 
#     # This prevents the code from treating temporary CTEs as missing database tables.
#     alias_to_table = {}
#     # Initializes a dictionary that will act as a translation guide, 
#     # linking query aliases (like u) back to physical table names (like users).

#     for t in tree.find_all(exp.Table):
#         # Starts a loop that goes through every single table refernced in the SQL query
#         if t.name in cte_names:
#             # ignore cte because they dont live in the catalog,
#             # they are temporary tables created within the query itself
#             continue
        
#         #if queries table is not present in the catalog, we add an error message to the errors list
#         if t.name not in catalog:
#             errors.append(f"Unknown table: {t.name}")
#         else:
#             # If the table is found in the catalog, we add an entry to the alias_to_table dictionary, 
#             # mapping the alias (or name) used in the query to the actual table name in the catalog.
#             alias_to_table[t.alias_or_name] = t.name

#     select_aliases = {a.alias for a in tree.find_all(exp.Alias)}
#     known_columns = {c["column"] for tbl in alias_to_table.values() for c in catalog[tbl]}

#     for col in tree.find_all(exp.Column):
#         if col.name in select_aliases and not col.table:
#             continue
#         if col.table:
#             tbl = alias_to_table.get(col.table)
#             if tbl is None:
#                 errors.append(f"Unknown table/alias: {col.table}")
#             elif col.name not in {c["column"] for c in catalog[tbl]}:
#                 errors.append(f"Unknown column: {col.table}.{col.name}")
#         elif col.name not in known_columns:
#             errors.append(f"Unknown column: {col.name}")
#     return errors

def check_schema(tree, catalog: dict):
    errors = [] 
    cte_names = {c.alias for c in tree.find_all(exp.CTE)}
    subquery_aliases = {s.alias for s in tree.find_all(exp.Subquery) if s.alias}
    virtual_names = cte_names | subquery_aliases  # not real tables: nothing to check columns against

    alias_to_table = {}
    for t in tree.find_all(exp.Table):
        if t.name in cte_names:
            continue
        if t.name not in catalog:
            errors.append(f"Unknown table: {t.name}")
        else:
            alias_to_table[t.alias_or_name] = t.name

    select_aliases = {a.alias for a in tree.find_all(exp.Alias)}
    known_columns = {c["column"] for tbl in alias_to_table.values() for c in catalog[tbl]}

    for col in tree.find_all(exp.Column):
        if col.name in select_aliases and not col.table:
            continue
        if col.table:
            if col.table in virtual_names:
                continue  # belongs to a CTE or derived subquery -- trust it
            tbl = alias_to_table.get(col.table)
            if tbl is None:
                errors.append(f"Unknown table/alias: {col.table}")
            elif col.name not in {c["column"] for c in catalog[tbl]}:
                errors.append(f"Unknown column: {col.table}.{col.name}")
        elif col.name not in known_columns:
            errors.append(f"Unknown column: {col.name}")
    return errors

def check_explain(sql: str, conn):
    cur = conn.cursor()
    try:
        cur.execute("EXPLAIN " + sql)
        return None
    except psycopg2.Error as e:
        conn.rollback()
        return f"Postgres rejected the query: {str(e).splitlines()[0]}"
    finally:
        cur.close()


ALLOWED_UNRECOGNIZED_FUNCTIONS = {"age"}

def check_functions(tree):
    used = {f.name.lower() for f in tree.find_all(exp.Anonymous)}
    bad = sorted(used - ALLOWED_UNRECOGNIZED_FUNCTIONS)
    if bad:
        return f"Function not on the allowlist: {', '.join(bad)}"
    return None

def check_data_source(tree):
    if tree.args.get("from_") is None:
        return "Query has no FROM clause and references no real data"
    return None

def check_where_is_not_vacuous(tree):
    where = tree.args.get("where")
    if where is None:
        return None
    if not list(where.find_all(exp.Column)):
        return "WHERE clause references no real columns (tautological filter, not a genuine data filter)"
    return None

