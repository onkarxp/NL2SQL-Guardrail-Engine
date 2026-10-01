from retrieval.retrieve import retrieve_relevant_tables
from generation.generate import build_prompt, ask_claude
from generation.retry import generate_and_execute

def ask(question, top_k=4, max_attempts=3):
    return generate_and_execute(
        question,
        ask_fn=ask_claude,
        build_prompt_fn=build_prompt,
        retrieve_fn=retrieve_relevant_tables,
        top_k=top_k,
        max_attempts=max_attempts,
    )

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "List all cancelled orders"
    r = ask(q)
    print(f"success={r['success']} attempts={len(r['attempts'])}")
    print(f"\nSQL:\n{r['final']['sql']}\n")
    if r["success"]:
        print(r["final"]["columns"])
        for row in r["final"]["rows"][:10]:
            print(row)
    else:
        print("Failed:", r["final"]["errors"])