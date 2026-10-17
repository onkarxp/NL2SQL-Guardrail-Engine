import re
import datetime

def build_answer_prompt(question, result):
    rows_text = "\n".join(", ".join(str(v) for v in row) for row in result["rows"])

    truncation_rule = ""
    if result.get("truncated"):
        truncation_rule = f"""
IMPORTANT: this result was cut off at {result['row_count']} rows. There are MORE rows
than shown. Describe what the rows show as a sample. Do NOT say how many rows,
records or orders exist in total, and do not treat the rows as the complete data.
"""

    return f"""Question: {question}

Query result (columns: {", ".join(result["columns"])}):
{rows_text}
{truncation_rule}
Write one or two plain-English sentences answering the question.
Only state numbers that appear exactly in the result above. Do not
calculate, round, or infer any number not literally shown."""


def _numbers_in(text):
    return {float(n.replace(",", "")) for n in re.findall(r"-?\d[\d,]*\.?\d*", text)}


def _numbers_in_result(result):
    nums = set()
    for row in result["rows"]:
        for v in row:
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) or type(v).__name__ == "Decimal":
                nums.add(round(float(v), 2))
            elif isinstance(v, (datetime.date, datetime.datetime)):
                # a date such as 2025-09-12 is also a legitimate source of
                # the numbers 2025, 9 and 12 ("September 2025")
                nums.update({float(v.year), float(v.month), float(v.day)})
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