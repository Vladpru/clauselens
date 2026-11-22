"""S1: structured output via ChatOpenRouter. Usage: s1_structured_output.py --mode function_calling|json_prompt"""

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter

import pymupdf
import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from app.config import REPO_ROOT, get_settings
from app.llm import get_chat_model

CONTRACTS = 2
MAX_CONTEXT_PAGES = 3
FALLBACK_PAGES = 2
PASS_THRESHOLD = 9
LEAK_PATTERN = re.compile(r"</?think>|<reasoning|\[reasoning\]", re.IGNORECASE)


class ClauseExtraction(BaseModel):
    found: bool
    quote: str | None
    reasoning: str


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def build_context(pdf_path: str, query_terms: list[str]) -> str:
    with pymupdf.open(pdf_path) as doc:
        pages = [(i + 1, page.get_text()) for i, page in enumerate(doc)]
    terms = [t.casefold() for t in query_terms]
    hits = [(n, t) for n, t in pages if any(term in t.casefold() for term in terms)]
    chosen = hits[:MAX_CONTEXT_PAGES] or pages[:FALLBACK_PAGES]
    return "\n\n".join(f"[Page {n}]\n{t}" for n, t in chosen)


def system_prompt(clause: dict) -> str:
    return (
        f"You review a contract for the clause: {clause['title']}.\n"
        f"Playbook requirement (for context only): {clause['requirement']}\n"
        "Find the clause in the contract pages below. Quote it verbatim, character for character. "
        "If the clause is not present, return found=false and quote=null. "
        "In `reasoning`, explain briefly where you found it or why it is absent."
    )


def has_reasoning(raw) -> bool:
    kwargs = getattr(raw, "additional_kwargs", {}) or {}
    if any("reason" in key and kwargs[key] for key in kwargs):
        return True
    content = getattr(raw, "content", None)
    return isinstance(content, list) and any(
        isinstance(block, dict) and "reason" in str(block.get("type", "")) for block in content
    )


def run_call(mode: str, clause: dict, context: str) -> dict:
    messages = [SystemMessage(system_prompt(clause)), HumanMessage(context)]
    started = time.monotonic()
    record = {"valid": False, "error_type": None, "reasoning_present": False, "leak": False, "verbatim": None}
    try:
        model = get_chat_model()
        if mode == "function_calling":
            out = model.with_structured_output(ClauseExtraction, method="function_calling", include_raw=True).invoke(messages)
            parsed, raw = out["parsed"], out["raw"]
            if not isinstance(parsed, ClauseExtraction) or out["parsing_error"] is not None:
                raise ValueError(f"parsing_error: {out['parsing_error']}")
        else:
            parser = PydanticOutputParser(pydantic_object=ClauseExtraction)
            messages[0] = SystemMessage(system_prompt(clause) + "\n\n" + parser.get_format_instructions())
            raw = model.invoke(messages)
            parsed = parser.parse(raw.content if isinstance(raw.content, str) else json.dumps(raw.content))
        record["valid"] = True
        record["reasoning_present"] = has_reasoning(raw)
        record["leak"] = bool(LEAK_PATTERN.search(f"{parsed.quote or ''} {parsed.reasoning}"))
        if parsed.quote:
            record["verbatim"] = collapse(parsed.quote) in collapse(context)
    except Exception as exc:  # noqa: BLE001 - count every failure type and keep going
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)[:300]
    record["latency_s"] = round(time.monotonic() - started, 2)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["function_calling", "json_prompt"], required=True)
    mode = parser.parse_args().mode

    settings = get_settings()
    contracts = json.loads((settings.data_dir / "spikes" / "s3.json").read_text())[:CONTRACTS]
    playbook = yaml.safe_load((REPO_ROOT / "playbook" / "playbook.yaml").read_text())

    records = []
    for contract in contracts:
        for clause in playbook["clauses"]:
            context = build_context(contract["pdf"], clause["query_terms"])
            record = {"title": contract["title"], "clause": clause["id"], **run_call(mode, clause, context)}
            records.append(record)
            print(f"{clause['id']:28} valid={record['valid']} {record['error_type'] or ''} {record['latency_s']}s")

    out_path = settings.data_dir / "spikes" / f"s1_{mode}.json"
    out_path.write_text(json.dumps(records, indent=2))

    valid = sum(r["valid"] for r in records)
    leaks = sum(r["leak"] for r in records)
    errors = Counter(r["error_type"] for r in records if r["error_type"])
    verbatim = [r["verbatim"] for r in records if r["verbatim"] is not None]
    print(f"valid {valid}/{len(records)}  errors={dict(errors)}  leak_flags={leaks}")
    print(f"median latency {statistics.median(r['latency_s'] for r in records)}s")
    print(f"reasoning present on {sum(r['reasoning_present'] for r in records)} calls; verbatim {sum(verbatim)}/{len(verbatim)}")
    ok = valid >= PASS_THRESHOLD
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
