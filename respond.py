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

def respond(question: str, force_verify: bool = False):
    r = ask(question)
    if not r["success"]:
        return r

    r["plausibility_notes"] = check_plausibility(r["final"])
    r["answer"] = build_grounded_answer(question, r["final"], ask_claude)

    if force_verify or should_auto_verify(question):
        r["consistency"] = check_consistency_n(
            question, ask_fn=ask_claude, build_prompt_fn=build_prompt,
            retrieve_fn=retrieve_relevant_tables,
            generate_and_execute_fn=generate_and_execute, runs=3,
        )
    return r

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What was the revenue by region last quarter?"
    r = respond(q)
    print("SQL:", r["final"]["sql"])
    print("Answer:", r["answer"]["answer"])
    print("Grounded:", r["answer"]["grounded"])
    if "consistency" in r:
        print("Consistency check:", r["consistency"])