def _extract_numeric_map(result):
    """Turn a query result into {label: number}, matching by the first
    text column and the first fully-numeric column, not by row position."""
    columns = result["columns"]
    rows = result["rows"]
    label_idx, value_idx = 0, None
    for i in range(len(columns)):
        if i == 0:
            continue
        if rows and all(isinstance(r[i], (int, float)) or type(r[i]).__name__ == "Decimal" for r in rows):
            value_idx = i
            break
    if value_idx is None:
        return None
    return {str(r[label_idx]): float(r[value_idx]) for r in rows}


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
    

def check_consistency_n(question, ask_fn, build_prompt_fn, retrieve_fn, generate_and_execute_fn, runs=5, tolerance=0.15):
    results = []
    for _ in range(runs):
        r = generate_and_execute_fn(question, ask_fn, build_prompt_fn, retrieve_fn, max_attempts=1)
        if r["success"]:
            m = _extract_numeric_map(r["final"])
            if m:
                results.append((r["final"]["sql"], m))

    if len(results) < 2:
        return {"agreement_rate": None, "reason": "fewer than 2 successful comparable runs"}

    baseline_sql, baseline_map = results[0]
    agree_count = 0
    sql_variants = set()
    for sql, m in results:
        sql_variants.add(sql)
        shared = set(m) & set(baseline_map)
        if shared and all(abs(m[k] - baseline_map[k]) / max(abs(m[k]), abs(baseline_map[k]), 1e-9) <= tolerance for k in shared):
            agree_count += 1

    return {"agreement_rate": round(agree_count / len(results) * 100, 1),
            "distinct_sql_shapes": len(sql_variants), "n": len(results)}