def check_plausibility(result):
    # Flags, not failures -- these are notes for a human/UI to see,
    # not reasons to block an answer the way guardrails do.
    notes = []

    if result["row_count"] == 0:
        notes.append("Query returned zero rows -- could mean no matching data, "
                      "or a filter/join that's silently too strict")

    for col_idx, col_name in enumerate(result["columns"]):
        values = [row[col_idx] for row in result["rows"]]
        if values and all(v is None for v in values):
            notes.append(f"Column '{col_name}' is NULL in every row -- "
                          f"possible sign of a bad JOIN losing matches")

    return notes