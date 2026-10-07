from respond import respond, should_auto_verify

def test_trigger_classification():
    cases = [
        ("What was the revenue by region last quarter?", True),
        ("What's the average order value per region?", True),
        ("List all cancelled orders", False),
        ("What products are in the Electronics category?", False),
        ("What percentage of orders are cancelled?", True),
        ("Show me the top-selling product in each region", False),
    ]
    for question, expected in cases:
        got = should_auto_verify(question)
        status = "PASS" if got == expected else "FAIL"
        print(f"{status}  expected={expected} got={got}  {question}")

def test_consistency_wiring():
    r1 = respond("List all cancelled orders")
    print("plain question, consistency ran:", "consistency" in r1, "(expect False)")

    r2 = respond("What's the average order value per region?")
    print("ambiguous question, consistency ran:", "consistency" in r2, "(expect True)")

    r3 = respond("List all cancelled orders", force_verify=True)
    print("forced, consistency ran:", "consistency" in r3, "(expect True)")

if __name__ == "__main__":
    print("--- trigger classification ---")
    test_trigger_classification()
    print("\n--- consistency wiring (real API calls, costs a few cents) ---")
    test_consistency_wiring()