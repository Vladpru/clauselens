from fastapi import APIRouter, HTTPException

from app import services
from app.api.contracts import Svc
from app.api.schemas import RunView

router = APIRouter(prefix="/api/runs")


@router.get("/{run_id}", response_model=RunView)
def get_run(run_id: str, svc: Svc):
    view = services.get_run_view(svc, run_id)
    if view is None:
        raise HTTPException(404, "Run not found")
    return view
