from collections import Counter
from collections.abc import Sequence

from evals.cuad import TARGET_LABELS
from evals.metrics import (
    SPAN_MATCH_F1,
    ClauseOutcome,
    error_rate,
    presence_prf,
    retrieval_hit_rate,
    span_match_rate,
    uncertain_rate,
    verification_rejection_rate,
)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _labels(outcomes: Sequence[ClauseOutcome]) -> list[str]:
    present = {o.label for o in outcomes}
    return [label for label in TARGET_LABELS if label in present] + sorted(present - set(TARGET_LABELS))


def render_report(
    config: dict,
    sample: Sequence[str],
    excluded: Sequence[tuple[str, str]],
    gaps: Sequence[str],
    outcomes: Sequence[ClauseOutcome],
    cost: dict,
) -> str:
    labels = _labels(outcomes)
    out: list[str] = ["# ClauseLens eval report", "", "## Config", ""]
    out += [f"- {key}: {value}" for key, value in config.items()]

    out += ["", "## Sample", ""] + [f"- {title}" for title in sample]

    out += ["", "## Presence", ""]
    rows = []
    for label in labels:
        p, r, f1, tp, fp, fn = presence_prf(outcomes, label)
        rows.append([label, _fmt(p), _fmt(r), _fmt(f1), str(tp), str(fp), str(fn)])
    out += _table(["Clause", "P", "R", "F1", "TP", "FP", "FN"], rows)

    out += ["", "## Span match", "", f"Normalized token F1 >= {SPAN_MATCH_F1} against any gold span.", ""]
    out += _table(["Clause", "Span match rate"], [[label, _fmt(span_match_rate(outcomes, label))] for label in labels])

    out += [
        "",
        "## Verification rejection",
        "",
        f"Share of extracted quotes whose first attempt failed verification: {_fmt(verification_rejection_rate(outcomes))}",
        "",
        "## Uncertain and errors",
        "",
        f"- Uncertain rate: {_fmt(uncertain_rate(outcomes))}",
        f"- Error rate: {_fmt(error_rate(outcomes))}",
        "",
        "## Retrieval hit rate",
        "",
        "Among gold-present clauses, the share where any candidate page contains a gold span.",
        "",
    ]
    out += _table(["Clause", "Hit rate"], [[label, _fmt(retrieval_hit_rate(outcomes, label))] for label in labels])

    calls, seconds = cost.get("llm_calls", {}), cost.get("seconds", {})
    out += ["", "## Cost", "", "LLM calls include cache hits.", ""]
    out += _table(
        ["Contract", "LLM calls", "Seconds"],
        [[title, str(calls.get(title, "n/a")), f"{seconds[title]:.1f}" if title in seconds else "n/a"] for title in sample],
    )
    out += ["", f"Total LLM calls: {sum(calls.values())}", f"Total seconds: {sum(seconds.values()):.1f}"]

    out += ["", "## Excluded and gaps", "", f"Excluded before sampling: {len(excluded)}"]
    reasons = Counter(reason for _, reason in excluded)
    out += [f"- {reason}: {count}" for reason, count in sorted(reasons.items())]
    out += [f"- {title}: {reason}" for title, reason in excluded[:50]]
    out += ["", "Coverage gaps:"] + ([f"- {gap}" for gap in gaps] or ["- none"])
    return "\n".join(out) + "\n"
