import ast
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND / "app"
APP_FILES = sorted(APP_DIR.rglob("*.py"))
FORBIDDEN_IMPORTS = {"openai", "requests", "httpx"}


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_app_files_found():
    assert len(APP_FILES) > 5


def test_no_direct_http_or_openai_in_app():
    """AC-8: no direct HTTP client or openai import, and no hard-coded provider URL."""
    for path in APP_FILES:
        assert not imported_roots(path) & FORBIDDEN_IMPORTS, path
        assert "openrouter.ai" not in path.read_text(), path


def test_chat_model_constructed_only_in_llm_py():
    pattern = re.compile(r"\bChat[A-Z]\w*\(")
    offenders = [p for p in APP_FILES if pattern.search(p.read_text()) and p.name != "llm.py"]
    assert offenders == []
    assert pattern.search((APP_DIR / "llm.py").read_text())


def test_model_name_not_hard_coded():
    """C3: the model id comes from OPENROUTER_MODEL only."""
    assert [p for p in APP_FILES if "nemotron" in p.read_text().lower()] == []


def test_app_never_imports_evals():
    """AC-10: app/ never imports evals and never touches the CUAD dataset."""
    for path in APP_FILES:
        assert "evals" not in imported_roots(path), path
        text = path.read_text()
        assert "CUAD_v1" not in text, path
        # `cuad_label` is a playbook field name (the label string the eval maps to), not label data
        assert "cuad" not in text.lower().replace("cuad_label", ""), path


def test_importing_app_does_not_load_evals():
    code = (
        "import app.main, sys; "
        "assert not [m for m in sys.modules if m.split('.')[0] == 'evals']"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
