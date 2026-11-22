# Phase 0: Foundations and Spikes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the repo, environment, and dependencies. Resolve the five risky unknowns (S1 to S5) and draft the playbook, so Phase 1 starts from verified facts.

**Architecture:** Spike scripts live in `backend/spikes/` and use the real `app/config.py` and `app/llm.py`, so C1 holds from day one. The CUAD gold parser is written for real in `backend/evals/cuad.py` with unit tests. Raw spike output goes to `data/spikes/` (gitignored). A short summary of each result goes into the spec appendix.

**Tech Stack:** Python 3.15 (fallback 3.14) with `uv`, FastAPI, SQLModel, psycopg, PyMuPDF, LangChain + `langchain-openrouter`, LangGraph + `langgraph-checkpoint-postgres`, `langchain-qdrant`, `qdrant-client`, FastEmbed, PostgreSQL 16 and Qdrant in Docker, Next.js + pnpm.

**Spec:** `docs/specs/2026-11-22-contract-review-mvp-design.md` (sections 3, 4, 6.2, 6.6, 7, 10 Phase 0, 11, 12.A, 12.B, appendix).

## Preconditions (blockers, check before Task 1)

- [ ] The owner approves the spec. AGENTS.md: "Executing a phase needs the owner's approval of the spec first." The spec status is DRAFT today.
- [x] Open questions answered: see "Decisions" at the end of this plan.
- [ ] Tools present. Run: `uv --version && docker --version && docker compose version && node -v && pnpm -v`. Expected: all five print a version. If one is missing, stop and report.

## Global Constraints

- C1: LLM access only through LangChain chat model objects. No direct `openai`, `requests`, or `httpx` calls to the model API. `backend/app/llm.py` is the only place a chat model is constructed, including in spikes.
- C3: Provider is OpenRouter. The model name comes from `OPENROUTER_MODEL`, never hard-coded (not even as a `Settings` default).
- C4: Only public CUAD contracts.
- C7: Python 3.15. Fallback 3.14 only if S4 fails, and the reason is recorded.
- C8: App data and checkpoints in PostgreSQL, vectors in Qdrant, both from `docker-compose.yml`.
- Never read, print, or commit `.env`. The owner creates it. Programs may load it; the agent never opens it.
- CUAD gold labels are never put into an LLM prompt (anti-goal, section 2). S1 prompts use PDF page text only.
- `backend/app/` never imports `backend/evals/` (AC-10). Spikes may import both.
- The agent never writes under `data/cuad/` (denied in `.claude/settings.json`). The owner downloads CUAD.
- No commits unless the owner asks (AGENTS.md). This plan has no commit steps.
- Unverified library APIs (`ChatOpenRouter` parameter names, `langchain-qdrant` hybrid API, `PostgresSaver`): check current docs (context7) before writing the call. Where the docs disagree with this plan, follow the docs and note the difference in the spike record.

## Assumptions (stated, not asked)

- A1. `.env` lives at the repo root (spec section 11 step 5). `Settings` loads `<repo root>/.env`, so commands work from `backend/`.
- A2. A relative `DATA_DIR` resolves against the repo root, so `./data` means `clauselens/data/`, as in the spec layout (section 6.1).
- A3. Spikes run in this order: S4, S2, playbook, S3, S5, S1. S1 needs real page text and the playbook query terms, and S3 and S5 need the gold parser.
- A4. Spike-only Pydantic models and chunking live in the spike scripts. Phase 1 defines the real ones.

## Review Focus

1. A playbook `cuad_label` with a typo or wrong case (for example `"Governing law"`) makes every contract look "absent" in gold and corrupts eval numbers silently. Expected: `load_gold` raises and names the bad label. Test: `test_unknown_label_raises` (Task 5).
2. A CUAD answer that is empty or whitespace only must not count as "present". Test: `test_whitespace_only_answer_is_absent` (Task 5).
3. A contract title in the JSON with no matching PDF (509 vs 510 files, name drift) must be reported, not crash the run or silently shrink the sample. Test: `test_match_pdfs_reports_unmatched` (Task 5).
4. A missing `OPENROUTER_API_KEY` must fail at startup with a clear error, not as a 401 deep inside a graph run. The key must never appear in logs or `repr`. Tests: `test_settings_requires_api_key`, `test_api_key_not_in_repr` (Task 3).
5. A relative `DATA_DIR` must not depend on the working directory (`backend/` vs repo root). Otherwise uploads and parsed pages land in two places. Test: `test_relative_data_dir_resolves_to_repo_root` (Task 3).

---

### Task 1: Repo files (`.env.example`, `docker-compose.yml`, README warning)

**Files:**
- Create: `.env.example`, `docker-compose.yml`, `README.md`
- Modify: `.gitignore` (remove the `/docs` line only, decision D1)

- [ ] **Step 1: Fix `.gitignore` and check it covers the spec list**

Remove the line `/docs`. Keep `CLAUDE.md` and every other line.
Run: `grep -qxF '/docs' .gitignore && echo "STILL IGNORED" ; for p in .env data/ '*.db' .venv/ node_modules/ .next/ __pycache__/; do grep -qxF "$p" .gitignore && echo "ok $p" || echo "MISSING $p"; done; git check-ignore -q docs/specs/2026-11-22-contract-review-mvp-design.md && echo "docs ignored" || echo "docs tracked"`
Expected: seven `ok` lines, then `docs tracked`. No `STILL IGNORED`.

- [ ] **Step 2: Create `.env.example`**

Copy it verbatim from spec section 11 (7 variables, `OPENROUTER_API_KEY` empty).
Verify: `grep -c '=' .env.example` prints `7`, and `grep '^OPENROUTER_API_KEY=$' .env.example` matches.

- [ ] **Step 3: Create `docker-compose.yml`**

Copy it verbatim from spec section 11. Keep `image: qdrant/qdrant` for now. Task 4 pins the tag.
Verify: `docker compose config --quiet && echo valid` prints `valid`.

- [ ] **Step 4: Create `README.md`**

Contents: a one-line project description, the dev commands from spec section 11, and this warning in bold: "Only public CUAD contracts. Never upload real or confidential contracts: the free OpenRouter endpoint may log prompts and outputs." Also the footer text "AI-assisted review. Not legal advice."
Verify: `grep -c 'Never upload real' README.md` prints `1`.

- [ ] **Step 5: Owner creates `.env`**

Owner runs: `cp .env.example .env`, then adds the OpenRouter key. The agent does not read the file.
Verify (no content printed): `test -f .env && git check-ignore -q .env && echo "present and ignored"`.

---

### Task 2: S4 part A, backend project and dependencies on Python 3.15

**Spike S4 pass criterion (spec section 10):** On Python 3.15, `uv sync` installs the full dependency set, `docker compose up -d` brings up Postgres and Qdrant, `PostgresSaver.setup()` runs, and a SQLModel `create_all` succeeds. Task 2 covers the install. Task 4 covers the rest.
**Fallback (spec section 7):** Python 3.14, recorded with the exact failing package and error line.
**Result goes to:** spec appendix, `S4:` line.

**Files:**
- Create: `backend/pyproject.toml`, `backend/.python-version`, `backend/uv.lock` (all from `uv`)
- Create: `backend/app/__init__.py`, `backend/evals/__init__.py`, `backend/spikes/__init__.py`, `backend/tests/__init__.py` (empty)
- Delete: `backend/main.py` and `backend/README.md` if `uv init` generates them. They are stubs and would be confused with `app/main.py`.

- [ ] **Step 1: Update uv and find 3.15**

Run: `uv self update && uv --version && uv python list | grep -E '3\.1[45]'`
Expected: a uv version newer than 0.11.21, and at least one `3.15` entry. Record whether it is a final release (`3.15.0`) or a pre-release (`3.15.0bN`/`rcN`). If only a pre-release exists, apply decision D8.

- [ ] **Step 2: Init the project**

Run: `mkdir -p backend && cd backend && uv init --app --name contract-review-backend --python 3.15`
Verify: `cat backend/.python-version` starts with `3.15`, and `grep requires-python backend/pyproject.toml` shows `>=3.15`.

- [ ] **Step 3: Add the dependencies (exact list from spec section 11)**

Run from `backend/`:
```bash
uv add fastapi "uvicorn[standard]" python-multipart sqlmodel pydantic-settings pyyaml \
  "psycopg[binary,pool]" pymupdf langchain langchain-openrouter langgraph \
  langgraph-checkpoint-postgres langchain-qdrant qdrant-client fastembed
uv add --dev pytest pytest-asyncio httpx ruff
```
Expected: both commands exit 0. If one fails, copy the shortest decisive error line (package name and reason) into the S4 record. Then go to Step 5.

- [ ] **Step 4: Import smoke test**

Run from `backend/`:
```bash
uv run python -c "import fastapi, uvicorn, sqlmodel, pydantic_settings, yaml, psycopg, psycopg_pool, pymupdf, onnxruntime, fastembed, langchain, langchain_openrouter, langgraph, langgraph.checkpoint.postgres, langchain_qdrant, qdrant_client; import sys; print(sys.version); print('psycopg impl:', psycopg.pq.__impl__); print('imports ok')"
```
Expected: the Python version starts with `3.15`, `psycopg impl: binary`, and `imports ok`. `psycopg impl: python` means the binary wheel is missing on 3.15. Record that as an S4 finding. It is a slowdown, not a blocker.

- [ ] **Step 5 (only if Step 3 or 4 failed): Fall back to 3.14**

Run from `backend/`: `uv python pin 3.14 && sed -i '' 's/requires-python = ">=3.15"/requires-python = ">=3.14,<3.15"/' pyproject.toml && uv sync`, then repeat Step 4 and expect `3.14`.
Record in S4: the failing package, the error line, and "fell back to 3.14". Spec C7 and section 6.2 then need an owner-approved edit. Do not edit them silently.

- [ ] **Step 6: Configure pytest and ruff**

Add to `backend/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```
Verify: `cd backend && uv run pytest` exits with code 5 ("no tests ran"). `uv run ruff check .` prints `All checks passed!`.

---

### Task 3: `app/config.py` and `app/llm.py` (minimal, used by spikes)

**Files:**
- Create: `backend/app/config.py`, `backend/app/llm.py`
- Test: `backend/tests/test_config.py`, `backend/tests/test_llm.py`

**Interfaces:**
- Produces:
  - `class Settings(pydantic_settings.BaseSettings)`. Fields: `openrouter_api_key: SecretStr` (required), `openrouter_model: str` (required, no default, C3), `llm_max_concurrency: int = 2`, `data_dir: Path = Path("data")`, `database_url: str`, `checkpoint_db_url: str`, `qdrant_url: str`. `env_file` = `REPO_ROOT / ".env"`. A validator makes a relative `data_dir` absolute against `REPO_ROOT`.
  - `REPO_ROOT: Path = Path(__file__).resolve().parents[2]`
  - `get_settings() -> Settings` (cached with `functools.lru_cache`)
  - `get_chat_model(settings: Settings | None = None) -> BaseChatModel` returns a `ChatOpenRouter` with `temperature=0`, the configured model, and module constants `LLM_MAX_TOKENS = 4096`, `LLM_TIMEOUT_S = 120`, `LLM_MAX_RETRIES = 3`. Check the exact `ChatOpenRouter` parameter names in the `langchain-openrouter` docs first.

- [ ] **Step 1: Write failing tests**

`tests/test_config.py`. A fixture `env` uses `monkeypatch.setenv` to set every variable from `.env.example` with fake values (`OPENROUTER_API_KEY="test-key"`, `OPENROUTER_MODEL="vendor/model:free"`, `DATA_DIR="./data"`, and so on). Every test builds `Settings(_env_file=None)`, so the real `.env` is never read.
- `test_settings_reads_model_from_env`: `s.openrouter_model == "vendor/model:free"`
- `test_settings_requires_api_key`: after `monkeypatch.delenv("OPENROUTER_API_KEY")`, `pytest.raises(ValidationError)`
- `test_settings_requires_model`: same, for `OPENROUTER_MODEL`
- `test_api_key_not_in_repr`: `"test-key" not in repr(s)` and `"test-key" not in str(s.model_dump())`
- `test_relative_data_dir_resolves_to_repo_root`: `s.data_dir == REPO_ROOT / "data"`, also after `monkeypatch.chdir(tmp_path)`

`tests/test_llm.py` (uses the same `env` fixture, moved to `tests/conftest.py`):
- `test_get_chat_model_uses_configured_model`: `m = get_chat_model(Settings(_env_file=None))`, `isinstance(m, ChatOpenRouter)`, and the model attribute (name from the docs) `== "vendor/model:free"`
- `test_get_chat_model_temperature_zero`: `m.temperature == 0`

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Implement `Settings`, `get_settings`, and `get_chat_model` as given in Interfaces**

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_llm.py -v && uv run ruff check .`
Expected: 7 passed, ruff clean, no network access (constructing a model makes no call).

---

### Task 4: S4 part B, Docker, databases, and the checkpointer smoke test

**Pass criterion, fallback, and result destination:** as in Task 2.

**Files:**
- Modify: `docker-compose.yml` (pin the Qdrant tag only)
- Create: `backend/spikes/s4_smoke.py`

- [ ] **Step 1: Pull Qdrant and find its version**

Run: `docker pull qdrant/qdrant && docker compose up -d && sleep 5 && curl -s http://localhost:6333`
Expected: JSON with `"version":"X.Y.Z"`.

- [ ] **Step 2: Pin the tag**

Edit `docker-compose.yml`: `image: qdrant/qdrant:vX.Y.Z` (the version from Step 1). Remove the "pin a tag" comment.
Run: `docker compose up -d && docker compose ps && curl -s http://localhost:6333/readyz && docker compose exec postgres pg_isready -U postgres`
Expected: both services `running`, `all shards are ready`, and `accepting connections`.

- [ ] **Step 3: Create the two databases**

Run: `docker compose exec postgres createdb -U postgres contract_review && docker compose exec postgres createdb -U postgres contract_review_checkpoints`
Verify: `docker compose exec postgres psql -U postgres -lqt | cut -d'|' -f1 | grep -wE 'contract_review|contract_review_checkpoints'` prints both names.

- [ ] **Step 4: Write `spikes/s4_smoke.py`**

`main() -> int` uses `get_settings()` and runs three checks. Each check prints `PASS <name>` or `FAIL <name>: <error>`, and the script exits non-zero on any failure.
1. `checkpointer`: `with PostgresSaver.from_conn_string(settings.checkpoint_db_url) as saver: saver.setup()`.
2. `sqlmodel`: on `create_engine(settings.database_url)`, define a throwaway table `S4Probe(id: int primary key, note: str)`. Run `create_all`, insert one row, select it back, then `drop_all`, so no spike table is left behind.
3. `qdrant`: `QdrantClient(url=settings.qdrant_url).get_collections()` returns without an error.

- [ ] **Step 5: Run the smoke test**

Run: `cd backend && uv run python -m spikes.s4_smoke`
Expected: `PASS checkpointer`, `PASS sqlmodel`, `PASS qdrant`, exit 0.
Verify the checkpoint tables: `docker compose exec postgres psql -U postgres -d contract_review_checkpoints -c '\dt'` lists `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`.
Verify there is no leftover probe table: `docker compose exec postgres psql -U postgres -d contract_review -c '\dt'` prints `Did not find any relations.`

- [ ] **Step 6: Record S4**

In the spec appendix `S4:` line: Python version used (final or pre-release), uv version, psycopg impl, Qdrant tag, result of each smoke check, and any fallback taken.

---

### Task 5: Frontend scaffold

**Files:**
- Create: `frontend/` (generated)

- [ ] **Step 1: Scaffold**

Check the current flags first: `pnpm dlx create-next-app@latest --help`. Then run:
`pnpm dlx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm --yes`
Verify: `test -f frontend/package.json && test ! -d frontend/.git && echo ok` prints `ok`. A nested `.git` must not exist. If one was created, stop and report; do not delete it without asking.

- [ ] **Step 2: shadcn and libraries**

Run: `cd frontend && pnpm dlx shadcn@latest init -d && pnpm add @tanstack/react-query react-pdf`
Verify: `test -f frontend/components.json && grep -E '"(@tanstack/react-query|react-pdf)"' frontend/package.json` prints two lines.

- [ ] **Step 3: Lint and build**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: both exit 0.

---

### Task 6: S2, CUAD inspection and gold parser

**Spike S2 pass criterion (spec section 10):** Inspect the CUAD files, confirm the label strings and the gold format, and write the gold parser. Done means: the folder layout, JSON shape, and contract count are recorded; all 5 target labels exist as exact strings; the parser unit tests pass; the parser loads the real file and reports per-label present counts and PDF match counts.
**Fallback:** If a target label does not exist, the owner picks a replacement clause (spec section 6.6 allows a swap). If the JSON shape is not SQuAD-style, adapt the parser to the real shape and propose a correction to spec section 4.
**Result goes to:** spec appendix, `S2:` line.

**Precondition:** The owner has unzipped `CUAD_v1.zip` into `data/cuad/`.

**Files:**
- Create: `backend/spikes/s2_inspect_cuad.py`, `backend/evals/cuad.py`
- Test: `backend/tests/evals/__init__.py`, `backend/tests/evals/test_cuad.py`, `backend/tests/fixtures/cuad_mini.json` (synthetic, made up, no real CUAD text)

**Interfaces:**
- Produces (`evals/cuad.py`):
  - `TARGET_LABELS: tuple[str, ...]`, the 5 confirmed strings
  - `@dataclass(frozen=True) class GoldLabel: title: str; label: str; present: bool; spans: tuple[str, ...]`. `spans` holds the stripped, non-empty answer texts in file order.
  - `load_gold(json_path: Path, labels: Collection[str]) -> dict[str, dict[str, GoldLabel]]`, keyed by title, then label. It raises `ValueError` naming every requested label that appears in no question in the file. A contract with no QA entry for a requested label gets `present=False`.
  - `index_pdfs(cuad_root: Path) -> dict[str, Path]`, keyed by file stem. It matches `.pdf` case-insensitively and raises `ValueError` on duplicate stems.
  - `match_pdfs(titles: Iterable[str], pdf_index: Mapping[str, Path]) -> tuple[dict[str, Path], list[str]]` returns (matched, unmatched titles). Exact stem match only. Step 2 decides whether a looser rule is needed.

- [ ] **Step 1: Write and run the inspection script**

`spikes/s2_inspect_cuad.py <cuad_root>` prints:
- the directory tree to depth 3
- the JSON and CSV file names and sizes
- the PDF and TXT counts
- the JSON top-level keys
- for the first contract: its keys and its first 3 QA entries in full (`id`, `question`, `answers`, `is_impossible`)
- the sorted set of category names, read from the QA `id` suffix after the last `__` and from the quoted string in `question`, side by side
- the number of contracts in the JSON

Run: `cd backend && uv run python -I -m spikes.s2_inspect_cuad ../data/cuad`
Expected: 41 categories. Write down the exact strings for the 5 targets (spec guesses: `Governing Law`, `Termination For Convenience`, `Cap On Liability`, `Non-Compete`, `Anti-Assignment`). Confirm which source (`id` suffix or `question`) gives them reliably. `load_gold` uses that source.

- [ ] **Step 2: Write the fixture in the confirmed shape**

`tests/fixtures/cuad_mini.json` has 2 made-up contracts, `ALPHA_AGREEMENT` and `BETA_AGREEMENT`, in exactly the shape Step 1 printed:
- ALPHA: `Governing Law` with one answer `"This Agreement is governed by the laws of Delaware."`. `Non-Compete` with `answers: []`. `Cap On Liability` with one answer whose text is `"   "`. `Anti-Assignment` with two answers `"Neither party may assign this Agreement."` and `"Any attempted assignment is void."`. No QA entry for `Termination For Convenience`.
- BETA: `Governing Law` with `answers: []`.

- [ ] **Step 3: Write failing tests**

`tests/evals/test_cuad.py`:
- `test_present_when_non_empty_answer`: ALPHA `Governing Law` gives `present is True` and `spans == ("This Agreement is governed by the laws of Delaware.",)`
- `test_absent_when_no_answers`: BETA `Governing Law` gives `present is False` and `spans == ()`
- `test_whitespace_only_answer_is_absent`: ALPHA `Cap On Liability` gives `present is False`
- `test_multiple_spans_kept_in_order`: ALPHA `Anti-Assignment` spans equal the two texts in file order
- `test_missing_qa_entry_counts_as_absent`: ALPHA `Termination For Convenience` gives `present is False`
- `test_unknown_label_raises`: `load_gold(path, ["Governing Law", "Governing law"])` raises `ValueError` matching `"Governing law"`
- `test_only_requested_labels_returned`: `set(load_gold(path, ["Governing Law"])["ALPHA_AGREEMENT"]) == {"Governing Law"}`
- `test_index_pdfs_finds_nested_and_uppercase_suffix`: in `tmp_path`, `a/X.pdf` and `b/c/Y.PDF` give the keys `{"X", "Y"}`
- `test_index_pdfs_duplicate_stem_raises`: `a/X.pdf` and `b/X.pdf` raise `ValueError`
- `test_match_pdfs_reports_unmatched`: titles `["X", "Z"]` give `({"X": path}, ["Z"])`

Run: `cd backend && uv run pytest tests/evals/test_cuad.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'evals.cuad'`.

- [ ] **Step 4: Implement `evals/cuad.py` as given in Interfaces**

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd backend && uv run pytest tests/evals/test_cuad.py -v && uv run ruff check .`
Expected: 10 passed, ruff clean.

- [ ] **Step 6: Run on the real data**

Extend `s2_inspect_cuad.py` with a `--gold` flag. It calls `load_gold(<json>, TARGET_LABELS)`, `index_pdfs`, and `match_pdfs`, then prints, for each label, how many contracts have it present and absent, plus the matched and unmatched counts and the first 10 unmatched titles.
Run: `cd backend && uv run python -I -m spikes.s2_inspect_cuad ../data/cuad --gold`
Expected: no `ValueError`, present counts > 0 for all 5 labels, and unmatched ≤ 1 (the scanned file some mirrors drop). More unmatched titles mean `match_pdfs` needs a rule: record the pattern and ask the owner before changing it.

- [ ] **Step 7: Record S2**

Appendix `S2:`: folder names, JSON path and shape, contract count (JSON vs PDF), the 5 exact label strings, per-label present/absent counts, and the unmatched titles.

---

### Task 7: Playbook draft (owner reviews)

**Files:**
- Create: `playbook/playbook.yaml`

Schema from spec section 6.6, plus one new field `absence_is: ok | missing` (decision D2). Stance from spec section 13.2 (kept, decision D3). The `cuad_label` values are the exact strings from Task 6. Rule text is a draft for the owner to edit.

- [ ] **Step 1: Write `playbook/playbook.yaml`**

```yaml
version: 1
stance: "We are a commercial party reviewing a third-party agreement."
clauses:
  - id: governing_law
    cuad_label: "Governing Law"
    title: "Governing law"
    query_terms: ["governing law", "governed by", "laws of", "jurisdiction"]
    requirement: "Governing law must be England and Wales, or an EU member state."
    acceptable: ["England and Wales", "Scotland", "any EU member state"]
    red_flags: ["law of a jurisdiction outside UK/EU without our approval"]
    preferred_wording: "This Agreement is governed by the laws of England and Wales."
    severity_if_missing: medium
    absence_is: missing

  - id: termination_for_convenience
    cuad_label: "Termination For Convenience"
    title: "Termination for convenience"
    query_terms: ["terminate for convenience", "without cause", "for any reason", "terminate this agreement at any time", "upon written notice"]
    requirement: "If termination for convenience exists, it must be available to both parties and need at least 30 days' written notice."
    acceptable: ["mutual right with 30 or more days' notice", "no termination for convenience for either party"]
    red_flags: ["only the counterparty may terminate for convenience", "notice period under 30 days", "termination with immediate effect and no notice"]
    preferred_wording: "Either party may terminate this Agreement for convenience by giving the other party not less than thirty (30) days' prior written notice."
    severity_if_missing: low
    absence_is: ok

  - id: cap_on_liability
    cuad_label: "Cap On Liability"
    title: "Cap on liability"
    query_terms: ["limitation of liability", "aggregate liability", "shall not exceed", "in no event shall", "liable for"]
    requirement: "Liability must be capped for both parties, at no less than the fees paid or payable in the 12 months before the claim, with carve-outs for fraud, wilful misconduct, and death or personal injury caused by negligence."
    acceptable: ["mutual cap at or above 12 months' fees", "mutual cap at a fixed amount we approve"]
    red_flags: ["cap protects only the counterparty", "cap below 12 months' fees", "no carve-out for fraud or wilful misconduct"]
    preferred_wording: "Except for liability for fraud, wilful misconduct, or death or personal injury caused by negligence, each party's total aggregate liability arising out of or in connection with this Agreement shall not exceed the total fees paid or payable under this Agreement in the twelve (12) months preceding the event giving rise to the claim."
    severity_if_missing: high
    absence_is: missing

  - id: non_compete
    cuad_label: "Non-Compete"
    title: "Non-compete"
    query_terms: ["non-compete", "shall not compete", "competing products", "competitive business", "directly or indirectly engage"]
    requirement: "We must not accept a non-compete. If one exists, it must be limited to the subject matter of this Agreement, to a defined territory, and to the term plus at most 12 months."
    acceptable: ["no non-compete binding on us", "narrow non-compete limited in scope, territory, and time"]
    red_flags: ["non-compete binding on us with no end date", "worldwide scope", "covers products or services outside this Agreement"]
    preferred_wording: "Any restriction on competition under this Agreement applies only to the products and services supplied under this Agreement, only within the Territory, and ends twelve (12) months after this Agreement terminates or expires."
    severity_if_missing: low
    absence_is: ok

  - id: anti_assignment
    cuad_label: "Anti-Assignment"
    title: "Anti-assignment"
    query_terms: ["assign", "assignment", "transfer this agreement", "prior written consent", "change of control"]
    requirement: "Assignment must need the other party's prior written consent, not unreasonably withheld, for both parties. We must be able to assign without consent to an affiliate or to a successor in a merger or sale of substantially all assets."
    acceptable: ["mutual consent requirement with affiliate and successor carve-out"]
    red_flags: ["counterparty may assign freely while we need consent", "consent at the counterparty's sole discretion", "change of control of us counts as assignment"]
    preferred_wording: "Neither party may assign or transfer this Agreement without the prior written consent of the other party, such consent not to be unreasonably withheld, except that either party may assign this Agreement without consent to an affiliate or to a successor in connection with a merger, acquisition, or sale of all or substantially all of its assets."
    severity_if_missing: medium
    absence_is: missing
```

- [ ] **Step 2: Structural check (no `app/playbook.py` yet, that is Phase 1)**

Run from `backend/`:
```bash
uv run python -c "
import yaml; from evals.cuad import TARGET_LABELS
p = yaml.safe_load(open('../playbook/playbook.yaml'))
keys = {'id','cuad_label','title','query_terms','requirement','acceptable','red_flags','preferred_wording','severity_if_missing','absence_is'}
assert p['version'] == 1 and len(p['clauses']) == 5
for c in p['clauses']:
    assert set(c) == keys, c['id']
    assert c['severity_if_missing'] in {'low','medium','high'}, c['id']
    assert c['absence_is'] in {'ok','missing'}, c['id']
assert {c['cuad_label'] for c in p['clauses']} == set(TARGET_LABELS)
assert len({c['id'] for c in p['clauses']}) == 5
print('playbook ok')"
```
Expected: `playbook ok`.

- [ ] **Step 3: Owner review**

Hand the file to the owner. Changes to stance, rules, or clause choice go into the file. Tasks 8 and 9 read `query_terms` from it, so finish the review first or accept a rerun.

---

### Task 8: S3, PyMuPDF text and `search_for`

**Spike S3 pass criterion (spec section 10):** "PyMuPDF on 3 CUAD PDFs: page text extraction and `search_for` on a known quote." The spec does not give a number. This plan treats it as: for 3 of 3 PDFs, every page returns text, and the page holding a known gold quote is found by normalized substring match. `search_for` and word-level rectangle results are recorded. They are best-effort (spec section 7) and do not fail the spike.
**Fallback:** If the normalized match fails, try in this order: map curly quotes to straight, en and em dashes to `-`, and remove soft hyphens; then `get_text(sort=True)`. Record which step was needed, because it drives Phase 1 normalization. If 3 of 3 still cannot be reached, stop and report. The spec has no other PDF library.
**Result goes to:** spec appendix, `S3:` line, and `data/spikes/s3.json` (read by Tasks 9 and 10).

**Files:**
- Create: `backend/spikes/s3_pymupdf.py`

- [ ] **Step 1: Write `spikes/s3_pymupdf.py`**

- Selection: titles where `Governing Law` is present and the PDF matches, sorted, then `random.Random(42).sample(titles, 3)`.
- Per contract: page count; pages with empty `get_text()`; the first gold `Governing Law` span; the page number (1-based) where the whitespace-collapsed, casefolded span is a substring of the page text; whether the span crosses a page break (it matches only the joined text of two pages).
- Per contract: `len(page.search_for(span))` on that page, and the count of rectangles from a word-level match (consecutive `get_text("words")` tokens equal to the span tokens).
- Write `data/spikes/s3.json`: a list of `{title, pdf, page_count, empty_pages, gold_page, crosses_page, normalization_needed, search_for_rects, word_rects}`.

Gold spans are used here only as test strings for PyMuPDF. They are never sent to an LLM.

- [ ] **Step 2: Run**

Run: `cd backend && uv run python -I -m spikes.s3_pymupdf ../data/cuad`
Expected: 3 records, each with `gold_page` not null and `empty_pages == []`. Print a `PASS`/`FAIL` line against the criterion above.

- [ ] **Step 3: Record S3**

Appendix `S3:`: the 3 titles, page counts, normalization steps needed, and `search_for` vs word-level rectangle hit rates.

---

### Task 9: S5, Qdrant hybrid retrieval

**Spike S5 pass criterion (spec section 10):** Qdrant hybrid retrieval (dense + sparse) works through `langchain-qdrant` on 3 contracts and returns the page-tagged chunk for a known clause. This plan treats it as: for 3 of 3 contracts (from `data/spikes/s3.json`), the top 8 results for the `governing_law` query terms, filtered by `contract_id`, include a chunk whose `page == gold_page`, and every result has the queried `contract_id`.
**Fallback (spec section 6.2):** `rank_bm25` in process plus Qdrant dense search, merged with reciprocal rank fusion (k = 60). This adds the `rank-bm25` dependency: `uv add rank-bm25`, recorded.
**Result goes to:** spec appendix, `S5:` line, and `data/spikes/s5.json`.

**Files:**
- Create: `backend/spikes/s5_hybrid.py`

- [ ] **Step 1: Check the current API**

Read the `langchain-qdrant` docs (context7) for `QdrantVectorStore`, `RetrievalMode.HYBRID`, and `FastEmbedSparse`, and for how metadata is stored in the payload (a nested `metadata.` key or top level). Note the answer. Spec section 6.4 expects `contract_id`, `page`, and `chunk_id` in the payload.

- [ ] **Step 2: Write `spikes/s5_hybrid.py --mode hybrid|fallback`**

- Chunks: per page, 800-character windows with 150 overlap (spike-only values, section 14). Metadata `{contract_id: title, page, chunk_id}`.
- Dense: `BAAI/bge-small-en-v1.5` through FastEmbed. Use a small spike-local `Embeddings` adapter over `fastembed.TextEmbedding` (decision D5). Set FastEmbed `cache_dir` to `settings.data_dir / "models"`.
- Sparse: `FastEmbedSparse(model_name="Qdrant/bm25")`.
- Collection `contract_chunks_spike`, recreated on each run, never the real `contract_chunks`.
- Query: `" ".join(query_terms)` for `governing_law` from `playbook/playbook.yaml`, `k=8`, filtered on `contract_id`.
- `--mode fallback`: BM25 over the same chunks plus a dense-only Qdrant query, merged by RRF.
- Write `data/spikes/s5.json` per contract: `{title, gold_page, result_pages, hit, foreign_results}`. Print `PASS`/`FAIL`. At the end, delete the spike collection.

- [ ] **Step 3: Run hybrid mode**

Run: `cd backend && uv run python -m spikes.s5_hybrid --mode hybrid`
Expected: `hit: true` and `foreign_results: 0` for all 3, then `PASS`.
While the collection exists, the script prints the response of `GET {qdrant_url}/collections/contract_chunks_spike`. Expected: both a dense vector and a sparse vector config.

- [ ] **Step 4 (only if Step 3 failed): Run fallback mode**

Run: `uv add rank-bm25 && uv run python -m spikes.s5_hybrid --mode fallback`
Expected: `PASS`. If this also fails, stop and report with both result files.

- [ ] **Step 5: Record S5**

Appendix `S5:`: mode used, hits (3 of 3?), where `gold_page` ranked, payload layout (nested or flat), Qdrant tag.

---

### Task 10: S1, structured output with ChatOpenRouter and Nemotron free

**Spike S1 pass criterion (spec section 10):** `ChatOpenRouter` + Nemotron free + `with_structured_output(method="function_calling")` returns valid Pydantic objects on a sample extraction prompt in at least 9 of 10 tries.
This plan uses 10 different inputs (5 clauses × 2 contracts) instead of one prompt repeated. That is stricter and closer to real use (decision D4).
**Fallback (spec sections 7 and 10):** JSON-in-prompt plus `PydanticOutputParser`, or another OpenRouter model. The owner decides before Phase 1. To give the owner data, run the `json_prompt` mode once if `function_calling` fails.
**Result goes to:** spec appendix, `S1:` line, and `data/spikes/s1_<mode>.json`.

**Files:**
- Create: `backend/spikes/s1_structured_output.py`

**Interfaces:**
- Consumes: `get_chat_model()` from `app/llm.py` (Task 3), `data/spikes/s3.json` (Task 8), `playbook/playbook.yaml` (Task 7).

- [ ] **Step 1: Read the free-tier limits**

Read the OpenRouter rate-limit docs and the model page for `nvidia/nemotron-3-ultra-550b-a55b:free`. Note requests per minute, requests per day, and whether `response_format` is still listed as unsupported. These go into the S1 record and spec checklist 12.A.

- [ ] **Step 2: Plain chat call**

Run: `cd backend && uv run python -c "from app.llm import get_chat_model; r = get_chat_model().invoke('Reply with the single word: pong'); print(repr(r.content)[:200])"`
Expected: content contains `pong`. A 401 means the key is wrong: the owner fixes `.env`. The agent does not open it.

- [ ] **Step 3: Write `spikes/s1_structured_output.py --mode function_calling|json_prompt`**

- Spike-local model: `class ClauseExtraction(BaseModel): found: bool; quote: str | None; reasoning: str`.
- Inputs: the first 2 contracts in `s3.json` × the 5 playbook clauses. Context: up to 3 pages whose text contains any of the clause's `query_terms`, otherwise the first 2 pages. Page text only, no gold.
- Prompt: system message with the clause title, the requirement, and "quote verbatim, or found=false".
- `function_calling`: `get_chat_model().with_structured_output(ClauseExtraction, method="function_calling", include_raw=True)`. A call is valid when `parsed` is a `ClauseExtraction` and `parsing_error is None`.
- `json_prompt`: prompt plus `PydanticOutputParser(pydantic_object=ClauseExtraction)` format instructions. A call is valid when the parse succeeds.
- Each call is wrapped in `try`/`except`. Exceptions (429, timeout, other) are counted by type and the loop goes on. Calls run one at a time. No LLM cache, so the 10 calls are real.
- Per call, record: valid, error type, latency, whether the raw message carries reasoning content, whether `quote` or `reasoning` contains `<think>` or similar markers (leak check), and, for information only, whether `quote` is a whitespace-normalized substring of the context.
- Write `data/spikes/s1_<mode>.json`, then print `valid N/10` and `PASS` when N ≥ 9.

- [ ] **Step 4: Run**

Run: `cd backend && uv run python -m spikes.s1_structured_output --mode function_calling`
Expected: `valid N/10`, where N ≥ 9 gives `PASS`, and zero leak flags.

- [ ] **Step 5 (only if Step 4 failed): Run the fallback mode for comparison**

Run: `cd backend && uv run python -m spikes.s1_structured_output --mode json_prompt`
Do not switch modes or models in code. Record both results for the owner's decision.

- [ ] **Step 6: Record S1**

Appendix `S1:`: model id, mode, valid N/10, error types, median latency, reasoning-leak result, verbatim rate (informational), and the free-tier limits from Step 1.

---

### Task 11: Phase 0 exit

**Files:**
- Modify: `docs/specs/2026-11-22-contract-review-mvp-design.md` (appendix S1 to S5, checklist 12.A and 12.B checkboxes only)

- [ ] **Step 1: Full checks**

Run: `cd backend && uv run pytest -v && uv run ruff check . && cd ../frontend && pnpm lint`
Expected: 17 passed (7 from Task 3, 10 from Task 6), ruff clean, lint clean.

- [ ] **Step 2: Secrets and data check**

Run: `git status --porcelain --ignored | grep -E '\.env$|data/' ; git ls-files --others --exclude-standard | grep -E '(^|/)\.env$|^data/' && echo LEAK || echo clean`
Expected: `.env` and `data/` show only as ignored (`!!`), and the last line prints `clean`.

- [ ] **Step 3: Fill in the appendix and tick checklist 12.B**

Fill in the `S1:` to `S5:` lines from Tasks 2/4 and 6 to 10, and tick only the 12.A and 12.B items that were verified. "Playbook draft reviewed by owner" is ticked only after the owner says so.

- [ ] **Step 4: List owner decisions needed before Phase 1**

In the completion report, list:
- S1 failed: choose JSON-in-prompt or another model.
- S4 fell back to 3.14: approve the edit to C7 and section 6.2.
- S2 label swaps, or corrections to spec section 4.
- S5 fallback used.
- Any spec text that the spikes showed to be wrong.

Do not edit spec sections outside the appendix and checklist without approval.

---

## Decisions (owner delegated the open questions on 2026-11-22)

The owner reviewed the plan and asked for the recommended answer to each question.

- **D1 (was Q1), `.gitignore`:** Remove `/docs`, so the spec, plans, and appendix are tracked. Keep `CLAUDE.md` ignored. It only contains `@AGENTS.md`, and AGENTS.md is the tracked file. Done in Task 1.
- **D2 (was Q2), clauses where absence is good for us:** Add the playbook field `absence_is: ok | missing`. Non-Compete and Termination For Convenience use `ok`; the other three use `missing`. Phase 0 only adds the field to the playbook draft (Task 7). Phase 1 rule, to be written into spec sections 6.3, 6.6, and AC-6 before Phase 1 starts: when not found and `absence_is: ok`, the status is `ok`, the examined candidates are recorded, and there is no suggestion.
- **D3 (was Q3), stance and rules:** Keep "commercial party reviewing a third-party agreement" and the Task 7 draft rules as they are. The owner may edit them later; that only changes the YAML.
- **D4 (was Q4), S1 inputs:** 10 different inputs (5 clauses × 2 contracts), as in Task 10.
- **D5 (was Q5), dense embeddings:** A spike-local adapter over `fastembed.TextEmbedding`. No `langchain-community` in Phase 0.
- **D6 (was Q6), LLM cache:** Deferred to Phase 1 planning. Not needed in Phase 0, because S1 runs uncached on purpose.
- **D7 (was Q7), spike code:** Keep `backend/spikes/` in the repo as evidence for the appendix. `app/` never imports it.
- **D8 (was Q8), Python 3.15 pre-release:** Use 3.15 final if `uv` offers it. If only a pre-release exists, try it; if any S4 check fails on it, fall back to 3.14 as in Task 2 Step 5.
- **D9 (was Q9), `ChatOpenRouter` unavailable or broken:** Fall back to LangChain `ChatOpenAI` with the OpenRouter base URL, still built only in `app/llm.py` (C1 holds). Record it in S1 or S4. Spec section 6.2 then needs an update before Phase 1.

## Still needs the owner during execution

- Approve the spec (AGENTS.md precondition), or say explicitly that Phase 0 may run against the DRAFT.
- Create `.env` with the OpenRouter key (Task 1 Step 5).
- Download and unzip CUAD into `data/cuad/` before Task 6.
- Approve any spec edit outside the appendix and checklist.
