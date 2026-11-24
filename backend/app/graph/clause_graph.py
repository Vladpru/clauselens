from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.assess import assess
from app.graph.nodes.emit import emit
from app.graph.nodes.extract import extract
from app.graph.nodes.locate import locate
from app.graph.nodes.retrieve import retrieve
from app.graph.nodes.suggest import suggest
from app.graph.nodes.verify import verify
from app.graph.state import ClauseOutput, ClauseState, GraphDeps

MAX_VERIFY_FAILURES = 2


def build_clause_graph(deps: GraphDeps) -> CompiledStateGraph:
    def after_extract(state: ClauseState) -> str:
        if state.get("error"):
            return "emit"
        extraction = state["extraction"]
        if extraction.found:
            return "verify"
        rule = deps.playbook.clause(state["clause_id"])
        return "suggest" if rule.absence_is == "missing" else "emit"

    def after_verify(state: ClauseState) -> str:
        if state.get("page") is not None:
            return "locate"
        if state.get("verify_failures", 0) < MAX_VERIFY_FAILURES:
            return "extract"
        return "emit"

    def after_assess(state: ClauseState) -> str:
        if state.get("error") or state["assessment"].compliant:
            return "emit"
        return "suggest"

    graph = StateGraph(ClauseState, output_schema=ClauseOutput)
    for name, node in [
        ("retrieve", retrieve),
        ("extract", extract),
        ("verify", verify),
        ("locate", locate),
        ("assess", assess),
        ("suggest", suggest),
        ("emit", emit),
    ]:
        graph.add_node(name, partial(node, deps=deps))
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "extract")
    graph.add_conditional_edges("extract", after_extract, ["verify", "suggest", "emit"])
    graph.add_conditional_edges("verify", after_verify, ["locate", "extract", "emit"])
    graph.add_edge("locate", "assess")
    graph.add_conditional_edges("assess", after_assess, ["suggest", "emit"])
    graph.add_edge("suggest", "emit")
    graph.add_edge("emit", END)
    return graph.compile()
