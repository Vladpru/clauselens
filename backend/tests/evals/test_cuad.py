from pathlib import Path

import pytest

from evals.cuad import index_pdfs, load_gold, match_pdfs

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cuad_mini.json"
LABELS = ["Governing Law", "Non-Compete", "Cap On Liability", "Anti-Assignment", "Termination For Convenience"]


@pytest.fixture(scope="module")
def gold():
    return load_gold(FIXTURE, LABELS)


def test_present_when_non_empty_answer(gold):
    g = gold["ALPHA_AGREEMENT"]["Governing Law"]
    assert g.present is True
    assert g.spans == ("This Agreement is governed by the laws of Delaware.",)


def test_absent_when_no_answers(gold):
    g = gold["BETA_AGREEMENT"]["Governing Law"]
    assert g.present is False
    assert g.spans == ()


def test_whitespace_only_answer_is_absent(gold):
    assert gold["ALPHA_AGREEMENT"]["Cap On Liability"].present is False


def test_multiple_spans_kept_in_order(gold):
    assert gold["ALPHA_AGREEMENT"]["Anti-Assignment"].spans == (
        "Neither party may assign this Agreement.",
        "Any attempted assignment is void.",
    )


def test_missing_qa_entry_counts_as_absent(gold):
    assert gold["ALPHA_AGREEMENT"]["Termination For Convenience"].present is False


def test_unknown_label_raises():
    with pytest.raises(ValueError, match="Governing law"):
        load_gold(FIXTURE, ["Governing Law", "Governing law"])


def test_only_requested_labels_returned():
    result = load_gold(FIXTURE, ["Governing Law"])
    assert set(result["ALPHA_AGREEMENT"]) == {"Governing Law"}


def test_index_pdfs_finds_nested_and_uppercase_suffix(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b" / "c").mkdir(parents=True)
    (tmp_path / "a" / "X.pdf").touch()
    (tmp_path / "b" / "c" / "Y.PDF").touch()
    assert set(index_pdfs(tmp_path)) == {"X", "Y"}


def test_index_pdfs_duplicate_stem_raises(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "X.pdf").touch()
    (tmp_path / "b" / "X.pdf").touch()
    with pytest.raises(ValueError):
        index_pdfs(tmp_path)


def test_match_pdfs_reports_unmatched(tmp_path):
    path = tmp_path / "X.pdf"
    assert match_pdfs(["X", "Z"], {"X": path}) == ({"X": path}, ["Z"])


def test_match_pdfs_ignores_whitespace_and_unicode_form():
    p1, p2 = Path("a.pdf"), Path("b.pdf")
    index = {"Foo Agreement ": p1, "LECLANCHÉ S.A.": p2}
    matched, unmatched = match_pdfs(["Foo Agreement", "LECLANCHÉ S.A."], index)
    assert matched == {"Foo Agreement": p1, "LECLANCHÉ S.A.": p2}
    assert unmatched == []


def test_match_pdfs_unique_prefix_fallback_both_directions(caplog):
    longer, shorter = Path("long.pdf"), Path("short.pdf")
    index = {"Dev Agreement_Option Agreement": longer, "Netgear Amendment-": shorter}
    with caplog.at_level("INFO", logger="evals.cuad"):
        matched, unmatched = match_pdfs(["Dev Agreement", "Netgear Amendment"], index)
    assert matched == {"Dev Agreement": longer, "Netgear Amendment": shorter}
    assert unmatched == []
    assert "Dev Agreement" in caplog.text


def test_match_pdfs_ambiguous_prefix_stays_unmatched():
    index = {"Foo Agreement A": Path("a.pdf"), "Foo Agreement B": Path("b.pdf")}
    assert match_pdfs(["Foo Agreement"], index) == ({}, ["Foo Agreement"])


def test_match_pdfs_exact_match_beats_prefix():
    exact, other = Path("exact.pdf"), Path("other.pdf")
    index = {"Foo": exact, "Foo Bar": other}
    assert match_pdfs(["Foo"], index) == ({"Foo": exact}, [])


def test_match_pdfs_prefix_never_steals_pdf_claimed_by_exact_title():
    base, amendment = Path("base.pdf"), Path("amend.pdf")
    index = {"Foo-Amendment": amendment}
    # "Foo" is a strict prefix of the amendment stem, but "Foo-Amendment" is its exact owner
    matched, unmatched = match_pdfs(["Foo", "Foo-Amendment"], index)
    assert matched == {"Foo-Amendment": amendment}
    assert unmatched == ["Foo"]
    assert base not in matched.values()


def test_match_pdfs_two_titles_never_share_one_pdf_by_prefix():
    index = {"Foo Agreement Final": Path("a.pdf")}
    matched, unmatched = match_pdfs(["Foo Agreement", "Foo Agreement F"], index)
    assert matched == {}
    assert sorted(unmatched) == ["Foo Agreement", "Foo Agreement F"]


def test_match_pdfs_empty_title_is_unmatched():
    assert match_pdfs([""], {"Only": Path("o.pdf")}) == ({}, [""])
