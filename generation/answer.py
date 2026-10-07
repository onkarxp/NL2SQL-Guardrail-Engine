import re

def build_answer_prompt(question, result):
    rows_text = "\n".join(", ".join(str(v) for v in row) for row in result["rows"])
    return f"""Question: {question}

Query result (columns: {", ".join(result["columns"])}):
{rows_text}

Write one or two plain-English sentences answering the question.
Only state numbers that appear exactly in the result above. Do not
calculate, round, or infer any number not literally shown."""


def _numbers_in(text):
    return {float(n.replace(",", "")) for n in re.findall(r"-?\d[\d,]*\.?\d*", text)}


def _numbers_in_result(result):
    nums = set()
    for row in result["rows"]:
        for v in row:
            if isinstance(v, (int, float)) or type(v).__name__ == "Decimal":
                nums.add(round(float(v), 2))
    return nums


def build_grounded_answer(question, result, ask_fn):
    if result["row_count"] == 0:
        return {"answer": "No matching results were found for this question.", "grounded": True, "ungrounded_numbers": []}

    prompt = build_answer_prompt(question, result)
    answer_text = ask_fn([{"role": "user", "content": prompt}])

    claimed = _numbers_in(answer_text)
    real = _numbers_in_result(result)
    ungrounded = sorted(n for n in claimed if round(n, 2) not in real and n not in real)

    return {"answer": answer_text, "grounded": len(ungrounded) == 0, "ungrounded_numbers": ungrounded}