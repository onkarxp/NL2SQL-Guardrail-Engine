from execution.plausibility import check_plausibility
from generation.answer import build_grounded_answer
from generation.generate import ask_claude
from ask import ask as run_pipeline

def ask_with_answer(question):
    r = run_pipeline(question)
    if not r["success"]:
        return r

    r["plausibility_notes"] = check_plausibility(r["final"])
    r["answer"] = build_grounded_answer(question, r["final"], ask_claude)
    return r

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What was the revenue by region last quarter?"
    r = ask_with_answer(q)
    print("SQL:", r["final"]["sql"])
    print("Plausibility notes:", r["plausibility_notes"])
    print("Answer:", r["answer"]["answer"])
    print("Grounded:", r["answer"]["grounded"], " ungrounded numbers:", r["answer"]["ungrounded_numbers"])