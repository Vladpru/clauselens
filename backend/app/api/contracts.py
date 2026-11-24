from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse

from app import services
from app.api.schemas import AnalyzeResponse, UploadResponse
from app.ingest.pdf import MAX_BYTES, PdfRejected
from app.models import Contract

router = APIRouter(prefix="/api/contracts")


def get_services(request: Request) -> services.Services:
    return request.app.state.services


Svc = Annotated[services.Services, Depends(get_services)]


@router.post("", response_model=UploadResponse)
def upload_contract(file: UploadFile, svc: Svc):
    data = file.file.read(MAX_BYTES + 1)
    try:
        contract = services.ingest_contract(svc, file.filename or "contract.pdf", data)
    except PdfRejected as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return UploadResponse(contract_id=contract.id, page_count=contract.page_count)


@router.get("/{contract_id}/pdf")
def get_pdf(contract_id: str, svc: Svc):
    with svc.session() as session:
        contract = session.get(Contract, contract_id)
    if contract is None or not Path(contract.path).is_file():
        raise HTTPException(404, "Contract not found")
    return FileResponse(contract.path, media_type="application/pdf")


@router.post("/{contract_id}/analyze", status_code=202, response_model=AnalyzeResponse)
def analyze(
    contract_id: str,
    background: BackgroundTasks,
    svc: Svc,
):
    try:
        run = services.create_run(svc, contract_id)
    except LookupError:
        raise HTTPException(404, "Contract not found") from None
    background.add_task(services.execute_run, svc, run.id)
    return AnalyzeResponse(run_id=run.id)
