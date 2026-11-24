import pytest

from evals.metrics import (
    SPAN_MATCH_F1,
    ClauseOutcome,
    error_rate,
    gold_pages,
    presence_prf,
    retrieval_hit_rate,
    span_match_rate,
    uncertain_rate,
    verification_rejection_rate,
)

LABEL = "Governing Law"


def outcome(title="t", *, present=True, status="ok", quote="a b c d e", spans=("a b c d e",),
            verify_failures=0, error=None, candidate_pages=(1,), gold_pages=(1,), label=LABEL):
    return ClauseOutcome(
        title=title, label=label, gold_present=present, status=status, quote=quote,
        gold_spans=tuple(spans), verify_failures=verify_failures, error=error,
        candidate_pages=list(candidate_pages), gold_pages=list(gold_pages),
    )


def test_presence_prf_counts():
    outcomes = [
        outcome("tp1"),
        outcome("tp2", status="risky"),
        outcome("fp", present=False),
        outcome("fn", quote=None, status="missing"),
        outcome("tn", present=False, quote=None),
    ]
    p, r, f1, tp, fp, fn = presence_prf(outcomes, LABEL)
    assert (tp, fp, fn) == (2, 1, 1)
    assert p == pytest.approx(2 / 3)
    assert r == pytest.approx(2 / 3)
    assert f1 == pytest.approx(2 / 3)


def test_presence_prf_filters_by_label():
    outcomes = [outcome(), outcome(label="Non-Compete", present=False)]
    assert presence_prf(outcomes, LABEL)[3:] == (1, 0, 0)


def test_ok_without_quote_counts_as_not_found():
    p, r, f1, tp, fp, fn = presence_prf([outcome(status="ok", quote=None)], LABEL)
    assert (tp, fp, fn) == (0, 0, 1)
    assert p is None
    assert r == 0.0
    assert f1 is None


def test_uncertain_with_quote_is_not_found():
    _, _, _, tp, _, fn = presence_prf([outcome(status="uncertain", quote="x y z a b")], LABEL)
    assert (tp, fn) == (0, 1)


def test_presence_prf_without_positives_is_not_available():
    p, r, f1, tp, fp, fn = presence_prf([outcome(present=False, quote=None)], LABEL)
    assert (p, r, f1) == (None, None, None)
    assert (tp, fp, fn) == (0, 0, 0)


def test_span_match_threshold():
    assert SPAN_MATCH_F1 == 0.5
    exactly = outcome(quote="a b", spans=("a c",))
    below = outcome(quote="a b c", spans=("a d e",))
    assert span_match_rate([exactly], LABEL) == 1.0
    assert span_match_rate([below], LABEL) == 0.0


def test_span_match_uses_best_span_and_only_true_positives():
    hit = outcome("hit", quote="a b c d", spans=("x y", "a b c d"))
    miss = outcome("miss", quote="a b c d", spans=("w x y z",))
    fp = outcome("fp", present=False, quote="a b c d", spans=())
    assert span_match_rate([hit, miss, fp], LABEL) == 0.5
    assert span_match_rate([fp], LABEL) is None


def test_verification_rejection_rate():
    outcomes = [
        outcome("clean"),
        outcome("retried", verify_failures=1),
        outcome("failed", status="uncertain", quote=None, verify_failures=2),
        outcome("none", status="ok", quote=None),
    ]
    assert verification_rejection_rate(outcomes) == pytest.approx(2 / 3)
    assert verification_rejection_rate([outcome("none", quote=None)]) is None


def test_uncertain_and_error_rates():
    outcomes = [
        outcome(),
        outcome(status="uncertain", quote=None, error="TimeoutError: x"),
        outcome(status="uncertain", quote=None, verify_failures=2),
        outcome(),
    ]
    assert uncertain_rate(outcomes) == 0.5
    assert error_rate(outcomes) == 0.25


def test_retrieval_hit_rate():
    outcomes = [
        outcome("hit", candidate_pages=(2, 5), gold_pages=(5,)),
        outcome("miss", candidate_pages=(2, 3), gold_pages=(9,)),
        outcome("absent", present=False, candidate_pages=(1,), gold_pages=()),
    ]
    assert retrieval_hit_rate(outcomes, LABEL) == 0.5
    assert retrieval_hit_rate([outcomes[2]], LABEL) is None


def test_gold_pages_finds_normalized_spans():
    pages = ["intro", "This  Agreement is\ngoverned by the laws of Delaware.", "other"]
    spans = ("this agreement is governed by the laws of delaware.",)
    assert gold_pages(pages, spans) == [2]
    assert gold_pages(pages, ("nowhere to be found",)) == []
