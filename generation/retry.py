from execution.sandbox import execute_query

MAX_ATTEMPTS = 3

def generate_and_execute(question, ask_fn, build_prompt_fn, retrieve_fn, top_k=4, max_attempts=MAX_ATTEMPTS):
    retrieved = retrieve_fn(question, top_k=top_k)
    prompt = build_prompt_fn(question, retrieved)
    messages = [{"role": "user", "content": prompt}]

    attempts = []
    for attempt_num in range(1, max_attempts + 1):
        raw_output = ask_fn(messages)
        messages.append({"role": "assistant", "content": raw_output})

        result = execute_query(raw_output)
        attempts.append({"attempt": attempt_num, "raw_output": raw_output, "result": result})
        
        if result.get("failed_at") == "refused":
            return {"question": question, "success": False, "refused": True,
                    "reason": result["errors"][0], "attempts": attempts, "final": result}

        if result["executed"]:
            return {"question": question, "success": True, "attempts": attempts, "final": result}

        error = result["errors"][0] if result["errors"] else "Unknown validation failure"
        followup = (
            f"Your query failed validation ({result['failed_at']} check): {error}\n"
            "Fix the SQL and respond again using the same format: REASONING: ... / SQL: ..."
        )
        messages.append({"role": "user", "content": followup})

    return {"question": question, "success": False, "attempts": attempts, "final": attempts[-1]["result"]}