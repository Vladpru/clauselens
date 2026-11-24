from pathlib import Path

from app.ingest.pdf import MAX_PAGES
from evals.cuad import TARGET_LABELS, GoldLabel
from evals.sample import EvalContract, eligible_contracts, sample_contracts

LABELS = list(TARGET_LABELS)
TEXT = "The parties agree to the schedules and the payment terms of this agreement. " * 4


def make_gold(titles, present_for):
    return {
        title: {
            label: GoldLabel(title, label, present_for(i, j), ("span",) if present_for(i, j) else ())
            for j, label in enumerate(LABELS)
        }
        for i, title in enumerate(titles)
    }


def synthetic(n_contracts=12, present_for=lambda i, j: (i + j) % 2 == 0):
    titles = [f"contract_{i:02d}" for i in range(n_contracts)]
    gold = make_gold(titles, present_for)
    eligible = [EvalContract(t, Path(f"/x/{t}.pdf"), 5) for t in titles]
    return eligible, gold


def titles_of(sample):
    return [c.title for c in sample]


def test_sample_is_deterministic():
    eligible, gold = synthetic()
    first, _ = sample_contracts(eligible, gold, LABELS, 4, seed=42)
    second, _ = sample_contracts(eligible, gold, LABELS, 4, seed=42)
    other, _ = sample_contracts(eligible, gold, LABELS, 4, seed=7)
    assert titles_of(first) == titles_of(second)
    assert len(first) == 4
    assert titles_of(first) != titles_of(other)


def test_sample_ignores_input_order():
    eligible, gold = synthetic()
    forward, _ = sample_contracts(eligible, gold, LABELS, 4, seed=1)
    backward, _ = sample_contracts(list(reversed(eligible)), gold, LABELS, 4, seed=1)
    assert titles_of(forward) == titles_of(backward)


def test_sample_covers_present_and_absent_when_possible():
    eligible, gold = synthetic()
    sample, gaps = sample_contracts(eligible, gold, LABELS, 4, seed=3)
    assert gaps == []
    for label in LABELS:
        presence = {gold[c.title][label].present for c in sample}
        assert presence == {True, False}, label


def test_sample_reports_gaps_when_impossible():
    eligible, gold = synthetic(present_for=lambda i, j: True)
    sample, gaps = sample_contracts(eligible, gold, LABELS, 4, seed=3)
    assert len(sample) == 4
    assert any(LABELS[3] in gap and "absent" in gap for gap in gaps)


def test_sample_reports_gap_when_n_too_small():
    eligible, gold = synthetic()
    sample, gaps = sample_contracts(eligible, gold, LABELS, 1, seed=3)
    assert len(sample) == 1
    assert gaps


def test_sample_smaller_than_n_when_few_contracts():
    eligible, gold = synthetic(n_contracts=3)
    sample, _ = sample_contracts(eligible, gold, LABELS, 10, seed=3)
    assert len(sample) == 3


def test_sampler_excludes_oversized_contracts(tmp_path, make_pdf):
    good = tmp_path / "good.pdf"
    good.write_bytes(make_pdf([TEXT] * 3))
    big = tmp_path / "big.pdf"
    big.write_bytes(make_pdf([TEXT] * (MAX_PAGES + 1)))
    scanned = tmp_path / "scanned.pdf"
    scanned.write_bytes(make_pdf(["", ""], blank=True))
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7 garbage")
    gold = make_gold(["good", "big", "scanned", "broken"], lambda i, j: True)
    matched = {"good": good, "big": big, "scanned": scanned, "broken": broken}

    eligible, excluded = eligible_contracts(gold, matched)

    assert [(c.title, c.page_count) for c in eligible] == [("good", 3)]
    assert dict(excluded) == {
        "big": "too many pages",
        "scanned": "no text layer",
        "broken": "unreadable",
    }
    sample, _ = sample_contracts(eligible, gold, LABELS, 4, seed=1)
    assert "big" not in titles_of(sample)


def test_eligible_excludes_titles_without_pdf(tmp_path, make_pdf):
    good = tmp_path / "good.pdf"
    good.write_bytes(make_pdf([TEXT]))
    gold = make_gold(["good", "ghost"], lambda i, j: True)
    eligible, excluded = eligible_contracts(gold, {"good": good})
    assert [c.title for c in eligible] == ["good"]
    assert excluded == [("ghost", "no matching pdf")]
