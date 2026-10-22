"""Measures latency and cost per query for a fixed set of representative questions.
Run:  python -m evaluation.measure_cost
Costs a few rupees in API credit."""
import json
import statistics
import time

from generation import generate as G
from respond import respond

# Claude Haiku 4.5 list price (USD per token): $1 / MTok input, $5 / MTok output.
PRICE_IN = 1.00 / 1_000_000
PRICE_OUT = 5.00 / 1_000_000
USD_TO_INR = 94.6   # PLACEHOLDER: set this to today's exchange rate

QUESTIONS = [
    # (group, question, force consistency check)
    ("simple",  "How many customers are there?", False),
    ("simple",  "List the names of all regions.", False),
    ("simple",  "What is the highest product price?", False),
    ("simple",  "How many orders are there for each status?", False),
    ("join",    "What is the total revenue by region?", False),
    ("join",    "How many customers have no orders?", False),
    ("join",    "What is the total revenue for each product category?", False),
    ("join",    "Which product category has the highest total revenue?", False),
    ("complex", "For each region, using the region on the order, list the top 3 product categories by total revenue from shipped orders created in 2026. For each category show the revenue (the sum of order item amounts) and its percentage of that region's total shipped revenue in 2026. Order by region name, then revenue descending.", False),
    ("complex", "For each region (using the customer's region), compare 2025 and 2026: the number of orders, the number of cancelled or returned orders, and the cancelled-or-returned rate as a percentage of all orders in that year. Only include regions that had at least 160 orders in both years, and order them by the increase in the rate from 2025 to 2026, largest first.", False),
    ("complex", "Segment all customers into three groups: those who have never placed an order, those whose total spend across all their orders is below the average total spend of customers who have ordered, and those at or above that average. For each segment show the number of customers, their average total spend (0 for the never-ordered group), and how many signed up in 2025 versus 2026. Total spend means the sum of order item amounts.", False),
    ("refused", "Delete all orders from the database.", False),
    ("refused", "What is the profit margin per product?", False),
    ("consistency", "What is the average order value?", True),
    ("consistency", "What was the revenue by region last quarter?", True),
    ("consistency", "How many orders were created in each year?", True),
]


def run_one(group, question, force):
    G.USAGE_LOG.clear()
    t0 = time.perf_counter()
    try:
        r = respond(question, force_verify=force)
        outcome = ("answered" if r.get("success") else
                   "refused" if r.get("refused") else "failed")
        consistency = "consistency" in r
        error = None
    except Exception as e:
        outcome, consistency, error = "crashed", False, f"{type(e).__name__}: {e}"
    total = time.perf_counter() - t0
    calls = list(G.USAGE_LOG)
    tin = sum(c["in"] for c in calls)
    tout = sum(c["out"] for c in calls)
    llm_sec = sum(c["sec"] for c in calls)
    usd = tin * PRICE_IN + tout * PRICE_OUT
    return {
        "group": group, "question": question[:70], "outcome": outcome,
        "consistency_ran": consistency, "total_sec": round(total, 2),
        "llm_sec": round(llm_sec, 2), "other_sec": round(total - llm_sec, 2),
        "llm_calls": len(calls), "tokens_in": tin, "tokens_out": tout,
        "usd": usd, "error": error,
    }


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def worst(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.9 * len(xs)))] if xs else float("nan")


def main():
    print("Warm-up (loads the embedding model; not counted)...")
    run_one("warmup", "How many customers are there?", False)

    rows = []
    for group, q, force in QUESTIONS:
        row = run_one(group, q, force)
        rows.append(row)
        print(f"{row['group']:<12} {row['outcome']:<9} {row['total_sec']:>6.1f}s  "
              f"calls={row['llm_calls']}  in={row['tokens_in']:>5} out={row['tokens_out']:>4}  "
              f"${row['usd']:.4f}  {row['question']}")
        if row["error"]:
            print("   ERROR:", row["error"])

    if all(r["llm_calls"] == 0 for r in rows):
        print("\nNo model calls were logged. Check the generate.py edits.")
        return

    print("\n=== Summary (one run per question) ===")
    print(f"{'group':<12} {'n':>2} {'median s':>9} {'slowest10%':>11} {'calls':>6} {'median $':>10} {'median Rs':>10}")
    for g in ["simple", "join", "complex", "refused", "consistency"]:
        rs = [r for r in rows if r["group"] == g]
        print(f"{g:<12} {len(rs):>2} {med([r['total_sec'] for r in rs]):>9.1f} "
              f"{worst([r['total_sec'] for r in rs]):>11.1f} "
              f"{med([r['llm_calls'] for r in rs]):>6.0f} "
              f"{med([r['usd'] for r in rs]):>10.4f} "
              f"{med([r['usd'] for r in rs]) * USD_TO_INR:>10.2f}")

    normal = [r for r in rows if r["group"] in ("simple", "join", "complex")
            and r["outcome"] == "answered" and not r["consistency_ran"]]
    print("\nNormal answered queries (simple + join + complex, no consistency check):")
    print(f"  n = {len(normal)}")
    print(f"  median latency   : {med([r['total_sec'] for r in normal]):.1f} s")
    print(f"  slowest 10%      : {worst([r['total_sec'] for r in normal]):.1f} s")
    print(f"  of which model   : {med([r['llm_sec'] for r in normal]):.1f} s (median); "
          f"retrieval + validation + database: {med([r['other_sec'] for r in normal]):.1f} s")
    print(f"  model calls      : {med([r['llm_calls'] for r in normal]):.0f} (median)")
    print(f"  tokens in / out  : {med([r['tokens_in'] for r in normal]):.0f} / {med([r['tokens_out'] for r in normal]):.0f} (median)")
    print(f"  cost per query   : ${med([r['usd'] for r in normal]):.4f}  =  Rs {med([r['usd'] for r in normal]) * USD_TO_INR:.2f} (median)")
    print(f"  cost for 1,000   : ${med([r['usd'] for r in normal]) * 1000:.2f}")
    print(f"\n(USD to INR rate used: {USD_TO_INR}. Set it to today's rate.)")

    with open("measure_results.json", "w") as f:
        json.dump(rows, f, indent=2)
    print("Saved measure_results.json")


if __name__ == "__main__":
    main()