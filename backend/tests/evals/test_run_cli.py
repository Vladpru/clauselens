import json

from evals import run as eval_run
from evals.cuad import TARGET_LABELS

TEXT = "The parties agree to the schedules and the payment terms of this agreement. " * 4


def write_cuad(root, titles, make_pdf):
    data = []
    for i, title in enumerate(titles):
        qas = []
        for j, label in enumerate(TARGET_LABELS):
            answers = [{"text": f"span {title} {label}", "answer_start": 0}] if (i + j) % 2 == 0 else []
            qas.append({"id": f"{title}__{label}", "question": label, "answers": answers, "is_impossible": not answers})
        data.append({"title": title, "paragraphs": [{"qas": qas, "context": ""}]})
    root.mkdir(parents=True, exist_ok=True)
    (root / "CUAD_v1.json").write_text(json.dumps({"version": "t", "data": data}))
    for title in titles:
        (root / f"{title}.pdf").write_bytes(make_pdf([TEXT] * 2))


def test_sample_only_is_deterministic_and_offline(tmp_path, make_pdf, monkeypatch, capsys):
    titles = [f"contract_{i:02d}" for i in range(8)]
    write_cuad(tmp_path / "cuad", titles, make_pdf)

    def forbidden(*args, **kwargs):
        raise AssertionError("services must not be built for --sample-only")

    monkeypatch.setattr(eval_run, "build_services", forbidden)
    argv = ["--sample-only", "--n", "3", "--seed", "1", "--cuad", str(tmp_path / "cuad")]

    assert eval_run.main(argv) == 0
    first = capsys.readouterr().out
    assert eval_run.main(argv) == 0
    second = capsys.readouterr().out

    assert first == second
    assert sum(title in first for title in titles) >= 3
    assert "excluded" in first.lower()


def test_sample_only_reports_excluded_contracts(tmp_path, make_pdf, capsys):
    titles = [f"contract_{i:02d}" for i in range(4)]
    write_cuad(tmp_path / "cuad", titles, make_pdf)
    (tmp_path / "cuad" / "contract_00.pdf").write_bytes(b"not a pdf")
    eval_run.main(["--sample-only", "--n", "4", "--seed", "1", "--cuad", str(tmp_path / "cuad")])
    out = capsys.readouterr().out
    assert "Excluded: 1" in out
    assert "contract_00: unreadable" in out


def test_git_commit_label_marks_dirty(monkeypatch):
    calls = iter(["abc1234\n", " M file\n"])
    monkeypatch.setattr(eval_run, "_git", lambda *args: next(calls))
    assert eval_run.git_commit() == "abc1234-dirty"
    calls = iter(["abc1234\n", ""])
    assert eval_run.git_commit() == "abc1234"


def test_arguments_have_documented_defaults():
    args = eval_run.parse_args([])
    assert (args.n, args.seed, args.sample_only) == (10, 42, False)


def test_main_returns_2_and_writes_no_report_when_daily_limit_reached(tmp_path, make_pdf, monkeypatch, capsys):
    titles = [f"contract_{i:02d}" for i in range(4)]
    write_cuad(tmp_path / "cuad", titles, make_pdf)
    monkeypatch.setattr(eval_run, "RESULTS_DIR", tmp_path / "results")

    class FakeSettings:
        openrouter_model = "m"

    class FakeServices:
        close = None

    def limit(svc, sample, gold):
        raise eval_run.DailyLimitReached("contract_01", 3)

    monkeypatch.setattr(eval_run, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(eval_run, "build_services", lambda settings: FakeServices())
    monkeypatch.setattr(eval_run, "evaluate", limit)

    assert eval_run.main(["--n", "4", "--seed", "1", "--cuad", str(tmp_path / "cuad")]) == 2
    out = capsys.readouterr().out
    assert "daily" in out.lower() and "contract_01" in out and "3" in out
    assert not (tmp_path / "results").exists()
