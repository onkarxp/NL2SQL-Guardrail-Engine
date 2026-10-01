from generation.generate import ask_claude, build_prompt
from retrieval.retrieve import retrieve_relevant_tables
from generation.retry import generate_and_execute

result = generate_and_execute(
    "What's the average order value per region for orders placed in the last 90 days, excluding cancelled orders?",
    ask_fn=ask_claude,
    build_prompt_fn=build_prompt,
    retrieve_fn=retrieve_relevant_tables,
)
print(f"success={result['success']} in {len(result['attempts'])} attempt(s)")
for a in result["attempts"]:
    r = a["result"]
    status = "EXECUTED" if r["executed"] else f"BLOCKED at={r['failed_at']}: {r['errors']}"
    print(f"  attempt {a['attempt']}: {status}")