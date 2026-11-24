from sqlmodel import select

from app.models import Run, RunStatus


def test_analyze_unknown_contract_404(client):
    assert client.post("/api/contracts/unknown/analyze").status_code == 404


def test_analyze_then_run_completed_with_five_findings(client, run_id):
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["status"] == "completed"
    assert len(body["findings"]) == 5
    assert {f["clause_id"] for f in body["findings"]} == {
        "governing_law",
        "termination_for_convenience",
        "cap_on_liability",
        "non_compete",
        "anti_assignment",
    }
    assert len(body["progress"]) == 5
    assert set(body["progress"].values()) == {"done"}
    assert body["model"] == "vendor/model:free"
    assert body["started_at"] and body["finished_at"]


def test_run_with_llm_error_is_completed_with_errors(client, script, contract_id):
    script[("ClauseExtraction", "cap_on_liability")] = lambda messages: TimeoutError("slow")
    run_id = client.post(f"/api/contracts/{contract_id}/analyze").json()["run_id"]
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["status"] == "completed_with_errors"
    by_clause = {f["clause_id"]: f for f in body["findings"]}
    assert by_clause["cap_on_liability"]["status"] == "uncertain"
    assert "TimeoutError" in by_clause["cap_on_liability"]["error"]


def test_run_view_titles_findings_and_orders_by_playbook(client, run_id):
    findings = client.get(f"/api/runs/{run_id}").json()["findings"]
    assert findings[0]["clause_id"] == "governing_law"
    assert findings[0]["clause_title"] == "Governing law"
    assert findings[0]["playbook_rule"]


def test_unreadable_contract_fails_run(client, services, contract_id):
    (services.settings.data_dir / "contracts" / contract_id / "pages.json").unlink()
    run_id = client.post(f"/api/contracts/{contract_id}/analyze").json()["run_id"]
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["status"] == "failed"
    assert body["findings"] == []


def test_unknown_run_404(client):
    assert client.get("/api/runs/unknown").status_code == 404


def test_stale_runs_failed_on_startup(services):
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.main import create_app

    with Session(services.engine) as session:
        session.add(Run(contract_id="c", status=RunStatus.RUNNING, model="m", playbook_hash="h"))
        session.commit()
    with TestClient(create_app(services)):
        pass
    with Session(services.engine) as session:
        assert session.exec(select(Run)).one().status == "failed"



def test_execute_run_passes_callbacks_to_the_graph(services, contract_id):
    from langchain_core.callbacks import BaseCallbackHandler

    from app.services import create_run, execute_run

    class Counter(BaseCallbackHandler):
        count = 0

        def on_chat_model_start(self, serialized, messages, **kwargs):
            Counter.count += 1

    run = create_run(services, contract_id)
    execute_run(services, run.id, callbacks=[Counter()])
    assert Counter.count >= 5


def test_execute_run_tags_and_annotates_the_trace(services, contract_id):
    from langchain_core.callbacks import BaseCallbackHandler

    from app.services import create_run, execute_run

    seen = []

    class Capture(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, messages, *, tags=None, metadata=None, **kwargs):
            seen.append((tags, metadata))

    run = create_run(services, contract_id)
    execute_run(services, run.id, callbacks=[Capture()], tags=["eval"])

    assert seen
    for tags, metadata in seen:
        assert {"clauselens", "eval"} <= set(tags)
        assert metadata["run_id"] == run.id
        assert metadata["contract_id"] == contract_id
        assert metadata["playbook_hash"] == services.playbook_hash
        assert metadata["model"] == "vendor/model:free"
