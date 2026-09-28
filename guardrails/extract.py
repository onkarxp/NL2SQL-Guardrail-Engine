## This file is used for pulling i.e extracting the SQL queries from the responses
import re ##python library for regex

def extract_sql_queries(raw_output: str):
    
    ## re func = re.search(pattern, string, flags=0)
    match = re.search(r"SQL:\s*(.*)", raw_output, re.DOTALL | re.IGNORECASE)
    ## THIS RETURNS A MATCH OBJECT IF FOUND, ELSE NONE
    if not match:
        return None
    sql = match.group(1).strip()  ## group(1) returns the first captured group, which is the SQL query
    
    ## Models sometimes wrap code in markdown fences, even when told not to:
    ## to solve this, we write this line of code
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql).strip()
    return sql.rstrip(";").strip() or None

if __name__ == "__main__":
    tests = [
        "REASONING: Filter by status.\nSQL: SELECT * FROM orders WHERE status = 'cancelled';",
        "REASONING: x\nSQL: ```sql\nSELECT * FROM regions\n```",
        "I can't answer that with this schema.",
        "REASONING: unclear\nSQL:",
    ]
    for t in tests:
        print(repr(extract_sql_queries(t)))
    
   