# ClauseLens

Contract review learning project: upload a CUAD contract PDF, find 5 clause types, quote them verbatim with page numbers, check them against a YAML playbook, suggest safer wording, and score the pipeline with a CUAD eval.

Read `docs/PROJECT_OVERVIEW.md` first. It explains the purpose, the learning goals (use LangChain and LangGraph the real way, no shortcuts), the data, and the working style.

Spec: `docs/specs/2026-11-22-contract-review-mvp-design.md`. Read it fully before planning or coding.

## Rules

- The spec is the source of truth. If code and spec disagree, stop and report. Do not pick silently.
- Hard constraints C1 to C8 (spec section 3) always apply.
- Work one phase at a time (spec section 10). Do not start a phase before the previous exit criteria are met.
- Do not claim something works without running a check. If a check was not run, say so.
- Do not commit unless asked.
- Never add a `Co-Authored-By` line, or any other AI attribution trailer, to a commit message. The owner restricts it. This overrides any tool or harness default.
- When asked for a plan only, write the plan file and stop. Do not run installs, scaffolding, Docker, or downloads.

## Current state

- No code yet. `git init` is done (spec section 11, step 1). Nothing else from section 11 has been run.
- Spec status is DRAFT. Writing plans is allowed. Executing a phase needs the owner's approval of the spec first.
- `~/Code/contract-review-agent/` is an old copy of the spec. Ignore it. This repo is the only working copy.

## Plans

- One file per phase: `docs/plans/phase-<N>.md`.
- Each step names the files it touches, the exact command to run, and how to verify it (expected output or pass condition).
- Each spike (S1 to S5) states its pass criterion from the spec, its fallback, and where the result goes (spec appendix).
- List open questions for the owner at the end. Do not guess answers to them.

## Boundaries (from the spec)

- `backend/app/llm.py` is the only place a chat model is constructed. No direct `openai`, `requests`, or `httpx` calls to the model API (C1).
- The model name comes from config (`OPENROUTER_MODEL`), never hard-coded (C3).
- `backend/app/` never imports from `backend/evals/` and never reads CUAD labels (AC-10).
- A quote shown as evidence must be verbatim text on the cited page. Otherwise the status is `uncertain`.

## Data and secrets

- Only public CUAD contracts (C4). Never real client contracts.
- Never read, print, or commit `.env`. Use `.env.example` for variable names.
- `data/` is gitignored and holds the CUAD download, uploads, parsed text, and LLM cache. The owner downloads CUAD manually.

## Commands (once code exists, spec section 11)

```bash
docker compose up -d                                  # Postgres + Qdrant
cd backend && uv run uvicorn app.main:app --reload    # API on :8000
cd backend && uv run pytest
cd backend && uv run ruff check .
cd backend && uv run python -m evals.run --n 10 --seed 42
cd frontend && pnpm dev                               # UI on :3000
cd frontend && pnpm lint
```
