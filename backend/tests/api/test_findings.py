import pytest


def findings_by_status(client, run_id):
    body = client.get(f"/api/runs/{run_id}").json()
    return {f["clause_id"]: f for f in body["findings"]}


@pytest.fixture
def risky_run(client, script, contract_id):
    script[("ClauseAssessment", "governing_law")] = {
        "compliant": False,
        "issues": ["x"],
        "rationale": "r",
    }
    return client.post(f"/api/contracts/{contract_id}/analyze").json()["run_id"]


def test_decision_persists_across_requests(client, risky_run):
    finding = findings_by_status(client, risky_run)["governing_law"]
    assert finding["decision"]["state"] == "pending"
    response = client.put(
        f"/api/findings/{finding['id']}/decision",
        json={"state": "edited", "edited_text": "My wording."},
    )
    assert response.status_code == 200
    reloaded = findings_by_status(client, risky_run)["governing_law"]
    assert reloaded["decision"]["state"] == "edited"
    assert reloaded["decision"]["edited_text"] == "My wording."

    client.put(
        f"/api/findings/{finding['id']}/decision",
        json={"state": "rejected", "edited_text": "ignored"},
    )
    reloaded = findings_by_status(client, risky_run)["governing_law"]
    assert reloaded["decision"] == {**reloaded["decision"], "state": "rejected", "edited_text": None}


def test_decision_edited_requires_text(client, risky_run):
    finding = findings_by_status(client, risky_run)["governing_law"]
    for body in ({"state": "edited"}, {"state": "edited", "edited_text": "  "}):
        response = client.put(f"/api/findings/{finding['id']}/decision", json=body)
        assert response.status_code == 422


def test_decision_rejects_pending_state(client, risky_run):
    finding = findings_by_status(client, risky_run)["governing_law"]
    response = client.put(f"/api/findings/{finding['id']}/decision", json={"state": "pending"})
    assert response.status_code == 422


def test_decision_on_finding_without_suggestion_422(client, risky_run):
    ok_finding = findings_by_status(client, risky_run)["cap_on_liability"]
    assert ok_finding["status"] == "ok"
    assert ok_finding["decision"] is None
    response = client.put(f"/api/findings/{ok_finding['id']}/decision", json={"state": "accepted"})
    assert response.status_code == 422


def test_decision_unknown_finding_404(client):
    assert client.put("/api/findings/nope/decision", json={"state": "accepted"}).status_code == 404
