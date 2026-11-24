from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.ingest.index import Candidate
from app.playbook import ClauseRule


def _rule_text(rule: ClauseRule) -> str:
    return (
        f"Clause: {rule.title}\n"
        f"Requirement: {rule.requirement}\n"
        f"Acceptable: {'; '.join(rule.acceptable)}\n"
        f"Red flags: {'; '.join(rule.red_flags)}\n"
        f"Preferred wording: {rule.preferred_wording}"
    )


def extract_messages(
    rule: ClauseRule, candidates: list[Candidate], feedback: str | None
) -> list[BaseMessage]:
    passages = "\n\n".join(f"[page {c.page}] {c.text}" for c in candidates)
    system = (
        f"clause_id={rule.id}\n"
        "You are a contract analyst. Decide whether the passages contain the clause "
        f"'{rule.title}'. If they do, copy the clause text exactly, word for word, from one "
        "passage into `quote`. Never paraphrase, never join text from different passages, "
        "and never add words. If the clause is not in the passages, set found=false and "
        "quote=null. Answer only by calling the tool."
    )
    human = f"Passages:\n\n{passages}"
    messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(human)]
    if feedback:
        messages.append(HumanMessage(feedback))
    return messages


def assess_messages(rule: ClauseRule, stance: str, quote: str) -> list[BaseMessage]:
    system = (
        f"clause_id={rule.id}\n"
        f"{stance} Compare the quoted clause with the playbook rule. Set compliant=true only if "
        "the clause meets the requirement and has no red flag. List each problem in `issues`. "
        "Answer only by calling the tool."
    )
    return [
        SystemMessage(system),
        HumanMessage(f"Playbook rule:\n{_rule_text(rule)}\n\nQuoted clause:\n{quote}"),
    ]


def suggest_messages(rule: ClauseRule, stance: str, quote: str | None) -> list[BaseMessage]:
    system = (
        f"clause_id={rule.id}\n"
        f"{stance} Draft safer contract wording for this clause, based on the playbook's "
        "preferred wording. Put the wording in `text` and a short reason in `explanation`. "
        "Answer only by calling the tool."
    )
    situation = (
        f"Current clause:\n{quote}" if quote else "The contract has no such clause. Draft one."
    )
    return [
        SystemMessage(system),
        HumanMessage(f"Playbook rule:\n{_rule_text(rule)}\n\n{situation}"),
    ]
