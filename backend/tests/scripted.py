FILLER = "The parties agree to the schedules and the payment terms set out in this agreement. " * 3
QUOTES = {
    "governing_law": (2, "This Agreement shall be governed by the laws of the State of New York."),
    "termination_for_convenience": (
        3,
        "Either party may terminate this Agreement for convenience upon thirty days written notice.",
    ),
    "cap_on_liability": (
        3,
        "In no event shall either party aggregate liability exceed the fees paid in the preceding twelve months.",
    ),
    "anti_assignment": (
        4,
        "Neither party may assign this Agreement without the prior written consent of the other party.",
    ),
}
PAGES = [
    f"Preamble. {FILLER}",
    f"{QUOTES['governing_law'][1]} {FILLER}",
    f"{QUOTES['termination_for_convenience'][1]} {QUOTES['cap_on_liability'][1]} {FILLER}",
    f"{QUOTES['anti_assignment'][1]} {FILLER}",
]
SUGGESTION = {"text": "Better wording.", "explanation": "Because the playbook says so."}




def default_reply(tool: str, clause: str):
    if tool == "ClauseExtraction":
        if clause not in QUOTES:
            return {"found": False, "quote": None, "reasoning": "not in the passages"}
        return {"found": True, "quote": QUOTES[clause][1], "reasoning": "found it"}
    if tool == "ClauseAssessment":
        return {"compliant": True, "issues": [], "rationale": "meets the rule"}
    return dict(SUGGESTION)
