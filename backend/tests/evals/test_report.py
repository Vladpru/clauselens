from evals.metrics import ClauseOutcome
from evals.report import render_report

OUTCOME = ClauseOutcome(
    title="t1", label="Governing Law", gold_present=True, status="ok", quote="a b c d e",
    gold_spans=("a b c d e",), verify_failures=0, error=None, candidate_pages=[1], gold_pages=[1],
)
HEADINGS = [
    "## Config", "## Sample", "## Presence", "## Span match", "## Verification rejection",
    "## Uncertain and errors", "## Retrieval hit rate", "## Cost", "## Excluded and gaps",
]


def render(**overrides):
    args = {
        "config": {
            "model": "vendor/model:free",
            "seed": 42,
            "n": 1,
            "playbook_hash": "abc123def456",
            "git_commit": "deadbee-dirty",
            "date": "2026-11-23",
        },
        "sample": ["t1"],
        "excluded": [("big", "too many pages")],
        "gaps": ["Non-Compete: no absent contract"],
        "outcomes": [OUTCOME],
        "cost": {"llm_calls": {"t1": 7}, "seconds": {"t1": 12.5}},
    }
    args.update(overrides)
    return render_report(**args)


def test_report_has_all_sections():
    report = render()
    for heading in HEADINGS:
        assert heading in report
    assert "vendor/model:free" in report
    assert "abc123def456" in report
    assert "deadbee-dirty" in report


def test_report_lists_sample_exclusions_gaps_and_cost():
    report = render()
    assert "t1" in report
    assert "big" in report and "too many pages" in report
    assert "Non-Compete: no absent contract" in report
    assert "7" in report and "12.5" in report


def test_report_shows_na_for_undefined_metrics():
    absent = ClauseOutcome(
        title="t2", label="Non-Compete", gold_present=False, status="ok", quote=None,
        gold_spans=(), verify_failures=0, error=None, candidate_pages=[], gold_pages=[],
    )
    report = render(outcomes=[absent])
    assert "n/a" in report
