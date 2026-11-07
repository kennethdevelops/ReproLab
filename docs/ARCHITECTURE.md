# Architecture

See spec §5 for the target diagram. This page records what exists and how it fits together.

## Services (docker-compose.yml)

| Service | Image / target | Networks | Role |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:0.8.0-pg16` | core | Canonical store: projects, snapshots, runs, steps, evidence metadata, chunks |
| `redis` | `redis:7.4-alpine` | core | Celery broker only (not run history) |
| `migrate` | backend `app` | core | One-shot `alembic upgrade head` + demo seed |
| `api` | backend `app` | core, edge | FastAPI, `/healthz`, `/readyz`, `/api/v1/*`, SSE |
| `worker-indexing` | backend `app` | core, edge | Celery queue `indexing`: fetch, parse, chunk, embed |
| `worker-investigation` | backend `browser` (Playwright Python image) | core, sandbox, edge | Celery queue `investigations`: LangGraph agent + Chromium |
| `demo-target` | demo-target | sandbox, edge | Buggy storefront the agent investigates |
| `demo-target-fixed` | demo-target | sandbox, edge | Fixed variant; validation/evaluation only |
| `frontend` | frontend | edge | Static React build |
| `test-runner` | Node + Playwright Test | sandbox only | Compiles restricted JSON test specs and runs them against fixtures |

`core` and `sandbox` are Docker `internal` networks: containers on them alone have no outside route.

## Fixture variants

The demo store's defects live in its normal source tree (`demo-target/src`, `demo-target/server`). The corrected implementations live in `demo-target/fixtures/fixed/` and are swapped in at build time by a Vite resolve plugin (client) and a module loader (server). Consequences:

- The indexed source is exactly what a developer of the buggy app would see; there are no `if (BUG_D01)` switches.
- The fixture mode is selected by which process is serving (`--mode buggy|fixed`), never by anything in the page.
- Oracles (`demo-target/fixtures/oracles/`) assert correct behaviour. `scripts/verify-oracles.mjs` requires each oracle to pass on the fixed build and to fail on the buggy build inside a step titled `oracle:`; a failure during `setup:` counts as a mismatch.

## Backend package

`backend/src/reprolab/`: `api/` (routes, error envelope), `config/` (settings), `db/` (models, session, seed), `observability/` (JSON logs, request IDs), `workers/` (Celery), plus packages filled in by later milestones (`agent/`, `browser/`, `retrieval/`, `indexing/`, `reports/`, `artifacts/`, `evaluation/`, `github/`).

## Data model

Migration `0001` creates `projects`, `repo_snapshots`, `investigations`, `investigation_events` (ordered SSE log), `agent_steps`, `evidence_assets`, `findings`, `generated_tests` and enables the `vector` extension. Retrieval tables arrive with M3.
