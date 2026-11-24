from app.graph.nodes import report_step
from app.graph.state import ClauseState, GraphDeps


def retrieve(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "retrieve")
    rule = deps.playbook.clause(state["clause_id"])
    query = " ".join(rule.query_terms)
    return {"candidates": deps.retriever.search(state["contract_id"], query, deps.top_k)}
