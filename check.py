from retrieval.retrieve import retrieve_relevant_tables
from generation.generate import build_prompt, ask_claude
from generation.retry import generate_and_execute
from execution.consistency import check_consistency, check_consistency_n
from execution.consistency import check_consistency_n
  
if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What's the average order value per region?"


    result = check_consistency_n(q, ask_fn=ask_claude, build_prompt_fn=build_prompt,
                              retrieve_fn=retrieve_relevant_tables,
                              generate_and_execute_fn=generate_and_execute, runs=5)
    print(result)
    if result.get("disagreements"):
        print("\nDisagreements:")
        for d in result["disagreements"]:
            print(f"  {d['label']}: run1={d['run1']}  run2={d['run2']}  diff={d['pct_diff']}%")
    if "sql_1" in result:
        print(f"\nRun 1 SQL:\n{result['sql_1']}")
        print(f"\nRun 2 SQL:\n{result['sql_2']}")