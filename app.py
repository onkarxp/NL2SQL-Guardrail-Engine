import time
from decimal import Decimal

import pandas as pd
import streamlit as st

from respond import respond
from retrieval.retrieve import retrieve_relevant_tables

st.set_page_config(page_title="SafeQuery", page_icon="🛡️", layout="wide")

EXAMPLES = [
    "What is the total revenue by region?",
    "How many customers have no orders?",
    "What is the average order value?",
    "What was the revenue by region last quarter?",
    "Delete all orders from the database.",
    "What is the profit margin per product?",
]


def to_dataframe(final):
    df = pd.DataFrame(final["rows"], columns=final["columns"])
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].map(lambda v: float(v) if isinstance(v, Decimal) else v)
    return df


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("🛡️ SafeQuery")
    st.caption("Guardrailed natural-language-to-SQL over a read-only Postgres database.")
    force_verify = st.checkbox(
        "Always run consistency check",
        value=False,
        help="Runs the question 3 more times and compares the answers. Costs extra LLM calls. "
             "Questions with words like 'average', 'rate' or 'last quarter' trigger it automatically.",
    )
    st.divider()
    st.caption("Try an example:")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex, key=f"ex{i}", width="stretch"):
            st.session_state["question"] = ex

# ---------------- main ----------------
st.title("Ask your database a question")
question = st.text_input("Question", key="question", placeholder="e.g. What is the total revenue by region?")
go = st.button("Ask", type="primary")

if go and question.strip():
    t0 = time.perf_counter()
    with st.spinner("Retrieving schema, generating SQL, validating, executing…"):
        r = respond(question.strip(), force_verify=force_verify)
    elapsed = time.perf_counter() - t0
    try:
        retrieved = retrieve_relevant_tables(question.strip(), top_k=4)
    except Exception as e:
        retrieved = f"(could not display: {e})"

    left, right = st.columns([3, 2], gap="large")

    # ---------- left: what the user sees ----------
    with left:
        if not r["success"]:
            if r.get("refused"):
                st.warning(f"**I can't answer that.** {r.get('reason', '')}")
            else:
                final = r.get("final") or {}
                st.error(f"Validation failed at **{final.get('failed_at')}**: {final.get('errors')}")
        else:
            if r.get("low_confidence"):
                st.warning(
                    f"**Low confidence.** Repeated runs gave {len(r['possible_answers'])} "
                    "different answers. Each reading is listed below."
                )
            elif r.get("verified") is False:
                st.info("Could not verify this answer (the consistency check could not run).")

            ans = r["answer"]
            st.subheader("Answer")
            st.write(ans["answer"])
            if ans.get("grounded"):
                st.success("Grounded: every number in this answer appears in the query result.")
            else:
                st.error(f"Not grounded: these numbers are not in the result: {ans.get('ungrounded_numbers')}")

            for note in r.get("plausibility_notes", []):
                st.info(note)

            st.subheader("Data")
            st.dataframe(to_dataframe(r["final"]), width="stretch")

            if r.get("low_confidence"):
                st.subheader("Possible answers")
                for k, alt in enumerate(r["possible_answers"], 1):
                    with st.expander(f"Reading {k}: {alt['share_pct']}% of runs"):
                        st.json(alt["values"])
                        st.code(alt["sql"], language="sql")

    # ---------- right: telemetry ----------
    with right:
        st.subheader("🔍 Guardrail telemetry")
        c1, c2 = st.columns(2)
        c1.metric("Total time", f"{elapsed:.1f} s")
        c2.metric("Attempts", len(r.get("attempts", [])))

        st.markdown("**1. Retrieved tables**")
        st.write(retrieved)

        st.markdown("**2. Generation attempts**")
        for a in r.get("attempts", []):
            res = a["result"]
            if res.get("executed"):
                st.success(f"Attempt {a['attempt']}: passed every layer and ran")
            elif res.get("failed_at") == "refused":
                st.warning(f"Attempt {a['attempt']}: model refused ({res['errors'][0]})")
            else:
                st.error(f"Attempt {a['attempt']}: rejected by **{res.get('failed_at')}**: {res.get('errors')}")

        if r["success"]:
            st.markdown("**3. SQL that ran**")
            st.code(r["final"]["sql"], language="sql")

        if "consistency" in r:
            c = r["consistency"]
            st.markdown("**4. Consistency check**")
            if c.get("agreement_rate") is None:
                st.write(c.get("reason", "not comparable"))
            else:
                st.write(
                    f"{c['n']} runs · {c['agreement_rate']}% agree · "
                    f"{c['distinct_answers']} distinct answer(s) · {c['distinct_sql_shapes']} SQL variant(s)"
                )