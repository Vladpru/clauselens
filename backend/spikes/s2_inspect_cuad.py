"""S2: inspect the CUAD download. Usage: s2_inspect_cuad.py <cuad_root> [--gold]"""

import json
import sys
from pathlib import Path


def print_tree(root: Path, max_depth: int = 3, max_entries: int = 12) -> None:
    def walk(path: Path, depth: int) -> None:
        children = sorted(path.iterdir())
        for child in children[:max_entries]:
            print("  " * depth + child.name + ("/" if child.is_dir() else ""))
            if child.is_dir() and depth + 1 < max_depth:
                walk(child, depth + 1)
        if len(children) > max_entries:
            print("  " * depth + f"... {len(children) - max_entries} more")

    print(root.name + "/")
    walk(root, 1)


def find_data_json(root: Path) -> Path:
    candidates = sorted(root.rglob("CUADv1.json")) or sorted(root.rglob("*.json"))
    return max(candidates, key=lambda p: p.stat().st_size)


def category_from_id(qa_id: str) -> str:
    return qa_id.rsplit("__", 1)[-1]


def category_from_question(question: str) -> str:
    start = question.find('"')
    end = question.find('"', start + 1)
    return question[start + 1 : end] if start != -1 and end != -1 else ""


def inspect(root: Path) -> None:
    print("== tree (depth 3)")
    print_tree(root)
    print("== json/csv files")
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in {".json", ".csv"}:
            print(f"{path.relative_to(root)}  {path.stat().st_size} bytes")
    pdfs = [p for p in root.rglob("*") if p.suffix.lower() == ".pdf"]
    txts = [p for p in root.rglob("*") if p.suffix.lower() == ".txt"]
    print(f"== counts: pdf={len(pdfs)} txt={len(txts)}")

    json_path = find_data_json(root)
    data = json.loads(json_path.read_text())
    print(f"== data json: {json_path.relative_to(root)}")
    print("top-level keys:", list(data))
    contracts = data["data"]
    print("contracts in json:", len(contracts))

    first = contracts[0]
    print("first contract keys:", list(first), "title:", first.get("title"))
    paragraphs = first["paragraphs"]
    print("paragraph keys:", list(paragraphs[0]), "count:", len(paragraphs))
    for qa in paragraphs[0]["qas"][:3]:
        print(json.dumps(qa, indent=2)[:1200])

    by_id: set[str] = set()
    by_question: set[str] = set()
    for contract in contracts:
        for paragraph in contract["paragraphs"]:
            for qa in paragraph["qas"]:
                by_id.add(category_from_id(qa["id"]))
                by_question.add(category_from_question(qa["question"]))
    print(f"== categories: by id suffix={len(by_id)} by question quote={len(by_question)}")
    for a, b in zip(sorted(by_id), sorted(by_question), strict=False):
        print(f"{a!r:45} {b!r}")


def gold_report(root: Path) -> None:
    from evals.cuad import TARGET_LABELS, index_pdfs, load_gold, match_pdfs

    gold = load_gold(find_data_json(root), TARGET_LABELS)
    for label in TARGET_LABELS:
        present = sum(1 for labels in gold.values() if labels[label].present)
        print(f"{label}: present={present} absent={len(gold) - present}")
    matched, unmatched = match_pdfs(gold, index_pdfs(root))
    print(f"contracts in json={len(gold)} matched={len(matched)} unmatched={len(unmatched)}")
    print("first 10 unmatched:", unmatched[:10])


if __name__ == "__main__":
    cuad_root = Path(sys.argv[1])
    if "--gold" in sys.argv:
        gold_report(cuad_root)
    else:
        inspect(cuad_root)
