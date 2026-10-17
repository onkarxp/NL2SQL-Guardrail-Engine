# respond.py (project root)
from ask import ask
from execution.plausibility import check_plausibility
from generation.answer import build_grounded_answer
from execution.consistency import check_consistency_n
from generation.generate import ask_claude, build_prompt
from retrieval.retrieve import retrieve_relevant_tables
from generation.retry import generate_and_execute

AMBIGUITY_TRIGGERS = ["average", "avg", "mean", "rate", "percent", "%",
                      "last quarter", "last month", "this year", "ratio"]

def should_auto_verify(question: str) -> bool:
    q = question.lower()
    return any(trigger in q for trigger in AMBIGUITY_TRIGGERS)

# added this to make sure that in the cases of queries, where there is a possibility of more than two perceptions
# of the answer, we can run multiple times and check for consistency. 
# If there is a disagreement, we can flag it as low confidence.
LOW_CONFIDENCE_BELOW = 100.0   # any disagreement at all flags it

def respond(question, force_verify=False):
    r = ask(question)
    if not r["success"]:
        return r
    r["plausibility_notes"] = check_plausibility(r["final"])
    if r["final"].get("truncated"):
        r["plausibility_notes"].append(
            f"Result truncated: only the first {r['final']['row_count']} rows are shown; "
            "the full result is larger."
        )
    r["answer"] = build_grounded_answer(question, r["final"], ask_claude)

    r["low_confidence"] = False
    r["verified"] = None            # None = no consistency check was requested or triggered
    if force_verify or should_auto_verify(question):
        c = check_consistency_n(question, ask_fn=ask_claude, build_prompt_fn=build_prompt,
                                retrieve_fn=retrieve_relevant_tables,
                                generate_and_execute_fn=generate_and_execute, runs=3)
        r["consistency"] = c
        if c.get("agreement_rate") is None:
            r["verified"] = False   # the check could not run: do not present as confident
        else:
            r["verified"] = True
            if c["agreement_rate"] < LOW_CONFIDENCE_BELOW:
                r["low_confidence"] = True
                r["possible_answers"] = c["alternatives"]
    return r

if __name__ == "__main__":
    import sys
    question = " ".join(sys.argv[1:])
    r = respond(question)

    if not r["success"]:
        if r.get("refused"):
            print("Could not answer:", r.get("reason", "no reason given"))
        else:
            print("Failed validation at:", (r.get("final") or {}).get("failed_at"))
            print("Errors:", (r.get("final") or {}).get("errors"))
        sys.exit(0)

    print("SQL:", r["final"]["sql"])
    print("Answer:", r["answer"]["answer"])
    print("Grounded:", r["answer"]["grounded"])
    for note in r.get("plausibility_notes", []):
        print("Note:", note)

    if r.get("verified") is False:
        print("Could not verify this answer (consistency check did not run).")
    elif r.get("low_confidence"):
        print(f"LOW CONFIDENCE: {len(r['possible_answers'])} different answers across runs")
        for alt in r["possible_answers"]:
            print(f"  {alt['share_pct']}% of runs: {alt['values']}")
            print(f"    SQL: {alt['sql']}")
    elif "consistency" in r:
        c = r["consistency"]
        print(f"Consistency: {c['agreement_rate']}% agreement over {c['n']} runs")