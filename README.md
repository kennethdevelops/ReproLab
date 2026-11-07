# ReproLab

AI-assisted web bug investigation. You give ReproLab a bug report and an authorised test target. A tightly constrained Playwright browser agent tries to reproduce the bug. Optionally, it searches the application's repository with hybrid RAG. ReproLab then produces an evidence-backed report and, when the bug is reproduced, a Playwright regression test. For the demo store, that test is checked automatically: it must fail on the buggy build and pass on the fixed one.

> **Status: portfolio project, feature-complete for its scope.** Exact verified results, including what is *not* verified yet, are in [`docs/PROGRESS.md`](docs/PROGRESS.md). Evaluation numbers on real models are not published yet.

## What it does

1. **Investigate.** An agent (LangGraph state machine) drives a real Chromium through a small allowlisted tool set: open a path, click, fill, read text, take screenshots. Navigation is limited to the project's origin. Step, time, token and cost budgets are enforced in code.
2. **Verify, don't trust.** The model only *proposes* a status. `reproduced` survives only if every quoted piece of evidence appears verbatim in a recorded browser observation made after a page interaction. Otherwise the run becomes `inconclusive`, and the rejected claim is shown.
3. **Retrieve (optional, `rag_mode`).** `search_code` and `read_source` query an indexed snapshot of the repository: Postgres full-text search plus pgvector, fused with RRF. Retrieved text is fenced as untrusted data. It can ground root-cause hypotheses, but it can never count as reproduction evidence.
4. **Propose a regression test.** The test is built deterministically from the recorded browser steps plus the model's statement of correct behaviour. The model never writes code. A separate, isolated Node runner accepts only an allowlisted JSON spec and generates the `.spec.ts`. For demo projects, the runner executes the test against the buggy and fixed fixtures. A test is marked `validated` only if it fails on buggy *at an assertion* and passes on fixed. A selector failure counts as `invalid`, not as a detected bug.
5. **Report.** Markdown/JSON export, screenshots, Playwright trace, a step timeline and live progress over SSE.

## Architecture

```
 Browser UI (React)  ──HTTP/SSE──▶  FastAPI  ──Celery/Redis──▶  workers
                                       │                          │
                                PostgreSQL + pgvector       ┌─────┴──────────────┐
                                (runs, steps, evidence,     │ indexing worker    │  snapshot → chunks → fastembed
                                 chunks, retrieval events)  │ investigation      │  LangGraph agent + Playwright
                                                            │ worker             │──▶ model provider (BYOM)
                                                            └─────┬──────────────┘
                                                  sandbox network │ (internal)
                                         ┌────────────────────────┼─────────────────────┐
                                         ▼                        ▼                     ▼
                                  demo store (buggy)     demo store (fixed)     test runner (Node,
                                                                                JSON specs only)
```

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/SECURITY.md`](docs/SECURITY.md), and the ADRs in [`docs/ADR/`](docs/ADR/).

## Bring your own model

Set `LLM_PROVIDER` in `.env`. `.env.example` has ready presets.

| Provider | Use for | Settings |
|---|---|---|
| `anthropic` | Claude via the official SDK | `ANTHROPIC_API_KEY`, `LLM_MODEL` |
| `openai_compatible` | Ollama, LM Studio, vLLM, OpenAI, Gemini, Groq, OpenRouter… | `LLM_BASE_URL`, `LLM_MODEL`, optional `LLM_API_KEY` |
| `replay` | Re-running a transcript recorded earlier with `LLM_RECORD_PATH` | `LLM_REPLAY_PATH` |

The model must support tool (function) calling. Check your setup:

```bash
cd backend && uv run python -m reprolab.agent.check_model
```

Replay runs are labelled `replay:<model>` everywhere. They exercise the real browser, verification and test validation, but they say nothing about model quality. Models with no entry in the price table (or in `LLM_PRICES_FILE`) run under token, step and time budgets only. Their cost shows as "not estimated".

## Quick start (Docker)

Prerequisites: Docker Desktop (Windows: with WSL2) or Docker Engine + Compose.

```bash
cp .env.example .env          # set POSTGRES_PASSWORD, DEMO_ADMIN_TOKEN and a model provider
docker compose up --build -d  # migrations, demo project seed, all services
```

- Web UI: http://localhost:3000. The API docs are at http://localhost:8000/docs.
- Demo store: buggy at http://localhost:4173, fixed at http://localhost:4174.
- To use RAG on the demo project, export a snapshot first: `cd backend && uv run python -m reprolab.indexing.local_snapshot export --out ../data/snapshots`. Then click **Index** on the RAG Explorer page.

Windows without `make`: `.\scripts\rl.ps1 <target>` mirrors the Makefile targets.

## Development without Docker

```bash
cd backend && uv sync && uv run pytest            # unit + security tests
cd frontend && npm ci && npm test && npm run dev
cd demo-target && npm ci && npm run build && npm run verify-oracles -- --runs 2
cd test-runner && npm ci && npm test              # spec allowlist + real buggy/fixed validation
```

Integration and browser tests need a disposable PostgreSQL with pgvector whose database name contains `test`, plus the built demo store:

```bash
DATABASE_URL=postgresql+psycopg://user@host:5432/reprolab_test uv run pytest -m "integration or browser"
```

## Honest limits

- **Agent quality on real models is not measured yet.** End-to-end tests use a scripted stub model against the real browser. They prove the tools, budgets, verification and test validation, not how well an LLM investigates. The benchmark harness (M6) and published per-model results are the next step.
- **Three of ten demo defects have oracles** (D01 coupon lost on reload, D02 stale subtotal, D05 filter lost on pagination). The others are out of scope for now.
- **Regression tests run automatically only against the demo fixtures.** For other targets the test is generated for human review and never executed.
- **Docker stack not yet verified end to end** on the development machine (no WSL2 there yet). CI has not run because the repository has not been pushed.
- **Egress:** the browser's origin allowlist is enforced in code on every request. A network-level egress proxy for public deployments is designed but not built (see `docs/SECURITY.md`).
- Small local models (7-8B) may call tools poorly. Results must always name the model used.

## Repository

| Path | Contents |
|---|---|
| `backend/` | FastAPI API, Celery workers, agent, retrieval (Python 3.12+, `uv`) |
| `frontend/` | React + Vite + Tailwind UI |
| `demo-target/` | Synthetic storefront with injected defects, fixed variants and oracle tests |
| `test-runner/` | Isolated Node Playwright Test validator for restricted JSON test specs |
| `benchmarks/` | Public cases, private ground truth, runners, measured results |
| `docs/` | Plan, progress, architecture, security, ADRs |

## Licence

MIT (pending owner confirmation). See [`LICENSE`](LICENSE).
