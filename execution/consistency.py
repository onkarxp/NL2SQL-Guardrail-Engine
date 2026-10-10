
# Function of this function is to check the consistency of SQL query results generated from the same question. 
# It runs the query multiple times and compares the numeric results to see if they are consistent within a specified tolerance.
def _is_num(v):
    return isinstance(v, (int, float)) or type(v).__name__ == "Decimal"




def _extract_numeric_map(result):
    columns = result["columns"]
    rows = result["rows"]
    if not rows:
        return None
    # Scalar result (AVG/COUNT/SUM): one row, label each numeric column by its name
    if len(rows) == 1:
        m = {f"col{i}": float(v) for i, v in enumerate(rows[0]) if _is_num(v)}
        return m or None
    # Grouped result: first column is the label, first fully numeric later column is the value
    for i in range(1, len(columns)):
        if all(_is_num(r[i]) for r in rows):
            return {str(r[0]): float(r[i]) for r in rows}
    return None


def check_consistency(question, ask_fn, build_prompt_fn, retrieve_fn, generate_and_execute_fn, tolerance=0.15):
    r1 = generate_and_execute_fn(question, ask_fn, build_prompt_fn, retrieve_fn, max_attempts=1)
    r2 = generate_and_execute_fn(question, ask_fn, build_prompt_fn, retrieve_fn, max_attempts=1)

    if not (r1["success"] and r2["success"]):
        return {"consistent": None, "reason": "one or both attempts failed", "r1": r1, "r2": r2}

    m1 = _extract_numeric_map(r1["final"])
    m2 = _extract_numeric_map(r2["final"])
    if m1 is None or m2 is None:
        return {"consistent": None, "reason": "could not find a comparable numeric column"}

    shared_labels = set(m1) & set(m2)
    if not shared_labels:
        return {"consistent": None, "reason": "no matching row labels between the two runs"}

    disagreements = []
    for label in sorted(shared_labels):
        v1, v2 = m1[label], m2[label]
        base = max(abs(v1), abs(v2), 1e-9)
        pct_diff = abs(v1 - v2) / base
        if pct_diff > tolerance:
            disagreements.append({"label": label, "run1": v1, "run2": v2, "pct_diff": round(pct_diff * 100, 1)})

    return {
        "consistent": len(disagreements) == 0,
        "tolerance_pct": tolerance * 100,
        "disagreements": disagreements,
        "sql_1": r1["final"]["sql"],
        "sql_2": r2["final"]["sql"],
    }
    

def _same_numbers(m1, m2, tolerance):
    # Same labels, and every value within tolerance of its counterpart
    if set(m1) != set(m2):
        return False
    return all(abs(m1[k] - m2[k]) / max(abs(m1[k]), abs(m2[k]), 1e-9) <= tolerance for k in m1)


def check_consistency_n(question, ask_fn, build_prompt_fn, retrieve_fn,
                        generate_and_execute_fn, runs=5, tolerance=0.15):
    collected = []
    for _ in range(runs):
        r = generate_and_execute_fn(question, ask_fn, build_prompt_fn, retrieve_fn, max_attempts=1)
        if r["success"]:
            m = _extract_numeric_map(r["final"])
            if m:
                collected.append({"sql": r["final"]["sql"], "map": m})

    if len(collected) < 2:
        return {"agreement_rate": None, "distinct_answers": None,
                "reason": "fewer than 2 successful comparable runs"}

    clusters = []  # each cluster = one distinct numeric answer
    for run in collected:
        for c in clusters:
            if _same_numbers(run["map"], c["map"], tolerance):
                c["runs"] += 1
                break
        else:
            clusters.append({"map": run["map"], "runs": 1, "sql": run["sql"]})

    clusters.sort(key=lambda c: c["runs"], reverse=True)
    n = len(collected)
    return {
        "n": n,
        "agreement_rate": round(clusters[0]["runs"] / n * 100, 1),  # share in the biggest cluster
        "distinct_answers": len(clusters),
        "distinct_sql_shapes": len({r["sql"] for r in collected}),
        "alternatives": [{"runs": c["runs"], "share_pct": round(c["runs"] / n * 100, 1),
                          "sql": c["sql"], "values": c["map"]} for c in clusters],
    }