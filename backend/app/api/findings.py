from fastapi import APIRouter, HTTPException

from app import services
from app.api.contracts import Svc
from app.api.schemas import DecisionIn, DecisionView

router = APIRouter(prefix="/api/findings")


@router.put("/{finding_id}/decision", response_model=DecisionView)
def put_decision(
    finding_id: str, body: DecisionIn, svc: Svc
):
    try:
        decision = services.set_decision(svc, finding_id, body.state, body.edited_text)
    except services.FindingNotFound:
        raise HTTPException(404, "Finding not found") from None
    except services.NoSuggestion:
        raise HTTPException(422, "Finding has no suggested wording") from None
    return DecisionView(
        state=decision.state, edited_text=decision.edited_text, decided_at=decision.decided_at
    )
