import argparse
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

from app.config import REPO_ROOT, get_settings
from app.ingest.pdf import load_pages
from app.playbook import playbook_hash
from app.services import (
    Services,
    build_services,
    contract_dir,
    create_run,
    execute_run,
    get_run_view,
    ingest_contract,
)
from evals.cuad import TARGET_LABELS, GoldLabel, index_pdfs, load_gold, match_pdfs
from evals.metrics import ClauseOutcome, gold_pages
from evals.report import render_report
from evals.sample import EvalContract, eligible_contracts, sample_contracts

RESULTS_DIR = REPO_ROOT / "backend" / "evals" / "results"
DEFAULT_CUAD_DIR = REPO_ROOT / "data" / "cuad"


DAILY_LIMIT_MARKER = "free-models-per-day"


class DailyLimitReached(Exception):
    """The free-tier daily request cap stopped the eval; finished contracts stay in the LLM cache."""

    def __init__(self, title: str, finished: int) -> None:
        super().__init__(f"daily free-model limit reached at {title!r} after {finished} contracts")
        self.title = title
        self.finished = finished


class CallCounter(BaseCallbackHandler):
    """Counts chat model calls, including retries and cache hits."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.count = 0

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        with self._lock:
            self.count += 1


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__)
    parser.add_argument("--n", type=int, default=10, help="number of contracts to sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cuad", type=Path, default=DEFAULT_CUAD_DIR, help="CUAD folder")
    parser.add_argument(
        "--sample-only", action="store_true", help="print the sample and exit, no LLM calls"
    )
    return parser.parse_args(argv)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def git_commit() -> str:
    commit = _git("rev-parse", "--short", "HEAD").strip() or "unknown"
    return f"{commit}-dirty" if _git("status", "--porcelain").strip() else commit


def _outcomes_for_contract(
    svc: Services, contract: EvalContract, gold: Mapping[str, GoldLabel], contract_id: str, run_id: str
) -> list[ClauseOutcome]:
    view = get_run_view(svc, run_id)
    findings = view.findings if view else []
    if not findings:
        return [
            ClauseOutcome(
                title=contract.title,
                label=rule.cuad_label,
                gold_present=gold[rule.cuad_label].present,
                status="uncertain",
                quote=None,
                gold_spans=gold[rule.cuad_label].spans,
                verify_failures=0,
                error="run failed",
                candidate_pages=[],
                gold_pages=[],
            )
            for rule in svc.playbook.clauses
        ]
    pages = load_pages(contract_dir(svc.settings, contract_id))
    outcomes = []
    for finding in findings:
        label = svc.playbook.clause(finding.clause_id).cuad_label
        label_gold = gold[label]
        outcomes.append(
            ClauseOutcome(
                title=contract.title,
                label=label,
                gold_present=label_gold.present,
                status=finding.status,
                quote=finding.quote,
                gold_spans=label_gold.spans,
                verify_failures=finding.verify_failures,
                error=finding.error,
                candidate_pages=sorted({c["page"] for c in finding.candidates}),
                gold_pages=gold_pages(pages, label_gold.spans) if label_gold.present else [],
            )
        )
    return outcomes


def evaluate(
    svc: Services,
    sample: Sequence[EvalContract],
    gold: Mapping[str, Mapping[str, GoldLabel]],
) -> tuple[list[ClauseOutcome], dict]:
    """Run each contract through the same service functions the API uses."""
    outcomes: list[ClauseOutcome] = []
    cost: dict = {"llm_calls": {}, "seconds": {}}
    for contract in sample:
        started = time.perf_counter()
        counter = CallCounter()
        stored = ingest_contract(svc, contract.pdf.name, contract.pdf.read_bytes())
        run = create_run(svc, stored.id)
        execute_run(svc, run.id, callbacks=[counter], tags=["eval"])
        contract_outcomes = _outcomes_for_contract(
            svc, contract, gold[contract.title], stored.id, run.id
        )
        if any(o.error and DAILY_LIMIT_MARKER in o.error for o in contract_outcomes):
            raise DailyLimitReached(contract.title, len(cost["llm_calls"]))
        outcomes += contract_outcomes
        cost["llm_calls"][contract.title] = counter.count
        cost["seconds"][contract.title] = time.perf_counter() - started
        print(f"done {contract.title}: {counter.count} LLM calls", flush=True)
    return outcomes, cost


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    gold = load_gold(args.cuad / "CUAD_v1.json", TARGET_LABELS)
    matched, unmatched = match_pdfs(gold, index_pdfs(args.cuad))
    eligible, excluded = eligible_contracts(gold, matched)
    sample, gaps = sample_contracts(eligible, gold, TARGET_LABELS, args.n, args.seed)

    if args.sample_only:
        print(f"Sample (n={args.n}, seed={args.seed}):")
        for contract in sample:
            print(f"  {contract.title}")
        print(f"Excluded: {len(excluded)}")
        for title, reason in excluded:
            print(f"  {title}: {reason}")
        print(f"Unmatched titles: {len(unmatched)}")
        print("Gaps: " + ("; ".join(gaps) if gaps else "none"))
        return 0

    settings = get_settings()
    svc = build_services(settings)
    try:
        outcomes, cost = evaluate(svc, sample, gold)
    except DailyLimitReached as exc:
        print(
            f"Daily free-model limit reached at {exc.title}; {exc.finished} contracts finished. "
            "No report written. Rerun the same command after the limit resets: "
            "finished work is served from the LLM cache."
        )
        return 2
    finally:
        if svc.close is not None:
            svc.close()
    now = datetime.now()
    report = render_report(
        config={
            "model": settings.openrouter_model,
            "seed": args.seed,
            "n": args.n,
            "playbook_hash": playbook_hash(),
            "git_commit": git_commit(),
            "date": now.strftime("%Y-%m-%d %H:%M"),
        },
        sample=[c.title for c in sample],
        excluded=excluded,
        gaps=gaps,
        outcomes=outcomes,
        cost=cost,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{now.strftime('%Y-%m-%d-%H%M')}.md"
    path.write_text(report)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
