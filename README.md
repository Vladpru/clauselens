# ClauseLens

Contract review learning project: upload a CUAD contract PDF, find 5 clause types, quote them verbatim with page numbers, check them against a YAML playbook, suggest safer wording, and score the pipeline with a CUAD eval.

**Only public CUAD contracts. Never upload real or confidential contracts: the free OpenRouter endpoint may log prompts and outputs.**

## Dev commands

```bash
docker compose up -d                                  # Postgres + Qdrant
cd backend && uv run uvicorn app.main:app --reload    # API on :8000
cd backend && uv run pytest
cd backend && uv run ruff check .
cd backend && uv run python -m evals.run --n 10 --seed 42
cd frontend && pnpm dev                               # UI on :3000
cd frontend && pnpm lint
```

AI-assisted review. Not legal advice.
