from app.graph.nodes import report_step
from app.graph.state import ClauseState, GraphDeps
from app.ingest.pdf import find_quote_rects


def locate(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "locate")
    pdf_path = deps.contract_dir(state["contract_id"]) / "original.pdf"
    try:
        bboxes = find_quote_rects(pdf_path, state["page"], state["extraction"].quote)
    except (RuntimeError, OSError):
        bboxes = []
    return {"bboxes": bboxes}
