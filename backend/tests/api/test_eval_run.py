from pathlib import Path

from sqlmodel import select

from app.models import Run
from evals.cuad import GoldLabel
from evals.run import CallCounter, evaluate
from evals.sample import EvalContract
from tests.scripted import PAGES, QUOTES


def gold_for(title: str) -> dict[str, GoldLabel]:
    labels = {
        "Governing Law": (QUOTES["governing_law"][1],),
        "Termination For Convenience": (QUOTES["termination_for_convenience"][1],),
        "Cap On Liability": (QUOTES["cap_on_liability"][1],),
        "Non-Compete": (),
        "Anti-Assignment": (QUOTES["anti_assignment"][1],),
    }
    return {label: GoldLabel(title, label, bool(spans), spans) for label, spans in labels.items()}


def test_evaluate_runs_the_real_service_path(services, db, make_pdf, tmp_path):
    pdf = tmp_path / "t1.pdf"
    pdf.write_bytes(make_pdf(PAGES))
    contract = EvalContract("t1", Path(pdf), len(PAGES))

    outcomes, cost = evaluate(services, [contract], {"t1": gold_for("t1")})

    assert len(outcomes) == 5
    by_label = {o.label: o for o in outcomes}
    governing = by_label["Governing Law"]
    assert governing.found and governing.gold_present
    assert governing.gold_pages == [2]
    assert governing.candidate_pages
    assert not by_label["Non-Compete"].found
    assert by_label["Non-Compete"].gold_pages == []
    assert cost["llm_calls"]["t1"] >= 5
    assert cost["seconds"]["t1"] >= 0
    assert db.exec(select(Run)).one().status == "completed"


def test_failed_run_yields_uncertain_outcomes(services, make_pdf, tmp_path, monkeypatch):
    pdf = tmp_path / "t1.pdf"
    pdf.write_bytes(make_pdf(PAGES))
    contract = EvalContract("t1", pdf, len(PAGES))

    def boom(*args, **kwargs):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr("app.services.build_review_graph", boom)
    outcomes, _ = evaluate(services, [contract], {"t1": gold_for("t1")})

    assert len(outcomes) == 5
    assert {o.status for o in outcomes} == {"uncertain"}
    assert all(o.error == "run failed" and not o.found for o in outcomes)


def test_call_counter_counts_chat_model_starts():
    counter = CallCounter()
    counter.on_chat_model_start({}, [[]])
    counter.on_chat_model_start({}, [[]])
    assert counter.count == 2


def test_daily_limit_aborts_the_eval_without_a_report(services, make_pdf, tmp_path, script):
    import pytest

    from evals.run import DailyLimitReached

    pdf = tmp_path / "t1.pdf"
    pdf.write_bytes(make_pdf(PAGES))
    script[("ClauseExtraction", "governing_law")] = lambda messages: TimeoutError(
        "Rate limit exceeded: free-models-per-day"
    )
    with pytest.raises(DailyLimitReached) as exc:
        evaluate(services, [EvalContract("t1", pdf, len(PAGES))], {"t1": gold_for("t1")})
    assert exc.value.title == "t1"
    assert exc.value.finished == 0
