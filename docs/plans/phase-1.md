# Phase 1: MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP from the spec. Upload a CUAD PDF, run a compiled LangGraph over 5 playbook clauses, return verified quotes with pages and highlights, let the lawyer accept, edit, or reject suggestions, and produce the first CUAD eval baseline. Exit when AC-1 to AC-13 pass.

**Architecture:** The backend is built in milestones:
- M1: pure building blocks (playbook, normalize/verify, PDF ingest, chunk index, DB).
- M2: the LangGraph pipeline, with every external dependency injected through a `GraphDeps` object, so tests run on a scripted LangChain fake chat model and a fake retriever.
- M3: FastAPI on top of a thin `services` module.
- M4: the eval CLI, which calls the same `services` functions as the API, so the score measures the real path.
- M5: the frontend, which only talks to the 5 endpoints of spec section 6.5.

The first eval number (M4) comes before any UI work (M5).

**Tech Stack:** Python 3.14, `uv`, FastAPI, SQLModel on PostgreSQL 16, PyMuPDF, LangChain (`langchain-openrouter` `ChatOpenRouter`), LangGraph (`StateGraph`, `Send`, compiled subgraph, `PostgresSaver`), `langchain-qdrant` hybrid retrieval with FastEmbed (`BAAI/bge-small-en-v1.5` dense, `Qdrant/bm25` sparse), Qdrant `v1.20.2`. Next.js 16 (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query, `react-pdf`.

**Spec:** `docs/specs/2026-11-22-contract-review-mvp-design.md`, approved 2026-11-22. Read it fully, including the Phase 0 appendix, before starting. Also read `docs/PROJECT_OVERVIEW.md`, and for frontend work `frontend/AGENTS.md`.

## Preconditions (blockers, check before Task 1)

- [x] The owner approved this plan on 2026-11-22 and accepted the recommended answers to Q2 to Q9 (see "Open questions").
- [ ] Open question Q1 (free-tier daily limit) is answered before Task 14 Step 6 (the baseline run). Nothing before that step needs real LLM calls, except the one manual smoke run in Task 12.
- [ ] Infra is up. Run: `docker compose up -d && docker compose exec postgres pg_isready -U postgres && curl -s http://localhost:6333/readyz`
  Expected: `accepting connections`, then `all shards are ready`.
- [ ] Baseline is green. Run: `cd backend && uv run pytest -q && uv run ruff check .`
  Expected: `27 passed`, `All checks passed!`.

## Global Constraints

- C1: Only LangChain chat model objects reach the LLM. `backend/app/llm.py` is the only place one is built (AC-8). No `openai`, `requests`, or `httpx` in `backend/app/`. `httpx` is allowed in tests as the FastAPI test client.
- C2: The pipeline is a compiled LangGraph `StateGraph`. No ad-hoc orchestration loops.
- C3: The model id comes only from `OPENROUTER_MODEL`. The string `nemotron` must not appear in `backend/app/`.
- C4: Only public CUAD contracts.
- C7: Python 3.14 (`requires-python = ">=3.14,<3.15"`).
- C8: App data in Postgres database `contract_review` and checkpoints in `contract_review_checkpoints`, both on host port 5434. Vectors in the Qdrant collection `contract_chunks`.
- AC-10: `backend/app/` never imports `evals` and never reads CUAD labels. `evals/` may import `app`.
- Gold labels never reach a prompt. Prompts never contain run ids or contract ids, so the LLM cache hits on reruns.
- A quote is shown only if `normalize(quote)` is a substring of `normalize(page_text)` for the cited page. Otherwise the status is `uncertain` and there is no quote.
- Statuses: `ok | risky | missing | uncertain`. Run statuses: `queued | running | completed | completed_with_errors | failed`. Decision states: `pending | accepted | edited | rejected`.
- Upload limits: PDF only, at most 20 MB, at most 100 pages, must have a text layer.
- `max_concurrency` = `LLM_MAX_CONCURRENCY` (default 2). `top_k` = 8. Chunks are 800 characters with 150 overlap, never crossing a page (S5).
- Qdrant payload keys are nested: filter on `metadata.contract_id` (S5, spec section 6.4).
- Structured output uses `with_structured_output(..., method="function_calling")` (S1). Parse only the tool call. Ignore reasoning content.
- Eval span match threshold: normalized token F1 ≥ 0.5 (`SPAN_MATCH_F1 = 0.5`).
- Never read, print, or commit `.env`. No commits unless the owner asks, and never a `Co-Authored-By` or any other AI attribution trailer (AGENTS.md).
- Frontend: Next.js 16 differs from older versions. Read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing each route or component (`frontend/AGENTS.md`).
- Unverified library APIs: check the current docs (context7) before writing the call. This covers `ChatOpenRouter` errors and retries, `Send`, compiled subgraphs as nodes, `get_stream_writer`, `PostgresSaver` with a pool, `QdrantVectorStore` on an existing collection, and `react-pdf` worker setup. Where the docs differ from this plan, follow the docs and note it in the task report.

## Test layout

- `uv run pytest` runs the default suite: no network, no Docker, no model downloads. It uses SQLite in memory for SQLModel, a scripted fake chat model, a fake retriever, and PDFs generated with PyMuPDF inside the tests. No binary fixtures.
- `uv run pytest -m integration` runs the tests that need Postgres, Qdrant, and the FastEmbed models (downloaded once to `data/models`). Register the marker in `pyproject.toml` with `addopts = "-m 'not integration'"`, so the default run excludes them.
- The task reports and the completion report must say which suite ran.

## Review Focus

1. **The LLM quotes a tiny fragment.** For example, `"state."` (the S3 CUAD fragment) trivially "verifies". Expected: quotes shorter than `MIN_QUOTE_WORDS = 5` fail verification and get the retry feedback. Test: `test_verify_rejects_short_quote` (Task 3).
2. **A quote crosses a page break, or the PDF hyphenates a word across lines** (`compe-\ntition`). Expected: a single-page quote verifies after normalization, a cross-page quote fails (single-page rule), and the finding ends `uncertain`, never with a quote that is not on the cited page. Tests: `test_verify_rejects_cross_page_quote` and `test_normalize_joins_line_break_hyphenation` (Task 3).
3. **One clause's LLM call keeps failing** (429, timeout, or invalid tool call). Expected: that clause is `uncertain` with an `error`, the other 4 findings are complete, and the run ends `completed_with_errors`, not `failed`. Test: `test_llm_error_on_one_clause_yields_uncertain` (Task 9), AC-12.
4. **A contract yields no candidates** (all chunks empty, or retrieval returns nothing). Expected: no LLM extraction call. The finding follows `absence_is` (`missing` with a suggestion, or `ok` without one) and records an empty candidate list. Test: `test_no_candidates_skips_extract` (Task 8).
5. **The eval sample contains a CUAD contract the app would reject** (more than 100 pages, more than 20 MB, or no text layer). Expected: the sampler excludes it before sampling and the report shows the excluded count, so a sample of N always means N analyzed contracts. Test: `test_sampler_excludes_oversized_contracts` (Task 13).

---

## Milestone M1: Building blocks

### Task 1: Apply the approved spec changes, config, and dependencies

**Files:**
- Modify: `docs/specs/2026-11-22-contract-review-mvp-design.md` (only the edits listed in Step 1)
- Modify: `.env.example`, `backend/app/config.py`, `backend/pyproject.toml`, `backend/tests/conftest.py`, `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.llm_cache_path: Path | None`. Default `Path("data/llm_cache.db")`, resolved against `REPO_ROOT` like `data_dir`. An empty env value means `None`, which turns the cache off.

- [ ] **Step 1: Spec edits that this plan depends on (from the open questions, as answered)**
  - Section 6.4: add the column `verify_failures` (int, 0 to 2) to `Finding` (Q3).
  - Section 8: add a diagnostic metric "Retrieval hit rate: among gold-present clauses, the share where any candidate page contains a gold span" (Q4).
  - Section 6.5: add "`PUT /api/findings/{id}/decision` returns 422 for a finding without suggested wording" (Q5).
  - Section 7: "SQLiteCache from `langchain-community`", or the Q2 alternative.

  Verify: `git diff --stat docs/specs` shows only the spec file. Reread each edited paragraph.

- [ ] **Step 2: Dependencies**

  Run: `cd backend && uv add langchain-community` (only if Q2 = yes).
  Verify: `uv run python -c "from langchain_community.cache import SQLiteCache; print('ok')"` prints `ok`.

- [ ] **Step 3: Write failing tests in `tests/test_config.py`**
  - `test_llm_cache_path_resolves_to_repo_root`: with `LLM_CACHE_PATH=./data/llm_cache.db`, `s.llm_cache_path == REPO_ROOT / "data" / "llm_cache.db"`.
  - `test_empty_llm_cache_path_disables_cache`: with `LLM_CACHE_PATH=""`, `s.llm_cache_path is None`.

  Add `LLM_CACHE_PATH` to the `ENV` dict in `conftest.py`. Run `uv run pytest tests/test_config.py -v`. Expected: the 2 new tests FAIL.

- [ ] **Step 4: Implement**

  Add the field and validator. Append `LLM_CACHE_PATH=./data/llm_cache.db` to `.env.example`, and tell the owner to add the same line to `.env` (the agent does not open it). Add the pytest marker config from "Test layout".
  Run: `uv run pytest -q`. Expected: `29 passed`.

### Task 2: Playbook loader (`app/playbook.py`)

**Files:**
- Create: `backend/app/playbook.py`
- Test: `backend/tests/test_playbook.py`

**Interfaces:**
- Produces:
  - `class ClauseRule(BaseModel)`, with `model_config = ConfigDict(extra="forbid", frozen=True)`. Fields: `id: str`, `cuad_label: str`, `title: str`, `query_terms: list[str]` (min 1), `requirement: str`, `acceptable: list[str]`, `red_flags: list[str]`, `preferred_wording: str`, `severity_if_missing: Literal["low", "medium", "high"]`, `absence_is: Literal["ok", "missing"]`.
  - `class Playbook(BaseModel)`, with `extra="forbid"`. Fields: `version: Literal[1]`, `stance: str`, `clauses: list[ClauseRule]` (1 to 5 entries, unique `id`s).
  - `PLAYBOOK_PATH = REPO_ROOT / "playbook" / "playbook.yaml"`
  - `load_playbook(path: Path = PLAYBOOK_PATH) -> Playbook`. Raises `PlaybookError(ValueError)` with the file path and the pydantic error text.
  - `playbook_hash(path: Path = PLAYBOOK_PATH) -> str`: the first 12 hex characters of the SHA-256 of the file bytes.
  - `Playbook.clause(clause_id: str) -> ClauseRule` raises `KeyError` for an unknown id.

- [ ] **Step 1: Write failing tests.** Each test writes YAML to `tmp_path`. Copy the real file and mutate it.
  - `test_real_playbook_loads`: `load_playbook()` has 5 clauses, the ids equal the 5 ids in `playbook/playbook.yaml`, and `non_compete.absence_is == "ok"`.
  - `test_unknown_key_rejected`: an extra key `notes:` on one clause raises `PlaybookError`.
  - `test_missing_key_rejected`: removing `absence_is` raises `PlaybookError`.
  - `test_bad_severity_rejected`: `severity_if_missing: critical` raises.
  - `test_duplicate_ids_rejected`, `test_more_than_five_clauses_rejected`, `test_empty_query_terms_rejected`.
  - `test_hash_changes_with_content`: two files that differ by one character give different 12-character hashes, and the same file gives a stable hash.
  - `test_playbook_labels_exist_in_cuad`: `{c.cuad_label for c in load_playbook().clauses} == set(evals.cuad.TARGET_LABELS)`. This test lives under `tests/`, which may import `evals`.

- [ ] **Step 2:** Run `uv run pytest tests/test_playbook.py -v`. Expected: FAIL with `ModuleNotFoundError: No module named 'app.playbook'`.
- [ ] **Step 3:** Implement as given in Interfaces, using `yaml.safe_load`.
- [ ] **Step 4:** Run the same command. Expected: 9 passed. Then `uv run ruff check .`.

### Task 3: Normalization and quote verification (`app/ingest/normalize.py`)

**Files:**
- Create: `backend/app/ingest/__init__.py`, `backend/app/ingest/normalize.py`
- Test: `backend/tests/ingest/__init__.py`, `backend/tests/ingest/test_normalize.py`

**Interfaces:**
- Produces:
  - `normalize(text: str) -> str`. The steps, in order:
    1. Unicode NFKC.
    2. Remove the soft hyphen U+00AD.
    3. Join line-break hyphenation: `(\w)-\s*\n\s*(\w)` becomes `\1\2`.
    4. Map curly single and double quotes to `'` and `"`, and en dash, em dash, and U+2212 to `-`.
    5. Collapse whitespace to one space.
    6. Strip and casefold.
  - `MIN_QUOTE_WORDS = 5`
  - `@dataclass(frozen=True) class VerifyResult: ok: bool; page: int | None; reason: str | None`, with a 1-based `page`.
  - `verify_quote(quote: str, pages: Sequence[str]) -> VerifyResult` returns the first page whose normalized text contains the normalized quote. Reasons: `"too short"`, `"not found verbatim on any single page"`, `"empty quote"`.
  - `token_f1(a: str, b: str) -> float`: token-level F1 over `normalize(x).split()`, with multiset overlap as in SQuAD. Used by the eval.

- [ ] **Step 1: Write failing tests**
  - `test_normalize_collapses_whitespace_and_case`: `normalize("This  Agreement\n\tIS") == "this agreement is"`
  - `test_normalize_maps_quotes_and_dashes`: `normalize("“Term” – ‘x’") == "\"term\" - 'x'"`
  - `test_normalize_removes_soft_hyphen`: `normalize("compe­tition") == "competition"`
  - `test_normalize_joins_line_break_hyphenation`: `normalize("compe-\ntition") == "competition"`, and `normalize("well-known") == "well-known"`
  - `test_verify_finds_quote_on_its_page`: pages `["intro text", "This Agreement shall be governed by the laws of Delaware."]` and a quote with different spacing and case give `VerifyResult(True, 2, None)`
  - `test_verify_returns_first_matching_page`
  - `test_verify_rejects_missing_quote`: `ok is False`, `reason == "not found verbatim on any single page"`
  - `test_verify_rejects_short_quote`: `"governed by Delaware law"` (4 words) gives `reason == "too short"`
  - `test_verify_rejects_cross_page_quote`: the first half of the sentence ends page 1 and the second half starts page 2. Gives `ok is False`.
  - `test_verify_rejects_empty_quote`: `""` and `"   "` give `reason == "empty quote"`
  - `test_token_f1`: identical gives `1.0`, disjoint gives `0.0`, `token_f1("a b c d", "a b")` is approximately `0.6667`

- [ ] **Step 2:** Run `uv run pytest tests/ingest/test_normalize.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement as given in Interfaces.
- [ ] **Step 4:** Run the same command. Expected: 11 passed.

### Task 4: PDF validation, page text, and highlight rectangles (`app/ingest/pdf.py`)

**Files:**
- Create: `backend/app/ingest/pdf.py`
- Test: `backend/tests/ingest/test_pdf.py`, and a `make_pdf` fixture in `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `normalize` (Task 3).
- Produces:
  - `MAX_BYTES = 20 * 1024 * 1024`, `MAX_PAGES = 100`, `MIN_TEXT_CHARS_PER_PAGE = 100`. Text layer rule: the mean non-whitespace characters per page must be at least 100.
  - `class PdfRejected(Exception)`. Attributes: `status_code: int` and `detail: str`. Codes: 415 not a PDF, 413 too large, 422 too many pages, 422 no text layer.
  - `parse_pdf(data: bytes) -> list[str]` returns the page texts in page order. It checks, in order: size, then the `%PDF-` magic bytes and a successful `pymupdf.open(stream=...)`, then page count, then the text layer.
  - `save_contract_files(contract_dir: Path, data: bytes, pages: list[str]) -> Path`. It writes `original.pdf` and `pages.json` (`[{"page": 1, "text": "..."}, ...]`) and returns the PDF path.
  - `load_pages(contract_dir: Path) -> list[str]`
  - `BBox = tuple[float, float, float, float]`, in PDF points, origin top left.
  - `find_quote_rects(pdf_path: Path, page: int, quote: str) -> list[BBox]` runs `page.search_for(quote)` first, then word-level matching of consecutive `get_text("words")` tokens under `normalize`, ported from `spikes/s3_pymupdf.py::word_rects` (it returns the rectangles, not a count). It returns `[]` when neither matches. It never raises for a not-found quote.
- Test fixture: `make_pdf(pages: list[str], *, blank: bool = False) -> bytes` builds a PDF in memory with `pymupdf.open()`, `new_page()`, and `insert_textbox`.

- [ ] **Step 1: Write failing tests**
  - `test_parse_returns_page_texts`: 3 pages of 300-character text give 3 strings, and page 2 contains its marker word.
  - `test_rejects_non_pdf`: `b"hello"` gives `PdfRejected` with `status_code == 415`.
  - `test_rejects_oversized`: `b"%PDF-" + b"0" * (MAX_BYTES + 1)` gives 413, before any parsing.
  - `test_rejects_too_many_pages`: 101 pages give 422, and `detail` mentions `100`.
  - `test_rejects_scanned_pdf`: 2 blank pages give 422, and `detail` mentions the text layer.
  - `test_rejects_corrupt_pdf`: `b"%PDF-1.7 garbage"` gives 415.
  - `test_save_and_load_pages_roundtrip`: `tmp_path` holds `original.pdf` and `pages.json`, and `load_pages` returns the same list.
  - `test_find_quote_rects_single_line`: a short sentence gives at least 1 rect, and every rect lies inside the page bounds.
  - `test_find_quote_rects_multi_line_falls_back_to_words`: a long sentence wrapped by `insert_textbox` gives at least 2 rects.
  - `test_find_quote_rects_not_found_returns_empty`

- [ ] **Step 2:** Run `uv run pytest tests/ingest/test_pdf.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as given in Interfaces.
- [ ] **Step 4:** Run the same command. Expected: 10 passed.

### Task 5: Chunking and the Qdrant hybrid index (`app/ingest/chunk.py`, `app/ingest/index.py`)

**Files:**
- Create: `backend/app/ingest/chunk.py`, `backend/app/ingest/index.py`
- Test: `backend/tests/ingest/test_chunk.py`, `backend/tests/integration/__init__.py`, `backend/tests/integration/test_index.py`

**Interfaces:**
- Produces:
  - `CHUNK_CHARS = 800`, `CHUNK_OVERLAP = 150`
  - `@dataclass(frozen=True) class Chunk: chunk_id: str; page: int; text: str`. `chunk_id` is `f"{page}-{i}"`, as in S5.
  - `chunk_pages(pages: Sequence[str]) -> list[Chunk]`: per-page windows of 800 characters with 150 overlap. It skips empty or whitespace-only pieces and never crosses a page.
  - `class Candidate(BaseModel)`: `chunk_id: str`, `page: int`, `text: str`. This is what `retrieve` records.
  - `class Retriever(Protocol)`: `def search(self, contract_id: str, query: str, k: int) -> list[Candidate]`.
  - `COLLECTION = "contract_chunks"`, `DENSE_MODEL = "BAAI/bge-small-en-v1.5"`, `SPARSE_MODEL = "Qdrant/bm25"`.
  - `class FastEmbedDense(Embeddings)`: moved from `spikes/s5_hybrid.py`. It is the D5 adapter, with no `langchain-community` embeddings.
  - `class ChunkIndex`, which implements `Retriever`:
    - `__init__(self, client: QdrantClient, cache_dir: Path)` creates the collection if it is missing: a 384-dimension cosine dense vector, plus the sparse vector name that `langchain-qdrant` expects (S5: `langchain-sparse`). It also adds a keyword payload index on `metadata.contract_id`. It wraps a `QdrantVectorStore(..., retrieval_mode=RetrievalMode.HYBRID)`.
    - `add_contract(contract_id: str, chunks: list[Chunk]) -> int` returns the number of points added. The metadata is `{contract_id, page, chunk_id}`.
    - `search(...)` filters on `metadata.contract_id` and returns at most `k` `Candidate`s in rank order.
    - `delete_contract(contract_id: str) -> None`.

- [ ] **Step 1: Write failing unit tests (`test_chunk.py`)**
  - `test_short_page_is_one_chunk`
  - `test_long_page_windows_overlap`: a 2000-character page gives chunks starting at 0, 650, and 1300, and chunk 1 starts with the last 150 characters of chunk 0's window.
  - `test_chunks_never_cross_pages`: every chunk's text is a substring of `pages[chunk.page - 1]`.
  - `test_blank_page_yields_no_chunks`
  - `test_chunk_ids_unique`

- [ ] **Step 2:** Run `uv run pytest tests/ingest/test_chunk.py -v`. Expected: FAIL. Implement `chunk.py`. Rerun. Expected: 5 passed.

- [ ] **Step 3: Write the integration test (`tests/integration/test_index.py`, `@pytest.mark.integration`)**

  It uses a test collection name `contract_chunks_test`, recreated per test module. Add a `collection_name` keyword argument to `ChunkIndex.__init__` (default `COLLECTION`) for this.
  - `test_hybrid_search_returns_page_of_clause`: contract A has 4 synthetic pages, with a governing law sentence ("construed in accordance with the laws of the State of New York") on page 3. The query is the joined real `governing_law.query_terms`. Expected: page 3 is in the top 8.
  - `test_search_is_filtered_by_contract`: contracts A and B. Every result for A has a candidate `chunk_id` from A only. Check this through a payload lookup.
  - `test_delete_contract_removes_points`

- [ ] **Step 4:** Implement `index.py`.
  Run: `uv run pytest -m integration tests/integration/test_index.py -v`. Expected: 3 passed. The first run downloads the models to `data/models`.

### Task 6: Database (`app/db.py`, `app/models.py`)

**Files:**
- Create: `backend/app/db.py`, `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces (SQLModel `table=True`, ids are `str(uuid4())`, JSON columns use `sa_column=Column(JSON)`, times are UTC-aware):
  - `Contract(id, filename, path, page_count, uploaded_at)`
  - `Run(id, contract_id FK, status, started_at: datetime | None, finished_at: datetime | None, model: str, playbook_hash: str)`
  - `Finding(id, run_id FK, clause_id, status, severity: str | None, quote: str | None, page: int | None, bboxes_json: list, candidates_json: list, playbook_rule: str, issues_json: list, rationale: str | None, suggestion_text: str | None, suggestion_explanation: str | None, error: str | None, verify_failures: int = 0)`
  - `Decision(finding_id PK FK, state, edited_text: str | None, decided_at: datetime)`
  - `RunStatus`, `FindingStatus`, `DecisionState` as `StrEnum`s with the exact values from Global Constraints.
  - `make_engine(url: str) -> Engine`. For `sqlite://` it uses `StaticPool` and `check_same_thread=False`.
  - `init_db(engine) -> None` runs `create_all` (spec decision 14: no Alembic in the MVP).
  - `mark_stale_runs_failed(session) -> int` sets every `queued` or `running` run to `failed` with `finished_at=now`, and returns the count. It is called at startup (Q7).

- [ ] **Step 1: Write failing tests (SQLite in memory)**
  - `test_create_all_and_roundtrip_finding`: the JSON columns round-trip lists of dicts.
  - `test_decision_primary_key_is_finding_id`: inserting a second `Decision` for the same finding raises `IntegrityError`.
  - `test_mark_stale_runs_failed`: given runs in `running`, `queued`, and `completed`, it returns `2`, and the `completed` run is unchanged.

- [ ] **Step 2:** Run `uv run pytest tests/test_models.py -v`. Expected: FAIL. Implement. Rerun. Expected: 3 passed.

- [ ] **Step 3: Postgres check (integration)**

  Add `tests/integration/test_db.py::test_create_all_on_postgres` (`@pytest.mark.integration`). It runs `init_db` on `settings.database_url` and checks that `inspect(engine).get_table_names()` contains `contract`, `run`, `finding`, and `decision`.
  Run: `uv run pytest -m integration tests/integration/test_db.py -v`. Expected: 1 passed.

---

## Milestone M2: LangGraph pipeline

### Task 7: Schemas, the scripted fake model, and the structured call helper

**Files:**
- Create: `backend/app/graph/__init__.py`, `backend/app/graph/state.py`, `backend/app/graph/structured.py`
- Create: `backend/tests/fakes.py`
- Test: `backend/tests/graph/__init__.py`, `backend/tests/graph/test_structured.py`

**Interfaces:**
- Produces in `state.py`:
  - LLM output schemas, each with a docstring (it becomes the tool description):
    - `ClauseExtraction(found: bool, quote: str | None, reasoning: str)`
    - `ClauseAssessment(compliant: bool, issues: list[str], rationale: str)`
    - `ClauseSuggestion(text: str, explanation: str)`
  - `class FindingResult(BaseModel)`. It mirrors the `Finding` columns except `id` and `run_id`: `clause_id`, `status`, `severity`, `quote`, `page`, `bboxes`, `candidates`, `playbook_rule`, `issues`, `rationale`, `suggestion_text`, `suggestion_explanation`, `error`, `verify_failures`.
  - `class ReviewState(TypedDict)`: `run_id: str`, `contract_id: str`, `clause_ids: list[str]`, `findings: Annotated[list[FindingResult], operator.add]`, `status: str | None`.
  - `class ClauseState(TypedDict, total=False)`: `contract_id`, `clause_id`, `candidates: list[Candidate]`, `extraction: ClauseExtraction | None`, `feedback: str | None`, `verify_failures: int`, `page: int | None`, `bboxes: list[BBox]`, `assessment: ClauseAssessment | None`, `suggestion: ClauseSuggestion | None`, `error: str | None`, `findings: Annotated[list[FindingResult], operator.add]`.
  - `@dataclass(frozen=True) class GraphDeps`: `model: BaseChatModel`, `retriever: Retriever`, `playbook: Playbook`, `contract_dir: Callable[[str], Path]`, `save_findings: Callable[[str, list[FindingResult]], None]`, `top_k: int = 8`.
- Produces in `structured.py`:
  - `class StructuredCallError(Exception)`
  - `invoke_structured(model: BaseChatModel, schema: type[T], messages: list[BaseMessage]) -> T`. It uses `model.with_structured_output(schema, method="function_calling", include_raw=True)`, wrapped with `.with_retry(stop_after_attempt=3, wait_exponential_jitter=True, retry_if_exception_type=TRANSIENT_ERRORS)`.
    - If `parsing_error` is set, or `parsed` is `None`, it retries once with an extra `HumanMessage` that holds the validation error text (spec section 7).
    - A second parse failure, or exhausted transient retries, raises `StructuredCallError`, with the original error type and message in its text.
  - `TRANSIENT_ERRORS: tuple[type[Exception], ...]`: the rate-limit, timeout, and 5xx exception classes that `langchain-openrouter` raises. Find them in its docs or source at execution. Fall back to `(TimeoutError, ConnectionError)` if no specific classes exist, and record that.
- Produces in `tests/fakes.py`:
  - `class ScriptedChatModel(BaseChatModel)`, a LangChain fake chat model. It is built with `responder: Callable[[str, list[BaseMessage]], dict | Exception]`.
    - `bind_tools(tools, **kwargs)` returns a copy that remembers the single tool's name.
    - `_generate` calls `responder(tool_name, messages)`. A returned dict becomes `AIMessage(content="", tool_calls=[{"name": tool_name, "args": dict, "id": "call-1"}])`. A returned exception is raised.
    - It counts calls in `self.calls: list[tuple[str, list[BaseMessage]]]` (a private attribute).
  - `class FakeRetriever`: `Retriever` over a `dict[str, list[Candidate]]` keyed by clause query substring or contract.
  - `def clause_of(messages) -> str`: reads the `clause_id=` marker that prompts put in the system message. The prompt carries the clause id, which is not a contract id, so the cache is unaffected.

- [ ] **Step 1: Write failing tests (`test_structured.py`)**
  - `test_returns_parsed_object`: the responder returns `{"found": True, "quote": "x y z a b", "reasoning": "r"}`. Gives a `ClauseExtraction` with `found is True`, and exactly 1 call.
  - `test_retries_once_with_validation_feedback`: the first response is `{"found": "maybe"}` (invalid), the second is valid. Gives a parsed result, 2 calls, and the second call's last message contains the validation error text.
  - `test_second_parse_failure_raises`: two invalid responses give `StructuredCallError`.
  - `test_transient_error_is_retried`: the first call raises `TimeoutError`, the second is valid. Gives success. Patch the wait to zero.
  - `test_persistent_transient_error_raises`: 3 `TimeoutError`s give `StructuredCallError` matching `TimeoutError`.

- [ ] **Step 2:** Run `uv run pytest tests/graph/test_structured.py -v`. Expected: FAIL. Implement. Rerun. Expected: 5 passed.

### Task 8: Clause subgraph (`app/graph/nodes/`, `app/graph/clause_graph.py`)

**Files:**
- Create: `backend/app/graph/prompts.py`, `backend/app/graph/nodes/__init__.py`, `retrieve.py`, `extract.py`, `verify.py`, `locate.py`, `assess.py`, `suggest.py`, `emit.py` (all under `backend/app/graph/nodes/`), and `backend/app/graph/clause_graph.py`
- Test: `backend/tests/graph/test_clause_graph.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 4, 5, and 7.
- Produces:
  - `prompts.py`: `extract_messages(rule, candidates, feedback) -> list[BaseMessage]`, `assess_messages(rule, stance, quote)`, `suggest_messages(rule, stance, quote | None)`.
    - The system message starts with `clause_id=<id>`.
    - Candidates are rendered as `[page N] text`.
    - There are no run or contract ids, and no gold.
    - The extract prompt requires an exact quote copied from one passage, or `found=false`.
  - Each node is `def node(state: ClauseState, *, deps: GraphDeps) -> dict`, bound with `functools.partial`.
  - Every node first calls `get_stream_writer()({"clause_id": ..., "step": "<node name>"})`. The `emit` node sends `"step": "done"`.
  - `build_clause_graph(deps: GraphDeps) -> CompiledStateGraph` (no checkpointer: the parent graph owns it).

  Nodes and edges, exactly:

  | Node | Does | Next |
  |---|---|---|
  | `retrieve` | `deps.retriever.search(contract_id, " ".join(rule.query_terms), deps.top_k)`, stores `candidates` | `extract` |
  | `extract` | If there are no candidates: `extraction=ClauseExtraction(found=False, quote=None, reasoning="no candidates")` and no LLM call. Otherwise `invoke_structured`. `StructuredCallError` sets `error` | `emit` if error; `suggest` if not found and `absence_is == "missing"`; `emit` if not found and `absence_is == "ok"`; else `verify` |
  | `verify` | `verify_quote(quote, load_pages(...))`. On failure: `verify_failures += 1` and `feedback = f"quote not found verbatim ({reason}); copy the exact text from one passage"` | `locate` if ok; `extract` if failed and `verify_failures < 2`; `emit` if failed and `verify_failures == 2` |
  | `locate` | `page` from verify, `bboxes = find_quote_rects(...)` | `assess` |
  | `assess` | `invoke_structured(ClauseAssessment)` | `emit` if error or compliant; `suggest` otherwise |
  | `suggest` | `invoke_structured(ClauseSuggestion)` with the quote, or `None` for missing | `emit` |
  | `emit` | Builds one `FindingResult` from the status rules below and returns `{"findings": [result]}` | END |

  Status rules in `emit` (spec section 6.3 as amended):
  - `error` set: `uncertain`, with `error` and no quote. Severity is `None`.
  - Extractor found, and verify failed twice: `uncertain`, no quote, `verify_failures=2`.
  - Not found and `absence_is == "missing"`: `missing`, with `severity = rule.severity_if_missing`, candidates, and the suggestion.
  - Not found and `absence_is == "ok"`: `ok`, with candidates, no quote, and no suggestion.
  - Found, verified, and compliant: `ok`, with the quote, page, and bboxes.
  - Found, verified, and not compliant: `risky`, with the quote, page, bboxes, issues, rationale, and the suggestion.
  - A suggest error after a successful assess: `risky` or `missing` is kept, `suggestion_text=None`, `error` is set. This counts as an error for the run status.

  `candidates` is always recorded, for every status (AC-5).

- [ ] **Step 1: Write failing tests**

  A `deps` fixture provides the real playbook, a `FakeRetriever`, `contract_dir` pointing to `tmp_path` with `pages.json` and a generated PDF, a `ScriptedChatModel`, and `save_findings` as a list collector. Each test invokes `build_clause_graph(deps).invoke({"contract_id": "c1", "clause_id": ..., "verify_failures": 0})`.
  - `test_found_verified_compliant_is_ok`: status `ok`, quote set, page correct, `len(bboxes) >= 1`, `suggestion_text is None`.
  - `test_found_verified_non_compliant_is_risky_with_suggestion`
  - `test_not_found_absence_missing_is_missing_with_suggestion`: on `governing_law`, gives `severity == "medium"`, `suggestion_text` set, `candidates` non-empty.
  - `test_not_found_absence_ok_is_ok_without_suggestion`: on `non_compete`, gives `ok`, `quote is None`, `suggestion_text is None`, and `candidates` non-empty. The responder must never be called with the `ClauseSuggestion` tool.
  - `test_verify_retry_then_success`: the first extraction quote is invented, the second is real. Gives `ok` or `risky`, `verify_failures == 1`, and the second extract call contains the feedback text.
  - `test_verify_fails_twice_is_uncertain`: `uncertain`, `quote is None`, `verify_failures == 2`, and exactly 2 extract calls.
  - `test_no_candidates_skips_extract`: an empty retriever result on `governing_law` gives `missing` with `candidates == []`, and no `ClauseExtraction` call.
  - `test_llm_error_in_assess_is_uncertain`: the responder raises `TimeoutError` for `ClauseAssessment` every time. Gives `uncertain` with `"TimeoutError"` in `error`.
  - `test_quote_is_substring_of_cited_page` (AC-3 property): for every test above that returns a quote, `normalize(quote) in normalize(pages[page - 1])`. Implement as a helper asserted at the end of each test.
  - `test_progress_events_emitted`: `graph.stream(..., stream_mode="custom")` yields steps in the order `retrieve, extract, verify, locate, assess, done` for the `ok` path.

- [ ] **Step 2:** Run `uv run pytest tests/graph/test_clause_graph.py -v`. Expected: FAIL. Implement. Rerun. Expected: 10 passed.

### Task 9: Review graph (`app/graph/review_graph.py`)

**Files:**
- Create: `backend/app/graph/review_graph.py`
- Test: `backend/tests/graph/test_review_graph.py`

**Interfaces:**
- Consumes: Task 8.
- Produces:
  - `build_review_graph(deps: GraphDeps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph`, with these nodes:
    - `ingest`: raises `ContractUnreadable` if `pages.json` is missing or empty, so the run fails early.
    - `dispatch`: a conditional edge from `ingest` that returns `[Send("review_clause", {"contract_id", "clause_id", "verify_failures": 0}) for each clause_id]`.
    - `review_clause`: the compiled clause subgraph, added as a node.
    - `finalize`: calls `deps.save_findings(run_id, findings)` and returns `{"status": "completed_with_errors" if any finding has an error else "completed"}`.
  - `run_config(run_id: str, max_concurrency: int) -> RunnableConfig` returns `{"configurable": {"thread_id": run_id}, "max_concurrency": max_concurrency}`.
  - `class ContractUnreadable(Exception)`.

- [ ] **Step 1: Write failing tests** (with `InMemorySaver`)
  - `test_returns_exactly_five_findings_one_per_clause` (AC-2): 5 findings, `{f.clause_id for f in findings} == set(playbook ids)`, and every status is in the 4 allowed values. Also checks that `save_findings` was called once with the same 5.
  - `test_llm_error_on_one_clause_yields_uncertain` (AC-12): the responder raises `TimeoutError` for every call whose `clause_of(messages) == "cap_on_liability"`. Gives 5 findings, `cap_on_liability` is `uncertain` with an error, the other 4 are not `uncertain`, and the final `status == "completed_with_errors"`.
  - `test_missing_findings_have_candidates_and_suggestion` (AC-5, AC-6): across a scripted mix, every `missing` finding has `candidates` and `suggestion_text`, and no `ok` finding has `suggestion_text`.
  - `test_unreadable_contract_raises`: no `pages.json` gives `ContractUnreadable` from `invoke`.
  - `test_checkpoint_saved_under_run_id`: after `invoke`, `graph.get_state(run_config("r1", 2)).values["status"] == "completed"`.
  - `test_custom_stream_reaches_parent`: `graph.stream(..., stream_mode="custom", subgraphs=True)` yields at least one `{"step": "done"}` event per clause, 5 in total.

- [ ] **Step 2:** Run `uv run pytest tests/graph -v`. Expected: the new tests FAIL. Implement. Rerun. Expected: all graph tests pass.

### Task 10: LLM factory hardening and the boundary gates (AC-8, AC-10)

**Files:**
- Modify: `backend/app/llm.py`
- Test: `backend/tests/test_llm.py`, `backend/tests/test_boundaries.py`

**Interfaces:**
- Produces: `get_chat_model(settings=None)` additionally sets `cache=SQLiteCache(database_path=str(settings.llm_cache_path))` when `llm_cache_path` is not `None`, and no cache otherwise. Temperature, max tokens, timeout, and retries are unchanged.

- [ ] **Step 1: Write failing tests**
  - `test_llm.py::test_cache_enabled_when_path_set`: `isinstance(m.cache, SQLiteCache)`, using a path in `tmp_path`.
  - `test_llm.py::test_cache_disabled_when_path_empty`: `m.cache is None`.
  - `test_boundaries.py::test_no_direct_http_or_openai_in_app` (AC-8): an AST walk over `backend/app/**/*.py` finds no import of `openai`, `requests`, or `httpx`, and no string containing `openrouter.ai`.
  - `test_boundaries.py::test_chat_model_constructed_only_in_llm_py`: the regex `\bChat[A-Z]\w*\(` matches only in `app/llm.py`.
  - `test_boundaries.py::test_model_name_not_hard_coded` (C3): `"nemotron"` does not appear in any file under `backend/app/`.
  - `test_boundaries.py::test_app_never_imports_evals` (AC-10): no `evals` import in the AST of any `app/` file, and the strings `CUAD_v1` and `cuad` (case-insensitive) do not appear under `app/`.
  - `test_boundaries.py::test_importing_app_does_not_load_evals`: a subprocess runs `uv run python -c "import app.main, sys; assert not [m for m in sys.modules if m.split('.')[0] == 'evals']"` and exits 0. This test needs `app.main` from Task 11. Mark it `xfail(strict=True)` until then and remove the marker in Task 11.

- [ ] **Step 2:** Run `uv run pytest tests/test_llm.py tests/test_boundaries.py -v`. Expected: the cache tests FAIL, the gate tests pass on today's code, and the subprocess test XFAILs. Implement. Rerun. Expected: all pass except the strict xfail.

---

## Milestone M3: API

### Task 11: Services and FastAPI app

**Files:**
- Create: `backend/app/services.py`, `backend/app/progress.py`, `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/api/contracts.py`, `backend/app/api/runs.py`, `backend/app/api/findings.py`, `backend/app/api/schemas.py`
- Test: `backend/tests/api/__init__.py`, `backend/tests/api/conftest.py`, `backend/tests/api/test_contracts.py`, `backend/tests/api/test_runs.py`, `backend/tests/api/test_findings.py`

**Interfaces:**
- Produces:
  - `progress.py`: `class ProgressStore`, a thread-safe in-memory store (Q7). Methods: `set(run_id, clause_id, step)`, `get(run_id) -> dict[str, str]`, `clear(run_id)`.
  - `services.py`:
    - `@dataclass class Services`: `settings`, `engine`, `index: Retriever` with `add_contract`, `model: BaseChatModel`, `checkpointer`, `playbook`, `playbook_hash: str`, `progress: ProgressStore`.
    - `build_services(settings) -> Services`. The real wiring: `make_engine` + `init_db` + `mark_stale_runs_failed`, `ChunkIndex(QdrantClient(url=...), settings.data_dir / "models")`, `get_chat_model()`, `PostgresSaver` over a `psycopg_pool.ConnectionPool(settings.checkpoint_db_url, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})` with `.setup()`, and `load_playbook()`.
    - `contract_dir(settings, contract_id) -> Path` returns `settings.data_dir / "contracts" / contract_id`.
    - `ingest_contract(svc, filename: str, data: bytes) -> Contract` runs `parse_pdf`, then `save_contract_files`, then `chunk_pages`, then `index.add_contract`, then inserts the `Contract` row. If indexing fails, it removes the contract dir and the DB row is not written.
    - `create_run(svc, contract_id) -> Run` creates a `queued` run. It raises `LookupError` for an unknown contract.
    - `execute_run(svc, run_id) -> None` sets the run to `running`, then iterates `build_review_graph(deps, svc.checkpointer).stream(input, run_config(...), stream_mode="custom", subgraphs=True)` and writes each event into `progress`. At the end it sets `status` and `finished_at` from the final graph state. Any exception sets the run to `failed` and logs it. It never raises out of the background task.
    - `save_findings(svc, run_id, results)` inserts the `Finding` rows plus a `Decision(state="pending")` for each finding that has `suggestion_text`.
    - `get_run_view(svc, run_id) -> RunView` and `set_decision(svc, finding_id, state, edited_text) -> Decision`.
  - `api/schemas.py`: `UploadResponse{contract_id, page_count}`, `AnalyzeResponse{run_id}`, `FindingView` (the `Finding` fields plus `decision: DecisionView | None`), `RunView{run_id, contract_id, status, model, started_at, finished_at, progress: dict[str, str], findings: list[FindingView]}`, `DecisionIn{state: Literal["accepted", "edited", "rejected"], edited_text: str | None}`.
    - `findings` is empty until the status is `completed`, `completed_with_errors`, or `failed`.
    - The `DecisionIn` validator: `edited` requires a non-empty `edited_text`; `accepted` and `rejected` set `edited_text` to `None`.
  - `main.py`: `create_app(services: Services | None = None) -> FastAPI`. The lifespan builds the services when none are passed. CORS allows `http://localhost:3000`. `app = create_app()` at module level, with lazy service construction in the lifespan, so importing does not connect.
  - Routes (spec section 6.5):
    - `POST /api/contracts`: multipart field `file`. `PdfRejected` maps to its status code and `{"detail": ...}`.
    - `GET /api/contracts/{id}/pdf`: `FileResponse` with `application/pdf`, or 404.
    - `POST /api/contracts/{id}/analyze`: 404 for an unknown contract. Otherwise it creates the run, adds `execute_run` as a `BackgroundTasks` task, and returns 202 `{run_id}`.
    - `GET /api/runs/{run_id}`: `RunView`, or 404.
    - `PUT /api/findings/{id}/decision`: 404 unknown, 422 if the finding has no suggestion (Q5), 422 if the body is invalid. Otherwise 200 with `DecisionView`.

- [ ] **Step 1: Write failing tests**

  `api/conftest.py` builds `Services` with a SQLite engine, `InMemorySaver`, a `FakeRetriever` that also accepts `add_contract`, a `ScriptedChatModel` that answers every clause, the real playbook, and `data_dir=tmp_path`. The client is `TestClient(create_app(services))`. FastAPI's `TestClient` runs background tasks before it returns the response, so runs finish synchronously in tests.
  - `test_upload_valid_pdf_returns_id_and_page_count` (AC-1): 200, `page_count == 3`, and `pages.json` exists on disk.
  - `test_upload_rejections` (AC-1), parametrized over non-PDF (415), oversized (413), 101 pages (422), and scanned (422). Each gives a non-empty `detail`, and no `Contract` row is written.
  - `test_get_pdf_serves_original`: same bytes, `content-type: application/pdf`. An unknown id gives 404.
  - `test_analyze_unknown_contract_404`
  - `test_analyze_then_run_completed_with_five_findings` (AC-2): 202, then `GET /api/runs/{id}` gives `status == "completed"`, 5 findings, and `progress` has 5 keys, each `"done"`.
  - `test_run_with_llm_error_is_completed_with_errors` (AC-12)
  - `test_unknown_run_404`
  - `test_decision_persists_across_requests` (AC-7): PUT `edited` with text, then a fresh `GET` of the run shows `decision.state == "edited"` and the text. Then PUT `rejected` gives `edited_text is None`.
  - `test_decision_edited_requires_text`: 422.
  - `test_decision_on_finding_without_suggestion_422`: on an `ok` finding.
  - `test_stale_runs_failed_on_startup`: a `running` row inserted before `create_app` and lifespan startup is `failed` afterwards.

  Remove the `xfail` marker from `test_importing_app_does_not_load_evals` (Task 10).

- [ ] **Step 2:** Run `uv run pytest tests/api -v`. Expected: FAIL. Implement. Rerun. Expected: 14 passed (the 4 upload rejection cases count separately). Then run `uv run pytest -q && uv run ruff check .`.

### Task 12: Real-stack check (integration, plus one manual LLM run)

**Files:**
- Create: `backend/tests/integration/test_pipeline.py`

- [ ] **Step 1: Integration test with real Postgres, Qdrant, and embeddings, and a fake model**

  `test_full_run_on_real_infra` (`@pytest.mark.integration`) uses `build_services(get_settings())` with `model` replaced by `ScriptedChatModel`. It uploads a generated 4-page PDF through `TestClient`, runs analyze, and expects 5 findings. It then checks that `PostgresSaver.get_tuple(run_config(run_id, 2))` is not `None`, which shows the checkpoint is in Postgres (AC-8).
  Run: `uv run pytest -m integration -v`. Expected: all integration tests pass.

- [ ] **Step 2: Manual run with the real model on one CUAD contract**

  Run these commands in this order:
  1. Start the API: `cd backend && uv run uvicorn app.main:app --port 8000`.
  2. Upload a contract and keep the returned `contract_id`:
     ```bash
     curl -s -F "file=@<the Rand Worldwide \"pdf\" path from data/spikes/s3.json>" localhost:8000/api/contracts
     ```
  3. Start a run, using the `contract_id` from step 2:
     ```bash
     curl -s -X POST localhost:8000/api/contracts/<id>/analyze
     ```
  4. Poll `curl -s localhost:8000/api/runs/<run_id>` until the status is not `running`.

  Expected: `completed` or `completed_with_errors`, and 5 findings. `governing_law` is `ok` or `risky`, with page 9 or 10 (S3 gold page). Record the status per clause, the number of LLM calls, and the wall-clock time in the task report. Run the same command again. Expected: much faster, because of cache hits.

---

## Milestone M4: Eval

### Task 13: Eval building blocks (`evals/sample.py`, `evals/metrics.py`, `evals/report.py`)

**Files:**
- Create: `backend/evals/sample.py`, `backend/evals/metrics.py`, `backend/evals/report.py`
- Test: `backend/tests/evals/test_sample.py`, `backend/tests/evals/test_metrics.py`, `backend/tests/evals/test_report.py`

**Interfaces:**
- Consumes: `load_gold`, `index_pdfs`, `match_pdfs`, `TARGET_LABELS` (Phase 0), and `token_f1` and `normalize` (Task 3).
- Produces:
  - `@dataclass(frozen=True) class EvalContract: title: str; pdf: Path; page_count: int`
  - `eligible_contracts(gold, matched: Mapping[str, Path]) -> tuple[list[EvalContract], list[tuple[str, str]]]` returns the eligible contracts and the excluded ones as `(title, reason)`. The reasons are `too many pages`, `too large`, `no text layer`, and `unreadable`, reusing the `parse_pdf` limits and constants.
  - `sample_contracts(eligible, gold, labels, n: int, seed: int) -> tuple[list[EvalContract], list[str]]` returns the sample and the coverage gaps. The algorithm, which must be deterministic:
    1. Sort by title, then shuffle with `random.Random(seed)`.
    2. For each `(label, present)`, then each `(label, absent)`, in `labels` order: if no picked contract covers it, pick the first shuffled contract that does.
    3. Fill up to `n` in shuffled order.
    4. If step 2 needs more than `n` contracts, keep the first `n` and list the uncovered needs as gaps.
  - `@dataclass class ClauseOutcome: title, label, gold_present: bool, found: bool, status: str, quote: str | None, gold_spans: tuple[str, ...], verify_failures: int, error: str | None, candidate_pages: list[int], gold_pages: list[int]`
  - `presence_prf(outcomes, label) -> tuple[float, float, float, int, int, int]` returns P, R, F1, TP, FP, FN. Found means `quote is not None and status in {"ok", "risky"}`. With no positives, a value is reported as `n/a`, not 0.
  - `span_match_rate(outcomes, label) -> float | None`: over TPs, the share where `max(token_f1(quote, s) for s in gold_spans) >= SPAN_MATCH_F1`.
  - `verification_rejection_rate(outcomes) -> float`: the share of outcomes with an extraction quote where `verify_failures >= 1`.
  - `uncertain_rate(outcomes) -> float`, `error_rate(outcomes) -> float`.
  - `retrieval_hit_rate(outcomes, label) -> float | None` (Q4): over gold-present outcomes, the share where `set(candidate_pages) & set(gold_pages)` is non-empty.
  - `gold_pages(pages: list[str], spans) -> list[int]`: the pages where any normalized span occurs (eval side only).
  - `render_report(config: dict, sample: list[str], excluded: list, gaps: list[str], outcomes, cost: dict) -> str` builds markdown with these sections:
    - `## Config`: model, seed, n, playbook hash, git commit, date.
    - `## Sample`: the titles.
    - `## Presence`: a table per clause with P, R, F1, TP, FP, FN.
    - `## Span match`
    - `## Verification rejection`
    - `## Uncertain and errors`
    - `## Retrieval hit rate`
    - `## Cost`: LLM calls per contract (cache hits included, stated), and wall-clock seconds per contract.
    - `## Excluded and gaps`.

- [ ] **Step 1: Write failing tests** (with synthetic gold from `tests/fixtures/cuad_mini.json` plus in-memory objects, and generated PDFs for `eligible_contracts`)
  - `test_sample_is_deterministic` (AC-9): the same seed gives the same title list twice, and a different seed gives a different order.
  - `test_sample_covers_present_and_absent_when_possible`: with 12 synthetic contracts and n = 4, every label has at least one present and one absent case.
  - `test_sample_reports_gaps_when_impossible`: a label with no absent case gives a gap string naming the label.
  - `test_sampler_excludes_oversized_contracts`: a 101-page generated PDF is in `excluded` with `too many pages`, and never in the sample.
  - `test_presence_prf_counts`: hand-built outcomes give the exact P, R, F1 values.
  - `test_ok_without_quote_counts_as_not_found`: `status="ok"`, `quote=None`, `gold_present=True` gives an FN.
  - `test_span_match_threshold`: a token F1 of exactly 0.5 counts, 0.49 does not.
  - `test_retrieval_hit_rate`
  - `test_report_has_all_sections`: every heading listed above appears in `render_report(...)`, and so does the model name.

- [ ] **Step 2:** Run `uv run pytest tests/evals -v`. Expected: the new tests FAIL. Implement. Rerun. Expected: all pass.

### Task 14: Eval CLI (`evals/run.py`) and the baseline

**Files:**
- Create: `backend/evals/run.py`, `backend/evals/results/.gitkeep`
- Test: `backend/tests/evals/test_run_cli.py`

**Interfaces:**
- Consumes: Tasks 11 and 13.
- Produces: `main(argv: list[str] | None = None) -> int`, run as `python -m evals.run [--n 10] [--seed 42] [--cuad ../data/cuad] [--sample-only]`.
  - It builds the real services with `build_services(get_settings())`.
  - For each sampled contract: `ingest_contract`, `create_run`, then `execute_run` (the same path as the API). It then reads the findings and builds the `ClauseOutcome`s.
  - LLM calls are counted with a LangChain `BaseCallbackHandler` (`on_chat_model_start`), passed in the run config. Add an optional `callbacks` parameter to `execute_run` for this.
  - It writes `evals/results/YYYY-MM-DD-HHMM.md` and prints the path.
  - `--sample-only` prints the sample titles and exclusions and exits without ingesting or making LLM calls.
  - Git commit: `git rev-parse --short HEAD`, plus `-dirty` if `git status --porcelain` is not empty.

- [ ] **Step 1: Write a failing test**

  `test_sample_only_is_deterministic_and_offline`: runs `main(["--sample-only", "--n", "3", "--seed", "1", "--cuad", <tmp dir with mini JSON and generated PDFs>])` twice with `capsys`. Both outputs are equal, and they make no services call (`build_services` is patched to raise).
  Run: `uv run pytest tests/evals/test_run_cli.py -v`. Expected: FAIL. Implement. Rerun. Expected: pass.

- [ ] **Step 2: Sample check on real CUAD (no LLM calls)**

  Run: `cd backend && uv run python -m evals.run --sample-only --n 10 --seed 42` twice.
  Expected: the same 10 titles both times (AC-9), plus the excluded count and any gaps. Record both in the task report.

- [ ] **Step 3: Small smoke eval**

  Run: `uv run python -m evals.run --n 2 --seed 42`.
  Expected: a report file with every section filled in and no Python errors.

- [ ] **Step 4: Rerun smoke to prove caching**

  Run the same command again. Expected: the same metrics and much lower wall-clock time.

- [ ] **Step 5: Check the call budget against Q1**

  Estimate the baseline: about 2 to 3 calls per clause × 5 clauses × 10 contracts, so roughly 150 calls before cache hits. Compare this with the daily limit the owner found. If it does not fit, stop and ask: split the run across days (the cache keeps finished contracts free), use a smaller N, or add credits.

- [ ] **Step 6: Baseline**

  Run: `uv run python -m evals.run --n 10 --seed 42`.
  Expected: `evals/results/<timestamp>.md` with all metrics. Paste the Presence and Span tables into the task report. The owner decides when to commit it (spec Phase 1 exit: "first eval report committed").

---

## Milestone M5: Frontend

All frontend tasks first read the matching docs in `frontend/node_modules/next/dist/docs/` (App Router routing, client components, `next.config` options) and note the version-specific findings. Verification for each task is `pnpm lint && pnpm build`, plus the manual checks listed. The spec has no frontend test framework, and this plan does not add one.

### Task 15: API client, providers, and the upload view

**Files:**
- Create: `frontend/src/lib/api.ts`, `frontend/src/app/providers.tsx`, `frontend/src/components/upload-panel.tsx`, `frontend/src/components/footer.tsx`, `frontend/.env.local.example`
- Modify: `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`

**Interfaces:**
- Produces in `api.ts`:
  - `API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`
  - TypeScript types that mirror `api/schemas.py`: `UploadResponse`, `RunView`, `FindingView`, `DecisionView`, `FindingStatus`, `RunStatus`, `DecisionState`.
  - Functions: `uploadContract(file: File): Promise<UploadResponse>`, `analyze(contractId: string): Promise<{ run_id: string }>`, `getRun(runId: string): Promise<RunView>`, `putDecision(findingId: string, body: { state: DecisionState; edited_text?: string }): Promise<DecisionView>`, `pdfUrl(contractId: string): string`.
  - `class ApiError extends Error { status: number; detail: string }`, thrown for any non-2xx response with the FastAPI `detail`.
- `providers.tsx`: a client component holding the `QueryClientProvider`.
- `footer.tsx`: the exact text "AI-assisted review. Not legal advice."
- `page.tsx` (route `/`) has these screen states:
  - empty: a dropzone, plus a file input that accepts `application/pdf`
  - uploading
  - upload error: shows `ApiError.detail`
  - uploaded: file name, page count, and an "Analyze" button
  - analyze: calls the API, then `router.push("/runs/<run_id>")`

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `cd frontend && pnpm lint && pnpm build`. Expected: both exit 0.
- [ ] **Step 3: Manual check**, with the API running and `pnpm dev`:
  - Upload a CUAD PDF: the page count is shown.
  - Upload a `.txt` renamed to `.pdf`: the 415 detail is shown.
  - The footer is visible.

### Task 16: Run page with progress, PDF viewer, and highlights

**Files:**
- Create: `frontend/src/app/runs/[runId]/page.tsx`, `frontend/src/components/run-progress.tsx`, `frontend/src/components/pdf-viewer.tsx`, `frontend/src/components/highlight-layer.tsx`

**Interfaces:**
- The run page:
  - `useQuery(["run", runId], getRun, { refetchInterval: (q) => q.state.data && ["queued", "running"].includes(q.state.data.status) ? 1000 : false })`. This polls every second while running (spec section 5).
  - States: analyzing (a `RunProgress` row per clause showing the current step), failed (a message and a "back to upload" link), results (split view), and partial results (some cards `uncertain`; same layout).
- `PdfViewer({ url, page, bboxes })`:
  - `react-pdf` `Document` plus a single `Page`, loaded with `next/dynamic` and `ssr: false`.
  - Set the worker source as the `react-pdf` v11 README says.
  - Page navigation buttons.
  - When the `page` prop changes, it scrolls or jumps to that page.
- `HighlightLayer({ bboxes, scale })`: absolutely positioned boxes over the rendered page, with `scale = renderedWidth / page.originalWidth`. PyMuPDF rects are in points with origin top left, which matches the viewport. With no bboxes, it shows a page-level highlight: a border around the whole page.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `pnpm lint && pnpm build`. Expected: exit 0.
- [ ] **Step 3: Manual check**, with a real run from Task 12:
  - The progress steps change while the run is running.
  - The PDF renders.
  - Changing `page` jumps to it.
  - Boxes line up with the quote text on the governing law page (AC-4, first half).

### Task 17: Clause cards and decisions

**Files:**
- Create: `frontend/src/components/clause-card.tsx`, `frontend/src/components/decision-controls.tsx`
- Modify: `frontend/src/app/runs/[runId]/page.tsx`
- Add shadcn components as needed: `pnpm dlx shadcn@latest add card badge textarea`.

**Interfaces:**
- `ClauseCard({ finding, rule, onSelect })` shows:
  - a status badge: `OK`, `Risky`, `Missing`, or `Uncertain`
  - the clause title and the playbook requirement
  - the quote and "page N", only when `quote` is set
  - the issues and the rationale
  - the suggestion and its explanation, for `risky` and `missing`
  - "Sections examined" (the candidate pages and the first 120 characters of each) when the clause was not found: `missing`, or `ok` without a quote
  - for `uncertain`, the `error` reason or "quote could not be verified"

  Clicking the card calls `onSelect(page, bboxes)`.
- The playbook rule text comes from `finding.playbook_rule`, which is stored per finding, so the frontend never reads the YAML.
- `DecisionControls({ finding })` is rendered only when `suggestion_text` is set.
  - Buttons: Accept, Edit, and Reject. Edit opens a textarea prefilled with the suggestion, then Save.
  - Each action uses a TanStack `useMutation(putDecision)`, then `invalidateQueries(["run", runId])`.
  - The current decision state is shown, and the 422 detail is shown on error.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `pnpm lint && pnpm build`. Expected: exit 0.
- [ ] **Step 3: Manual check** on a real run:
  - Clicking a card scrolls the PDF to the quote's page and highlights the quote (AC-4).
  - Edit the text, Save, then reload the browser. The edited text and state are still there (AC-7).
  - Reject, then reload. The state is still Rejected.
  - Take screenshots of the empty, analyzing, results, and failed states for the demo (checklist 12.F). Use a nonexistent run id for failed, or stop Qdrant before analyzing.

---

## Milestone M6: Exit

### Task 18: Acceptance walk, demo, and backlog

**Files:**
- Modify: spec checklists 12.A, 12.C, 12.D, 12.E, and 12.F (ticks only). Also `AGENTS.md` "Current state" and `README.md` (the run instructions).
- Create: `docs/plans/phase-2-backlog.md`, `docs/demo/` (screenshots; the owner decides whether to commit them).

- [ ] **Step 1: Full checks**

  Run:
  ```bash
  cd backend && uv run pytest -v && uv run pytest -m integration -v && uv run ruff check .
  cd ../frontend && pnpm lint && pnpm build
  ```
  Expected: all pass. Report both pytest counts separately.

- [ ] **Step 2: AC walk.** Write a table in the completion report: AC-1 to AC-13, each with the test name or manual step that proves it, and its result.
  - AC-11 (fresh clone): run `git clone /Users/vladlleen/Code/clauselens /tmp/clauselens-fresh`, copy `.env.example` to `.env` there (the owner adds the key), then follow the README. Also check `git ls-files | grep -E '(^|/)\.env$'`, which must print nothing.

- [ ] **Step 3: Demo.** Run 2 contracts end to end in the UI and save the screenshots (checklist 12.F).

- [ ] **Step 4: Phase 2 backlog.** Write `docs/plans/phase-2-backlog.md` from what the baseline showed: per-clause weak spots, the retrieval hit rate, the verification rejection rate, and the uncertain causes. Map each item to the spec section 10 Phase 2 list.

- [ ] **Step 5: Update the docs**
  - AGENTS.md "Current state": Phase 1 complete, and the baseline report path.
  - README: the full local run steps.
  - Spec checklists: tick only the verified items.

---

---

## Milestone M7: Observability (added 2026-11-23, owner request)

### Task 19: LangSmith tracing (spec 6.7, AC-14)

**Files:**
- Create: `backend/app/tracing.py`, `backend/tests/test_tracing.py`, `backend/tests/api/test_tracing_export.py`
- Modify: `backend/app/config.py`, `backend/app/services.py`, `backend/evals/run.py`, `.env.example`, `backend/tests/test_config.py`, `backend/tests/api/test_runs.py`

- [x] `Settings`: `langsmith_tracing` (default false), `langsmith_api_key`, `langsmith_project` (default `clauselens`), `langsmith_endpoint`; empty values mean unset.
- [x] `configure_tracing(settings)` sets `LANGSMITH_*` in `os.environ`, needs flag and key, overrides shell variables. Called in `build_services`.
- [x] `execute_run` sets `run_name`, tags (`clauselens`, plus `tags`), and metadata (`run_id`, `contract_id`, `model`, `playbook_hash`). The eval passes the tag `eval`.
- [x] Local fake-endpoint test: traces with graph, node, and LLM spans reach the endpoint when on; nothing when off.
- [ ] Owner adds `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and optionally `LANGSMITH_PROJECT` to `.env`, runs one analysis, and looks at the trace in LangSmith.

## Open questions for the owner

Status on 2026-11-22: the owner accepted the recommended answer for Q2 to Q9. They are decisions now; execute them as written. Q1 is still open: the owner is checking the free-tier limit. Q1 blocks only Task 14 Step 6.

1. **Q1, free-tier daily limit. Blocks Task 14 Step 6.** S1 could not read the numbers. My understanding, which is not verified: `:free` models get a small daily request count unless the account has bought credits, and a larger one after a small credit purchase. The baseline needs about 150 calls before cache hits. Please check https://openrouter.ai/docs/api-reference/limits, or `GET https://openrouter.ai/api/v1/key` (field `free_model_daily_requests`), and tell me the per-day and per-minute numbers.
2. **Q2, LLM cache package.** The spec names LangChain `SQLiteCache`. It lives in `langchain-community`, which is a new dependency. **Recommended: add `langchain-community` only for `SQLiteCache`** (no other use in `app/`). The alternative is our own small `BaseCache` over `sqlite3` (about 40 lines).
3. **Q3, new `Finding.verify_failures` column.** Eval metric 3 ("first quote failed verification") needs it, and spec section 6.4 does not have it. **Recommended: add it** (Task 1 edits the spec).
4. **Q4, retrieval hit rate in the eval report.** S5 says recall must be checked on a larger sample, and spec section 8 has no such metric. **Recommended: add it as a diagnostic metric.** It needs no extra LLM calls.
5. **Q5, decisions only on findings with suggested wording.** Spec section 5 shows buttons "for each suggestion". **Recommended: the API returns 422 for findings without a suggestion, and the UI hides the buttons there.**
6. **Q6, test split.** **Recommended: the default `pytest` runs offline on SQLite, fakes, and generated PDFs. Postgres, Qdrant, and model tests are marked `integration` and run with `-m integration`.** The runtime stays on Postgres (C8). Both suites are reported.
7. **Q7, run progress storage.** **Recommended: keep the per-clause progress in memory (it is lost on restart), and on startup mark leftover `queued` or `running` runs as `failed`.** No new table.
8. **Q8, quote rules.** **Recommended: a quote must be at least 5 words and lie on a single page. A cross-page quote ends `uncertain` after the retry.** This keeps AC-3 strict. Phase 2 can relax it.
9. **Q9, text-layer rule.** **Recommended: reject when the mean non-whitespace text per page is under 100 characters.** Task 14 excludes any CUAD contract that fails this rule and reports it.
