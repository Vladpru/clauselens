# Contract Review Agent: MVP design (Spec-Driven Development)

Status: APPROVED by the owner on 2026-11-22. Phase 0 is complete (results in the appendix). Phase 1 is next.
Date: 2026-11-22 (revised the same day: Python 3.14 after S4, PostgreSQL, Qdrant). Revised 2026-11-23: LangSmith tracing moved from Phase 3 into Phase 1 (G8, section 6.7, AC-14).
Owner: Vlad

---

## 1. Intent and why

**What it is.** A web app where a lawyer uploads a commercial contract (PDF). The app finds a small set of key clauses, quotes the exact text with its page number, compares each clause to a company playbook (a short YAML file of rules), flags risky or missing clauses, and drafts safer wording. The lawyer accepts, edits, or rejects each suggestion.

**Why it exists.** This is a learning project. The owner wants hands-on, practical experience of the AI-engineering stack, not a product to sell. The learning targets, in priority order:

1. **RAG on long documents:** parsing, chunking, hybrid retrieval, page-accurate citations.
2. **Structured LLM extraction:** typed outputs, retries, verification of what the model claims.
3. **Agent orchestration with LangGraph:** state, nodes, conditional edges, fan-out (`Send`), subgraphs, checkpointing.
4. **Evals:** measuring the pipeline against lawyer-labelled ground truth (CUAD) instead of eyeballing it.
5. **Human-in-the-loop review UX.**

The app should be "simple but must work" in the MVP, and then be iterated in phases (section 10). The MVP must already produce a real eval number.

**Why this domain.** Public, lawyer-labelled ground truth exists (CUAD), so quality can be measured. The hard problems (long documents, exact quotes, proving a clause is missing, page citations) are exactly the ones that teach the most.

## 2. Goals, non-goals, anti-goals

### Goals (MVP)
- G1. Upload a text-based PDF contract and run an analysis for 5 clause types.
- G2. For each clause, return status (`ok`, `risky`, `missing`, `uncertain`), the verbatim quote, the page number, and (when possible) the highlight rectangles.
- G3. Compare each found clause with a playbook rule and explain why it passes or fails.
- G4. Suggest safer wording for risky and missing clauses.
- G5. The lawyer can accept, edit, or reject each suggestion, and the decision persists.
- G6. A CLI eval harness scores the pipeline against CUAD labels and writes a reproducible markdown report.
- G7. LangChain is the only way the code talks to the LLM, and the pipeline is a compiled LangGraph.
- G8. The owner can see in LangSmith which prompts, models, and graph steps ran for a run, with their inputs, outputs, tokens, latency, and errors. Tracing is opt-in (section 6.7).

### Non-goals (MVP)
- Deploy, hosting, CI/CD, containerizing the app itself (local only). Docker is used only to run PostgreSQL and Qdrant locally.
- Login, multi-user, permissions.
- OCR or scanned PDFs. DOCX or other formats.
- More than 5 clause types. All 41 CUAD categories.
- Redline/Word export. Diff view.
- Streaming tokens to the UI. SSE.
- Production-grade security and privacy review.
- EU/UK-specific legal content (the playbook is generic in the MVP).

### Anti-goals (would make it a failure even if it "works")
- A citation that is not verbatim text on the cited page. A made-up quote shown as evidence is the worst failure.
- Declaring a clause "missing" without recording what was searched.
- Gold labels leaking into the pipeline, which would make eval numbers meaningless.
- Calling the LLM without LangChain, or orchestrating with ad-hoc loops instead of LangGraph.
- Real or confidential contracts sent to a free model endpoint (see section 7).
- Contract text sent to a tracing service without the owner turning tracing on. Traces hold full prompts, so tracing is off by default (section 6.7).
- Presenting output as legal advice.

## 3. Hard constraints (decided by the owner)

| # | Constraint |
|---|---|
| C1 | LLM access only through **LangChain** chat model objects. No direct `openai`, `requests`, or `httpx` calls to the model API. |
| C2 | Pipeline orchestrated with **LangGraph** (a compiled `StateGraph`). |
| C3 | LLM provider is **OpenRouter**. Default model: `nvidia/nemotron-3-ultra-550b-a55b:free`. The model name comes from config, never hard-coded. |
| C4 | Data source is **CUAD** (public). No real client contracts. |
| C5 | Backend is Python. Frontend is TypeScript (Next.js). |
| C6 | MVP is local only. No deploy work. |
| C7 | **Python 3.14** (originally 3.15, the owner's choice; changed after spike S4: `onnxruntime`, which FastEmbed needs, has no `cp315` wheels, see the appendix). `requires-python` is `>=3.14,<3.15`. |
| C8 | App data and LangGraph checkpoints live in **PostgreSQL**. Chunk vectors live in **Qdrant**. Both run in Docker through `docker-compose.yml`. |

## 4. Data: sources and how they are used

**CUAD v1** (Contract Understanding Atticus Dataset): 510 real commercial contracts, 41 clause categories labelled by lawyers. Download from Zenodo record 4595826 (`CUAD_v1.zip`, about 106 MB). According to the dataset description, it contains the contracts as PDF and TXT, and a SQuAD-style JSON with, per contract and category, the labelled answer texts and character offsets. Some mirrors have 509 PDFs (one scanned file removed). **Phase 0 must confirm the exact folder names, JSON shape, and category label strings by opening the files.**

| Source | Used for | Shown to the LLM? |
|---|---|---|
| CUAD contract PDFs | Input documents for the app and for eval | Yes (as parsed text chunks) |
| CUAD labels JSON | Ground truth for eval only (present/absent and gold span text per clause) | **Never** |
| `playbook/playbook.yaml` | The company's rules per clause. Written by the owner (a draft will be provided to edit) | Yes |

How the labels are used: for each (contract, clause) pair, the clause is "present" in gold if CUAD has at least one non-empty answer for that category. The gold span text is compared to the pipeline's extracted quote using normalized text (the TXT and the PDF text extraction will differ in whitespace and quotes, so character offsets are NOT comparable across them; matching is by normalized token overlap).

### Data flow

```mermaid
flowchart LR
  subgraph DATA[Data]
    C[CUAD contract PDFs]
    L[CUAD labels JSON]
    P[playbook.yaml]
  end

  C --> ING[Ingest: parse pages, text, bboxes; embed chunks]
  ING --> Q[(Qdrant: chunk vectors)]

  subgraph GRAPH[LangGraph review run]
    direction LR
    ING --> FAN{Fan out per clause}
    FAN --> RET[Retrieve candidates]
    RET --> EXT[Extract quote - LLM via LangChain]
    EXT --> VER{Verify quote on page}
    VER -- fail, retry once --> EXT
    VER --> LOC[Locate page + bbox]
    LOC --> ASS[Assess vs playbook rule - LLM]
    ASS --> SUG[Suggest wording - LLM]
    SUG --> MERGE[Merge findings]
  end

  P --> ASS
  P --> SUG
  Q --> RET
  MERGE --> DB[(PostgreSQL)]
  DB --> UI[Review UI: accept / edit / reject]

  MERGE --> EV[Eval harness - CLI]
  L --> EV
  EV --> REP[Markdown report: F1 per clause]
```

## 5. MVP user experience

One page, local, no login.

1. **Upload:** drag or select a PDF. Errors for scanned PDFs, files over the limits, or non-PDFs are shown clearly.
2. **Analyze:** click "Analyze". A progress panel shows the current graph step per clause (polling the run status every second).
3. **Review screen**, split in two:
   - **Left:** PDF viewer (pdf.js via `react-pdf`).
   - **Right:** one card per clause (5 cards):
     - status badge: `OK`, `Risky`, `Missing`, `Uncertain`
     - clause name and the playbook rule it was checked against
     - the verbatim quote and page number (not shown when the clause was not found)
     - the issues found and a short rationale
     - for `risky` and `missing`: suggested wording
     - when the clause was not found (`missing`, or `ok` because the playbook says absence is acceptable): the list of sections that were examined
     - **Accept / Edit / Reject** buttons. Edit lets the lawyer change the suggested text before accepting.
   - Clicking a card scrolls the PDF to the quote's page and highlights it when a bounding box is available (page-only highlight otherwise).
4. Decisions persist (reload the page, state remains).
5. Eval is **not** in the UI. It is a CLI: `uv run python -m evals.run`.

Screen states to implement: empty, uploading, analyzing, results, run failed, partial results (some clauses `uncertain`).

## 6. Architecture

### 6.1 Repository layout

```
clauselens/
├── backend/
│   ├── pyproject.toml            # managed by uv
│   ├── app/
│   │   ├── main.py               # FastAPI app
│   │   ├── config.py             # pydantic-settings (env)
│   │   ├── db.py, models.py      # SQLModel tables
│   │   ├── api/                  # routers: contracts, runs, findings
│   │   ├── ingest/               # pdf parsing, normalization, chunking, index
│   │   ├── llm.py                # the ONLY place a chat model is constructed
│   │   ├── playbook.py           # load + validate playbook.yaml
│   │   └── graph/
│   │       ├── state.py          # TypedDict/Pydantic state + schemas
│   │       ├── clause_graph.py   # per-clause subgraph
│   │       ├── review_graph.py   # parent graph with Send fan-out
│   │       └── nodes/            # retrieve, extract, verify, locate, assess, suggest
│   ├── evals/                    # CLI harness; imports app, never the reverse
│   │   ├── cuad.py               # parse CUAD labels, build gold
│   │   ├── run.py                # python -m evals.run
│   │   └── results/              # markdown reports (committed)
│   └── tests/
├── frontend/                     # Next.js app
├── playbook/playbook.yaml
├── docker-compose.yml            # postgres + qdrant
├── data/                         # gitignored: CUAD download, uploaded PDFs, parsed page text, LLM cache
├── docs/specs/                   # this file
├── .env.example
└── .gitignore
```

Rule: `app/` must not import from `evals/` or read CUAD labels (enforced by a test, AC-10).

### 6.2 Stack

| Layer | Choice | Note |
|---|---|---|
| Python | 3.14, `uv` | 3.15 was the first choice and failed spike S4 (no `onnxruntime` `cp315` wheels). Revisit 3.15 when those wheels exist |
| API | FastAPI + Uvicorn | |
| LLM layer | `langchain` + `langchain-openrouter` (`ChatOpenRouter`) | Dedicated integration is what LangChain docs recommend for OpenRouter, over `ChatOpenAI` with a custom base URL |
| Orchestration | `langgraph` + `PostgresSaver` (`langgraph-checkpoint-postgres`, `psycopg[binary,pool]`) | Call `checkpointer.setup()` once on first use (per LangGraph docs) |
| PDF | PyMuPDF (`pymupdf`) | Page text and `search_for` rectangles |
| Retrieval | Hybrid: dense + sparse (BM25-style) search in Qdrant | Preferred: Qdrant native hybrid through `langchain-qdrant` (I have not verified the exact API, see spike S5). Fallback: `rank_bm25` in process + Qdrant dense, merged with a small own reciprocal-rank-fusion function |
| Embeddings | Local small model, e.g. `BAAI/bge-small-en-v1.5`, preferably through FastEmbed (ONNX) | Avoids spending free-tier LLM quota. ONNX avoids a heavy torch install, which also lowers wheel risk on new Python versions |
| Vector store | Qdrant (Docker), one collection `contract_chunks`, payload filter by `contract_id` | Owner's choice |
| App DB | PostgreSQL 16 (Docker) via SQLModel + `psycopg`. `create_all` in the MVP, Alembic in Phase 2 | Owner's choice. Two databases on one server: `contract_review` (app data) and `contract_review_checkpoints` (LangGraph) |
| Observability | LangSmith, through LangChain's built-in tracing (`LANGSMITH_*` environment variables) | Opt-in and off by default. No tracing code in the nodes. See section 6.7 |
| Tests | pytest, LangChain fake chat models for graph tests | |
| Frontend | Next.js (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query, `react-pdf` | Matches owner's stack |
| API types | OpenAPI from FastAPI, optionally `openapi-typescript` | Optional |

### 6.3 LangGraph design

**Parent graph (`review_graph`)**, state:

```python
class ReviewState(TypedDict):
    contract_id: str
    clause_ids: list[str]                      # from playbook
    findings: Annotated[list[Finding], operator.add]   # reducer merges parallel results
```

Nodes and edges:
1. `ingest`: load the already-parsed contract (pages, text, index). Fails the run early if the contract is unreadable.
2. `dispatch`: conditional edge returning one `Send("review_clause", {...})` per clause (parallel fan-out).
3. `review_clause`: the per-clause subgraph (below), returning one `Finding`.
4. `finalize`: persist findings, set run status.

Run with `max_concurrency` of 2 (configurable) to stay inside free-tier rate limits. Compile with the `PostgresSaver` checkpointer and use the run id as `thread_id`. With Postgres there is no single-writer limit, so parallel clause branches and the app can write at the same time.

**Per-clause subgraph (`clause_graph`)**:

| Node | Type | What it does |
|---|---|---|
| `retrieve` | code | Hybrid search over the contract's chunks using the clause's query terms from the playbook. Returns top-k (default 8) candidates with page numbers. Records which candidates were examined. |
| `extract` | LLM | Given candidates, returns `ClauseExtraction{found: bool, quote: str \| null, reasoning: str}` via `with_structured_output(..., method="function_calling")`. Prompt requires a verbatim quote. |
| `verify` | code | Normalizes whitespace/quotes/dashes/case and checks the quote is a substring of the cited page text. |
| conditional edge | code | If verify fails and retries < 1, go back to `extract` with feedback "quote not found verbatim". If it still fails, status = `uncertain` and no quote is shown. |
| `locate` | code | Finds the page and highlight rectangles (`page.search_for`, with word-level fallback). Page is mandatory. Rectangles are best-effort. |
| `assess` | LLM | Given the quote and the playbook rule, returns `{compliant: bool, issues: [str], rationale: str}`. |
| `suggest` | LLM | Only for `risky` and `missing`. Returns `{text, explanation}` based on the playbook's preferred wording. |

Status rules:
- found, verified, compliant -> `ok`
- found, verified, not compliant -> `risky`
- not found by the extractor, playbook `absence_is: missing` -> `missing`, with severity from the playbook and the examined candidates recorded
- not found by the extractor, playbook `absence_is: ok` -> `ok` (absence is acceptable under our stance), with the examined candidates recorded and no suggestion
- extractor claims found but quote fails verification twice -> `uncertain`
- LLM error after retries (429, timeout, parse failure) -> `uncertain` with `error` reason. The run continues and ends `completed_with_errors`. It must not crash.

MVP "missing" proof is deliberately weak: one retrieval pass, top-k candidates recorded. Phase 2 adds an exhaustive second pass.

### 6.4 Data model (PostgreSQL)

- `Contract(id, filename, path, page_count, uploaded_at)`
- `Run(id, contract_id, status[queued|running|completed|completed_with_errors|failed], started_at, finished_at, model, playbook_hash)`
- `Finding(id, run_id, clause_id, status, severity, quote, page, bboxes_json, candidates_json, playbook_rule, issues_json, rationale, suggestion_text, suggestion_explanation, error, verify_failures)` (`verify_failures` is an int from 0 to 2: how many times the extracted quote failed verification. Eval metric 3 reads it.)
- `Decision(finding_id PK, state[pending|accepted|edited|rejected], edited_text, decided_at)`

Parsed page text lives under `data/contracts/{id}/pages.json` (the `verify` node reads it). Chunk vectors and sparse vectors live in the Qdrant collection `contract_chunks`, each point carrying `contract_id`, `page`, and `chunk_id` in its payload. With `langchain-qdrant` these sit under the `metadata` payload key (`metadata.contract_id`, confirmed in S5), so filters use that key.

### 6.5 API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/contracts` | Multipart PDF upload. Parses and indexes. Returns `{contract_id, page_count}` |
| GET | `/api/contracts/{id}/pdf` | Serves the original PDF |
| POST | `/api/contracts/{id}/analyze` | Starts a run (background task). Returns `{run_id}` |
| GET | `/api/runs/{run_id}` | Run status, per-clause step progress, findings when done |
| PUT | `/api/findings/{id}/decision` | Body `{state, edited_text?}`. Returns 422 for a finding without suggested wording |

Limits: PDF only, at most 20 MB and 100 pages, must contain a text layer.

### 6.6 Playbook schema (`playbook/playbook.yaml`)

```yaml
version: 1
stance: "We are a commercial party reviewing a third-party agreement."   # owner confirms
clauses:
  - id: governing_law
    cuad_label: "Governing Law"          # exact string confirmed in Phase 0
    title: "Governing law"
    query_terms: ["governing law", "governed by", "laws of", "jurisdiction"]
    requirement: "Governing law must be England and Wales, or an EU member state."
    acceptable: ["England and Wales", "Scotland", "any EU member state"]
    red_flags: ["law of a jurisdiction outside UK/EU without our approval"]
    preferred_wording: "This Agreement is governed by the laws of England and Wales."
    severity_if_missing: medium          # low | medium | high
    absence_is: missing                  # ok | missing: what a not-found clause means under our stance
```

MVP clauses (5), my pick, owner can swap: Governing Law, Termination For Convenience, Cap On Liability, Non-Compete, Anti-Assignment. The exact CUAD label strings are confirmed in Phase 0.

### 6.7 Observability (LangSmith)

LangChain and LangGraph send traces to LangSmith when tracing is on, so the nodes need no tracing code. `app/tracing.py` reads the settings and sets the `LANGSMITH_*` process environment, because the SDK reads the environment and not `.env`.

| Setting | Meaning |
|---|---|
| `LANGSMITH_TRACING` | `true` turns tracing on. Default `false` |
| `LANGSMITH_API_KEY` | Required for tracing. With the flag on and no key, tracing stays off |
| `LANGSMITH_PROJECT` | Project name. Default `clauselens` |
| `LANGSMITH_ENDPOINT` | Optional, for a regional or self-hosted endpoint |

- `app.tracing.configure_tracing(settings)` runs in `build_services`, so the API and the eval CLI behave the same. The settings override any `LANGSMITH_*` or `LANGCHAIN_*` variable set in the shell.
- One trace per run. It shows the parent graph, one child per clause subgraph, one span per node, and each LLM call with its prompt, tool call, tokens, latency, and error.
- Each trace is named `review <first 8 characters of the run id>` and tagged `clauselens`. Eval runs add the tag `eval`. Metadata: `run_id`, `contract_id`, `model` (the configured primary), `playbook_hash`. Metadata and tags are not part of any prompt, so the LLM cache is unaffected.
- Privacy: a trace holds the full prompts, so contract text goes to LangSmith. Use tracing only with public CUAD contracts (C4), and the README says so. Tracing off sends nothing, and the app works without a LangSmith account.
- Not traced: PDF parsing, chunking, embeddings, retrieval, and verification run as plain code. Their results show up as inputs and outputs of the nodes that call them.

## 7. Model facts, risks, mitigations

Facts checked on 2026-11-22 (OpenRouter listing pages):
- `nvidia/nemotron-3-ultra-550b-a55b:free` exists on OpenRouter.
- It **supports tool calling** but the listing indicates it does **not** support `response_format` (enforced JSON schema). Therefore structured output must use LangChain's `method="function_calling"` (forced tool call), not `json_schema`. **Unverified: whether `ChatOpenRouter.with_structured_output(method="function_calling")` works end to end with this model. This is Phase 0 spike S1.**
- The model has a very large context window (listed as about 1M tokens) and supports reasoning.
- Free endpoints are rate limited and the prompts/outputs on the free endpoint may be logged by the provider. Check the current daily and per-minute limits on OpenRouter before planning eval volume.

| Risk | Mitigation |
|---|---|
| Free-tier rate limits or daily cap break eval runs | `max_concurrency=2`, exponential backoff, LangChain `SQLiteCache` from `langchain-community` (a local cache file, separate from the app database) for dev and eval so repeated runs are free, small default eval size (10 contracts), full run (20) only occasionally |
| Function-calling output unreliable | Pydantic validation plus one retry with the validation error fed back. Fallback: JSON-in-prompt plus `PydanticOutputParser`. Decision point in Phase 0 |
| Reasoning text pollutes the answer | Parse only the structured tool call, ignore reasoning fields. Confirm in S1 |
| Quote hallucination | `verify` node (anti-goal enforced in code and tested) |
| Prompts logged by provider | Only public CUAD contracts. A README warning: never upload real contracts to this setup |
| Traces hold full contract text and prompts and go to LangSmith cloud | Tracing is off by default and needs a key. Only public CUAD contracts (C4). README warning. The owner can use a self-hosted or regional `LANGSMITH_ENDPOINT` |
| PDF bbox search fails on multi-line or hyphenated text | Page number is mandatory, bbox best-effort with word-level fallback, page-level highlight otherwise |
| CUAD txt vs PDF text mismatch breaks gold matching | Match by normalized token overlap, never by offsets |
| The model may be renamed or removed from the free tier | Model id is config. Swapping to another OpenRouter model is a one-line change |
| Legal liability | UI footer: "AI-assisted review. Not legal advice." |
| Python 3.15 was the first choice, but compiled dependencies may lack 3.15 wheels. Spike S4 confirmed it: `onnxruntime` (needed by FastEmbed) has no `cp315` wheels | Phase 0 fell back to Python 3.14 (see C7 and the appendix). Keep `requires-python` explicit in `pyproject.toml`. Revisit 3.15 when `onnxruntime` ships `cp315` wheels |
| `qdrant/qdrant` is not among the local Docker images (only Postgres images are) | `docker pull qdrant/qdrant` once, then pin the tag in `docker-compose.yml` |
| Connection string forms differ between `PostgresSaver` (plain `postgresql://`) and SQLModel/SQLAlchemy (`postgresql+psycopg://`) | Two env vars (`DATABASE_URL`, `CHECKPOINT_DB_URL`). Covered by the Phase 0 smoke test (S4) |

## 8. Evaluation design (MVP)

CLI: `uv run python -m evals.run --n 10 --seed 42` (default 10, full run 20).

**Sample:** deterministic sample of N CUAD contracts by seed, with the requirement that for each of the 5 clauses the sample has at least one present and one absent case when the data allows it (report if it does not).

**Metrics:**
1. **Presence P/R/F1 per clause:** gold present vs pipeline found. Found means the finding carries a verified quote (`ok` or `risky` with a quote). An `ok` finding without a quote (absence accepted by the playbook) counts as not found.
2. **Span match rate:** among true-positives, share where the extracted quote overlaps the gold span (normalized token F1 of at least 0.5, threshold is a documented constant).
3. **Verification rejection rate:** how often the LLM's first quote failed verification (a hallucination proxy).
4. **Uncertain/error rate.**
5. **Cost proxies:** LLM calls and wall-clock per contract.

Diagnostic metric (no LLM calls): **Retrieval hit rate.** Among gold-present clauses, the share where any candidate page contains a gold span. It separates retrieval misses from extraction misses.

**Output:** `backend/evals/results/YYYY-MM-DD-HHMM.md` containing the config (model, seed, n, playbook hash, git commit) and the tables. No pass/fail threshold in the MVP. The first run is the baseline to beat in Phase 2.

Not evaluated in the MVP (no ground truth exists): risk assessment and redline quality. Phase 2 adds a hand-labelled set (about 30 cases) and an LLM-judge.

## 9. Acceptance criteria (MVP)

Each is observable and has a verification step.

| ID | Criterion | Verified by |
|---|---|---|
| AC-1 | Uploading a text-based PDF within limits returns a contract id and page count. A scanned, oversized, or non-PDF file returns a clear 4xx error and the UI shows it | API tests + manual |
| AC-2 | Analyze returns exactly 5 findings, one per playbook clause, each with a status in `ok/risky/missing/uncertain` | Graph integration test with fake LLM |
| AC-3 | Every displayed quote is a normalized substring of the cited page's text. No unverified quote is ever returned as a citation | Unit tests for `verify` + property check in the integration test |
| AC-4 | Clicking a card scrolls the PDF to the cited page. When bboxes exist, the quote is highlighted | Manual check |
| AC-5 | A finding for a clause that was not found (`missing`, or `ok` with `absence_is: ok`) includes the list of examined candidates (pages/snippets) | Integration test |
| AC-6 | `risky` and `missing` findings carry suggested wording. `ok` findings do not, including `ok` findings for a clause that is absent with `absence_is: ok` | Integration test |
| AC-7 | Accept/Edit/Reject persists across a page reload | API test + manual |
| AC-8 | All model calls go through a LangChain chat model built in `app/llm.py`. The pipeline is a compiled LangGraph with a Postgres checkpointer | Grep gate in a test (no direct HTTP client to openrouter, no `openai` import) + code review |
| AC-9 | `python -m evals.run --n 10 --seed 42` produces the markdown report with all metrics in section 8, and the same seed selects the same contracts | Run twice, compare sample list |
| AC-10 | `app/` does not import `evals/` or read CUAD labels | Import-graph test |
| AC-11 | Runs locally from a fresh clone with `.env` from `.env.example` and `docker compose up -d` (Postgres + Qdrant). No secret is committed | Manual + `git ls-files` check |
| AC-12 | A 429/timeout/parse error on one clause yields `uncertain` with an error reason for that clause. The run still finishes | Integration test with a failing fake model |
| AC-13 | Unit tests cover normalization, verify, playbook validation, gold parsing. The graph is tested with a fake chat model (no network) | `uv run pytest` green |
| AC-14 | With `LANGSMITH_TRACING=true` and a key, a run produces one LangSmith trace with a child span per graph node and per LLM call, tagged and annotated as in section 6.7. With tracing off, or on without a key, nothing is sent and every other AC still holds | Unit tests for `configure_tracing` and run metadata, a local fake-endpoint check, and a manual look at the trace in LangSmith |

Negative requirements: no auth, no deploy files, no OCR, no export, no more than 5 clauses in the MVP, the UI never shows CUAD gold labels, tracing is never on unless the owner sets the flag and a key.

## 10. Phases

Each phase ends with a demo and an eval report. Do not start a phase before the previous exit criteria are met.

### Phase 0: Foundations and spikes (about 1 to 2 days)
Init repo, env, deps, CUAD download, and the risky unknowns:
- **S1:** `ChatOpenRouter` + Nemotron free + `with_structured_output(method="function_calling")` returns valid Pydantic objects on a sample extraction prompt in at least 9 of 10 tries.
- **S2:** Inspect CUAD files, confirm label strings and gold format, write the gold parser.
- **S3:** PyMuPDF on 3 CUAD PDFs: page text extraction and `search_for` on a known quote.
- **S4:** On Python 3.15 (fell back to 3.14, see the appendix): `uv sync` installs the full dependency set, `docker compose up -d` brings up Postgres and Qdrant, `PostgresSaver.setup()` runs, and a SQLModel `create_all` succeeds.
- **S5:** Qdrant hybrid retrieval (dense + sparse) works through `langchain-qdrant` on 3 contracts and returns the page-tagged chunk for a known clause. If not, use the fallback (in-process BM25 + Qdrant dense + RRF).
- Draft the playbook for 5 clauses (owner reviews).

Exit: S1 to S5 results recorded in the spec appendix. If S1 fails, decide the fallback (JSON-in-prompt parser or another OpenRouter model) before Phase 1. If S4 fails on 3.15, drop to 3.14 before Phase 1 (done).

### Phase 1: MVP (this spec)
Backend ingest, graph, API, tests. Frontend review screen. Eval CLI baseline. LangSmith tracing (opt-in, section 6.7).
Exit: all AC-1 to AC-14 pass, first eval report committed.

### Phase 2: Quality and evals
- Exhaustive "missing" proof (second retrieval pass and a full-document scan fallback).
- Grow to 10 clauses.
- Reranker experiment, chunking experiments, each compared by eval.
- Baseline vs pipeline comparison (single long-context call over the whole contract vs the graph).
- Hand-labelled set for risk and redline quality plus an LLM-judge.
- Alembic migrations for Postgres (the MVP uses `create_all`).
- LangGraph human-in-the-loop `interrupt`: the lawyer's edit feedback triggers a redraft node.

### Phase 3: Robustness
- Prompt versioning, regression evals runnable in CI, model comparison through OpenRouter (free vs cheap paid), SSE streaming of progress.

### Phase 4: Product polish (optional, later)
- EU/UK playbook content, additional file formats, auth, deploy.

## 11. Project init (how to start Phase 0)

These commands are instructions for later. Nothing has been run. Verify tool versions and flags at execution time.

```bash
# 1. Repo
cd ~/Code/clauselens
git init

# 2. Backend
mkdir -p backend && cd backend
uv init --app --name contract-review-backend --python 3.14
# uv 0.13 generates src/, [build-system] and a README stub. Remove them: the layout is flat backend/app (section 6.1).
uv add fastapi "uvicorn[standard]" python-multipart sqlmodel pydantic-settings pyyaml \
  "psycopg[binary,pool]" pymupdf langchain langchain-openrouter langgraph \
  langgraph-checkpoint-postgres langchain-qdrant qdrant-client fastembed
uv add --dev pytest pytest-asyncio httpx ruff
cd ..

# 3. Frontend
pnpm dlx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm --yes
cd frontend
pnpm dlx shadcn@latest init -d
pnpm add @tanstack/react-query react-pdf
cd ..

# 4. Infra (Postgres + Qdrant)
docker pull qdrant/qdrant            # pinned to v1.20.2 in docker-compose.yml
docker compose up -d
docker compose exec postgres createdb -U postgres contract_review
docker compose exec postgres createdb -U postgres contract_review_checkpoints

# 5. Env
cp .env.example .env     # then put your OpenRouter key in .env
```

`.env.example`:
```
OPENROUTER_API_KEY=
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
LLM_MAX_CONCURRENCY=2
DATA_DIR=./data
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5434/contract_review
CHECKPOINT_DB_URL=postgresql://postgres:postgres@localhost:5434/contract_review_checkpoints?sslmode=disable
QDRANT_URL=http://localhost:6333
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=clauselens
```

`docker-compose.yml` (local dev only, throwaway credentials):
```yaml
services:
  postgres:
    image: postgres:16            # already in local Docker images
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports: ["5434:5432"]   # host 5434: 5432 is often taken by another local Postgres
    volumes: [pgdata:/var/lib/postgresql/data]
  qdrant:
    image: qdrant/qdrant:v1.20.2
    ports: ["6333:6333", "6334:6334"]
    volumes: [qdrantdata:/qdrant/storage]
volumes:
  pgdata:
  qdrantdata:
```

`.gitignore` must include: `.env`, `data/`, `*.db`, `.venv/`, `node_modules/`, `.next/`, `__pycache__/`.

CUAD: download `CUAD_v1.zip` from https://zenodo.org/records/4595826 and unzip into `data/cuad/` (about 106 MB, owner does this step manually).

Dev commands (once code exists): `docker compose up -d`, `uv run uvicorn app.main:app --reload` (port 8000), `pnpm dev` (port 3000), `uv run pytest`, `uv run python -m evals.run --n 10 --seed 42`.

## 12. MVP checklist

### A. Model and provider readiness (OpenRouter + Nemotron)
- [x] OpenRouter account and API key created, stored only in `.env`
- [ ] Current free-tier limits (requests per minute, per day) read and noted here
- [x] Model id `nvidia/nemotron-3-ultra-550b-a55b:free` reachable from `ChatOpenRouter`
- [x] Plain chat call works
- [x] Forced tool call (function calling) returns a valid Pydantic object (S1, at least 9/10)
- [x] Reasoning output does not leak into parsed results
- [x] Temperature 0, max tokens, and request timeout set
- [ ] Retry with backoff on 429 and 5xx
- [ ] `SQLiteCache` enabled for dev and eval
- [ ] Fallback decided if S1 fails
- [x] README note: only public CUAD contracts, never real ones

### B. Phase 0
- [x] Repo, git, `.gitignore`, `.env.example`
- [x] `uv` updated and Python 3.15 available (`uv python list`)
- [x] Backend uv project on Python 3.15 with deps installed (S4), or fallback to 3.14 recorded
- [x] `qdrant/qdrant` pulled and tag pinned; `docker compose up -d` healthy
- [x] Databases `contract_review` and `contract_review_checkpoints` created; `PostgresSaver.setup()` run
- [x] Qdrant hybrid retrieval spike (S5)
- [x] Frontend scaffolded
- [x] CUAD downloaded, folder layout and label strings recorded
- [x] Gold parser prototype (S2)
- [x] PDF text and `search_for` spike (S3)
- [x] Playbook draft for 5 clauses reviewed by owner

### C. Phase 1 backend
- [ ] Config, SQLModel tables on Postgres, FastAPI skeleton
- [ ] Upload endpoint with validation and parsing
- [ ] Chunking with page metadata, Qdrant collection `contract_chunks`, hybrid retrieval
- [ ] `llm.py` single model factory
- [ ] Pydantic schemas: extraction, assessment, suggestion, finding
- [ ] Nodes: retrieve, extract, verify, locate, assess, suggest
- [ ] Per-clause subgraph with the verify retry edge
- [ ] Parent graph with `Send` fan-out, reducer, Postgres checkpointer
- [ ] Analyze endpoint (background run) and run status endpoint
- [ ] Decision endpoint
- [ ] Error handling to `uncertain` (AC-12)
- [ ] Tests for AC-2, 3, 5, 6, 8, 10, 12, 13

### D. Phase 1 frontend
- [ ] Upload view with error states
- [ ] Run progress polling view
- [ ] PDF viewer with jump-to-page
- [ ] Highlight overlay from bboxes (page-only fallback)
- [ ] Clause cards with status, quote, rule, issues, suggestion, examined sections
- [ ] Accept / Edit / Reject with persistence
- [ ] Footer disclaimer

### E. Phase 1 eval
- [ ] Gold builder from CUAD JSON
- [ ] Seeded stratified sampler
- [ ] Metrics 1 to 5 implemented
- [ ] Markdown report writer with config header
- [ ] First baseline report committed

### E2. Phase 1 observability (LangSmith)
- [ ] `app/tracing.py` sets `LANGSMITH_*` from settings; off by default; flag without key stays off
- [ ] Run metadata and tags (`run_id`, `contract_id`, `model`, `playbook_hash`, `clauselens`, `eval`) set in `execute_run`
- [ ] Local fake-endpoint check shows a trace tree is sent when tracing is on, and nothing when off
- [ ] Owner adds a LangSmith key and looks at one real trace (graph, nodes, LLM calls)
- [ ] README warning: tracing sends contract text to LangSmith, public CUAD contracts only

### F. Exit
- [ ] AC-1 to AC-14 checked one by one
- [ ] Demo run on 2 contracts recorded (screenshots)
- [ ] Phase 2 backlog written from what the baseline showed

## 13. Decisions I made (owner can override)

1. 5th clause is Anti-Assignment (owner named four).
2. MVP playbook stance is "a commercial party reviewing a third-party agreement". Owner confirms or changes this when reviewing the playbook, because it flips which direction is "risky" for several clauses.
3. Python 3.14 (3.15 was the owner's first choice and failed S4), `uv`, `pnpm`.
4. Local embeddings instead of an LLM-provider embeddings endpoint, to save free-tier quota. FastEmbed (ONNX) to avoid torch.
5. Qdrant for vectors and PostgreSQL 16 for everything else (owner's choice). The image is pinned to `postgres:16` because it is already local. The pgvector images are not needed since Qdrant holds the vectors.
6. Polling instead of SSE for progress in the MVP.
7. Parallel per-clause fan-out with `Send` (LangGraph learning goal), concurrency capped at 2.
8. `uncertain` as a fourth status, so the app never fakes a citation or a "missing" verdict.
9. Upload limits: 20 MB, 100 pages, text-layer required.
10. LangGraph human-in-the-loop `interrupt` is deferred to Phase 2. In the MVP, accept/edit/reject are plain REST writes after the run finishes.
11. Eval match threshold: normalized token F1 of at least 0.5 between the quote and gold span.
12. Two Postgres databases (app data, LangGraph checkpoints) on one server.
13. One Qdrant collection filtered by `contract_id`, not one collection per contract.
14. `create_all` for tables in the MVP, Alembic in Phase 2.
15. LangSmith (not Langfuse) for tracing, in Phase 1 instead of Phase 3 (owner's request, 2026-11-23). Opt-in through environment variables, so the default setup sends nothing off the machine.

## 14. Left to the builder

Prompt wording, chunk size and overlap, top-k tuning, exact Pydantic field names, UI styling, folder-internal file splits, choice between Qdrant native hybrid and own RRF, and embedding library packaging, as long as the acceptance criteria and constraints hold.

## Appendix: Phase 0 spike results (fill in)

- S1: PASS. Model `nvidia/nemotron-3-ultra-550b-a55b:free` through `ChatOpenRouter` (`langchain-openrouter` 0.3.0), `with_structured_output(ClauseExtraction, method="function_calling", include_raw=True)`: valid 10/10 (threshold 9/10) on 10 different inputs (first 2 spike contracts x 5 playbook clauses, up to 3 keyword-matched pages of PDF text as context, no gold, no cache). Error types: none. Median latency 9.24 s (range 7.1 to 21.1 s). Plain chat call returned `pong`. Reasoning leak: 0 flags (no `<think>`-style markers in `quote` or `reasoning`). The raw messages carry reasoning content on 10 of 10 calls, and the parsed objects were clean, so parse only the tool call. Verbatim rate (information only): only 2 of the 10 results carried a quote, and 1 of those 2 was a whitespace-normalized substring of the context, so the `verify` node is needed. The low quote count says little about model recall: the spike context is the first 3 pages that contain any query term, and for Governing Law that was pages 1 to 3 (Rand) and 6, 7, 14 (Bluerock) while the clause is on pages 9 to 10 and 43, so `found=false` was often the right answer for what the model saw. S1 proves schema validity, not extraction quality; Phase 1 retrieval and the eval measure that. The `json_prompt` fallback mode was not run (not needed). Model listing (OpenRouter `/api/v1/models`): context 1,000,000 tokens; `supported_parameters` include `tools`, `tool_choice`, `reasoning`, `include_reasoning`, `max_tokens`, `seed`, `temperature`, `top_p` and do NOT include `response_format` or `structured_outputs`, so function calling is the right method. Free-tier limits: the docs say limits depend on credits purchased and are enforced per minute and per day for `:free` variants, and a 429 carries `X-RateLimit-*` headers; the numeric table is rendered by JavaScript and was not readable by script, so the exact per-minute and per-day numbers are NOT verified (owner: check https://openrouter.ai/docs/api-reference/limits; the real remaining daily count is in `GET /api/v1/key`, field `free_model_daily_requests`). Results in `data/spikes/s1_function_calling.json`.
- S2: PASS. Layout under `data/cuad/`: `CUAD_v1.json`, `CUAD_v1_README.txt`, `master_clauses.csv`, `full_contract_pdf/Part_I..Part_III` (nested subfolders), `full_contract_txt/`, `label_group_xlsx/`. JSON is SQuAD-style: `{version, data: [{title, paragraphs: [{qas, context}]}]}`, 1 paragraph per contract, 41 QA entries per contract, each `{id: "<title>__<Label>", question, answers: [{text, answer_start}], is_impossible}`. `title` has no file extension. Contracts: 510 in JSON, 510 PDFs, 511 txt. The label comes from the `id` suffix after the last `__` (the quoted string in `question` gives the same 41 values). The 5 exact label strings are unchanged from section 6.6: `Governing Law`, `Termination For Convenience`, `Cap On Liability`, `Non-Compete`, `Anti-Assignment`. Present/absent per label (non-empty stripped answer = present): Governing Law 437/73, Termination For Convenience 183/327, Cap On Liability 275/235, Non-Compete 119/391, Anti-Assignment 374/136. Gold parser `backend/evals/cuad.py` has 14 unit tests passing. PDF matching: exact stem matched 505 of 510. The 5 misses: trailing space in the PDF filename (2), trailing `-` in the stem (1), extra `_Option Agreement` suffix in the stem (1), Unicode NFC vs NFD (1). Owner approved a unique-prefix fallback: exact, then normalized (NFC, strip, casefold), then a unique prefix match, logged. Result: 510 of 510 matched, one PDF per title, 0 unmatched. 2 contracts match by prefix, so their gold-to-PDF link relies on that rule (the NETGEAR title and the Harpoon `Development Agreement` title).
- S3: PASS (3 of 3). PyMuPDF 2.1 on the 3 `Governing Law` contracts picked with `random.Random(42).sample` over the sorted present-and-matched titles. The test string is the longest gold span of the contract (CUAD lists answers out of document order and one is a fragment: the first run took the 1-word fragment `state.` for Rand Worldwide and was wrong; fixed after review). Contracts: `RandWorldwideInc_20010402_8-KA_EX-10.2_2102464_EX-10.2_Co-Branding Agreement` (11 pages, clause starts on page 9 and continues onto page 10), `BLUEROCKRESIDENTIALGROWTHREIT,INC_06_01_2016-EX-1.1-AGENCY AGREEMENT` (47 pages, gold page 43), `ALAMOGORDOFINANCIALCORP_12_16_1999-EX-1-AGENCY AGREEMENT` (24 pages, gold page 23). No empty pages. `locate` reports the first page containing the span; the clause text was found within a single page on all 3 (no page-break join was needed). The span was found after whitespace collapse and casefold only; the quote/dash/soft-hyphen mapping and `sort=True` fallbacks were not needed on these 3, so Phase 1 normalization stays unproven for those cases. `page.search_for` on the collapsed span returned a hit on all 3 (3, 1, 2 rectangles). Word-level matching of consecutive `get_text("words")` tokens hit on all 3; `word_rects` is the token count of the matched run (31, 19, 15), not a count of distinct rectangles. Results in `data/spikes/s3.json`.
- S4: PASS on Python 3.14 (fallback taken). Python 3.15 failed: 3.15.2 (final release, not a beta) with uv 0.13.9; `uv add fastembed` unsatisfiable because `onnxruntime` has no `cp315` wheels (wheels exist only up to `cp313` for the versions fastembed accepts there). All other dependencies resolved on 3.15 (pymupdf, psycopg, pydantic-core). On 3.14.10: full dependency set installs (fastembed 0.9.1, onnxruntime 1.32.0, langchain-openrouter 0.3.0, langchain-qdrant 1.1.0, langgraph 1.2.24, pymupdf 2.1), psycopg impl `binary`. Qdrant `v1.20.2` pinned. Postgres host port is 5434 (5432 was taken by another local container). Smoke checks: `PASS checkpointer`, `PASS sqlmodel`, `PASS qdrant`; checkpoint tables created, no leftover probe table. Spec C7, section 6.2, section 11 and the other 3.15 mentions were updated to 3.14 and port 5434 after owner approval.
- S5: PASS (3 of 3) in hybrid mode, no fallback used (`rank-bm25` not added). `langchain-qdrant` 1.1.0 `QdrantVectorStore` + `RetrievalMode.HYBRID`, dense `BAAI/bge-small-en-v1.5` through a spike-local FastEmbed adapter, sparse `FastEmbedSparse("Qdrant/bm25")`, Qdrant `v1.20.2`. Chunks: 800 characters, 150 overlap, per page. Collection config: unnamed dense vector (384, cosine) plus sparse vector `langchain-sparse`. Payload layout is nested: `metadata.contract_id`, `metadata.page`, `metadata.chunk_id`, plus `page_content`, so the filter key is `metadata.contract_id`. First run with the original `governing_law` query terms: 2 of 3 (Alamogordo missed: its clause says "construed in accordance with", not "governed by"; top 8 pages `[11, 4, 16, 20, 21, 15, 15, 16]`, gold page 23). Owner chose to improve the query terms: added "construed in accordance with", "choice of law", "applicable law" to `governing_law.query_terms` in `playbook/playbook.yaml`. Second run: 3 of 3, 0 foreign results; `gold_page` ranked 1st for Bluerock and Alamogordo and 2nd for Rand Worldwide (gold page 9; its clause continues on page 10, which ranked 1st). Rerun after the S3 span fix, same outcome. Caveat: the added terms were chosen after seeing one miss on these same 3 contracts, so 3 of 3 does not measure generalization. The phrasings are standard legal wording, but Phase 1 must check recall on a larger sample. Results in `data/spikes/s5.json`.
