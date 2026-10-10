import json, time
from collections import Counter
from decimal import Decimal
from itertools import permutations
from ask import ask
from respond import respond
from execution.sandbox import get_reader_connection
from evaluation.cases import CASES

TABLES = ["regions", "customers", "products", "orders", "order_items"]
REPEATS = 3


def _norm(rows):
    def cell(v):
        if isinstance(v, (int, float, Decimal)):
            return round(float(v), 2)
        return str(v)
    return sorted(tuple(cell(v) for v in row) for row in rows)


def _reference_rows(sql):
    conn = get_reader_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def _table_counts():
    conn = get_reader_connection()
    try:
        with conn.cursor() as cur:
            out = {}
            for t in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                out[t] = cur.fetchone()[0]
            return out
    finally:
        conn.close()


def _matches(got_rows, want_rows):
    """True if some selection of the generated columns reproduces the reference result.
    Tolerates extra columns, column order and aliases."""
    want = _norm(want_rows)
    if not want_rows:
        return not got_rows
    if not got_rows:
        return False
    n_ref, n_got = len(want_rows[0]), len(got_rows[0])
    if n_got < n_ref:
        return False
    for cols in permutations(range(n_got), n_ref):
        projected = [tuple(row[i] for i in cols) for row in got_rows]
        if _norm(projected) == want:
            return True
    return False


def _attempt_count(r):
    a = r.get("attempts")
    return len(a) if isinstance(a, list) else a


def _layers_hit(r):
    """Which guardrail layer rejected each attempt (empty if first attempt passed)."""
    out = []
    for a in r.get("attempts") or []:
        res = a["result"]
        if not res.get("executed"):
            out.append(res.get("failed_at"))
    return out


def run_case(case):
    t0 = time.time()
    rec = {"id": case["id"], "kind": case["kind"], "question": case["question"]}
    try:
        if case["kind"] == "ambiguous":
            r = respond(case["question"], force_verify=True)
            rec["success"] = r.get("success", True)
            rec["low_confidence"] = r.get("low_confidence")
            rec["verified"] = r.get("verified", True)
            rec["distinct_answers"] = (r.get("consistency") or {}).get("distinct_answers")
            rec["passed"] = None            # recorded, not graded
        else:
            r = ask(case["question"])
            final = r.get("final") or {}
            rec["success"] = r["success"]
            rec["refused"] = r.get("refused", False)
            rec["attempts"] = _attempt_count(r)
            rec["layers"] = _layers_hit(r)
            rec["sql"] = final.get("sql")
            rec["failed_at"] = None if r["success"] else final.get("failed_at")
            rec["errors"] = None if r["success"] else final.get("errors")
            if case["kind"] == "blocked":
                rec["passed"] = not r["success"]    # True = no result returned
            elif not r["success"]:
                rec["passed"] = False
            else:
                rec["passed"] = _matches(final["rows"], _reference_rows(case["reference_sql"]))
    except Exception as e:                           # a crash is recorded, never silent
        rec["passed"] = False if case["kind"] != "ambiguous" else None
        rec["crash"] = f"{type(e).__name__}: {e}"
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main():
    before = _table_counts()
    results = []
    for c in CASES:
        runs = [run_case(c) for _ in range(REPEATS)]
        results.extend(runs)
        graded = [r["passed"] for r in runs if r["passed"] is not None]
        if graded:
            rate = f"{sum(graded)}/{len(graded)}"
            flag = "  <-- UNSTABLE" if 0 < sum(graded) < len(graded) else ""
            flag += "  <-- CRASH" if any("crash" in r for r in runs) else ""
        else:
            lc = [r.get("low_confidence") for r in runs]
            rate, flag = f"low_conf {lc}", ""
        print(f'{c["id"]} {c["kind"]:<9} {rate:<18} {c["question"]}{flag}')
    after = _table_counts()

    ans = [r for r in results if r["kind"] == "answer"]
    blk = [r for r in results if r["kind"] == "blocked"]

    print("\n=== Summary (%d runs per case) ===" % REPEATS)
    print("Execution accuracy       :", sum(r["passed"] for r in ans), "/", len(ans))
    print("First-attempt answers    :", sum(1 for r in ans if r["success"] and r.get("attempts") == 1), "/", len(ans))
    print("Blocked / no result      :", sum(r["passed"] for r in blk), "/", len(blk))
    print("Cleanly refused          :", sum(1 for r in blk if r.get("refused")), "/", len(blk))
    print("Tables unchanged         :", before == after)

    layer_counts = Counter(l for r in results if r["kind"] != "ambiguous" for l in r.get("layers", []))
    print("\nGuardrail layer that rejected an attempt (all runs):")
    for layer, n in layer_counts.most_common():
        print(f"  {layer:<16} {n}")

    unstable = sorted({r["id"] for r in results if r["passed"] is not None and
                       0 < sum(x["passed"] for x in results if x["id"] == r["id"]) < REPEATS})
    print("\nUnstable cases:", unstable or "none")

    with open("eval_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    main()