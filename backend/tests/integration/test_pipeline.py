import shutil

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.graph.review_graph import run_config
from app.main import create_app
from app.services import build_services, contract_dir
from tests.fakes import ScriptedChatModel, clause_of
from tests.scripted import PAGES, default_reply

pytestmark = pytest.mark.integration


def test_full_run_on_real_infra(make_pdf):
    settings = get_settings()
    svc = build_services(settings)
    svc.model = ScriptedChatModel(
        responder=lambda tool, messages: default_reply(tool, clause_of(messages))
    )
    contract_id = None
    try:
        with TestClient(create_app(svc)) as client:
            upload = client.post(
                "/api/contracts", files={"file": ("c.pdf", make_pdf(PAGES), "application/pdf")}
            )
            assert upload.status_code == 200, upload.text
            contract_id = upload.json()["contract_id"]
            run_id = client.post(f"/api/contracts/{contract_id}/analyze").json()["run_id"]
            body = client.get(f"/api/runs/{run_id}").json()
            assert body["status"] in {"completed", "completed_with_errors"}
            assert len(body["findings"]) == 5
            checkpoint = svc.checkpointer.get_tuple(run_config(run_id, 2))
            assert checkpoint is not None
    finally:
        if contract_id is not None:
            svc.index.delete_contract(contract_id)
            shutil.rmtree(contract_dir(settings, contract_id), ignore_errors=True)
        if svc.close is not None:
            svc.close()
