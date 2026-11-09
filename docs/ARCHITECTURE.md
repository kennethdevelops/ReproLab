# Architecture

## Services

All services are defined in `docker-compose.yml`.

| Service | Image / target | Networks | Role |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:0.8.0-pg16` | core | Projects, snapshots, runs, steps, evidence metadata, chunks, retrieval events |
| `redis` | `redis:7.4-alpine` | core | Celery broker only. Run history lives in PostgreSQL. |
| `migrate` | backend `app` | core | One-shot `alembic upgrade head` and demo project seed |
| `api` | backend `app` | core, edge | FastAPI: `/healthz`, `/readyz`, `/api/v1/*`, SSE event stream |
| `worker-indexing` | backend `app` | core, edge | Celery queue `indexing`: fetch, chunk, embed |
| `worker-investigation` | backend `browser` (Playwright Python image) | core, sandbox, edge | Celery queue `investigations`: agent + Chromium |
| `demo-target` | demo-target | sandbox, edge | Buggy demo store, the investigation target |
| `demo-target-fixed` | demo-target | sandbox, edge | Fixed build, used only for test validation and evaluation |
| `test-runner` | Node + Playwright Test | sandbox | Compiles restricted JSON test specs and runs them against the two builds |
| `frontend` | frontend | edge | Static React build |

`core` and `sandbox` are Docker `internal` networks. A container attached only to them has no route out. `edge` is a normal bridge for published ports and outbound calls (model provider, GitHub).

## An investigation, step by step

1. `POST /api/v1/projects/{id}/investigations` stores the bug report and the chosen `rag_mode`. The request cannot set origins, limits, model or prompt (`extra="forbid"`). The API enqueues a Celery task.
2. The worker builds the allowed origin list from the project (plus `LOCAL_EXTRA_ALLOWED_ORIGINS` in local mode), opens a fresh browser context and starts the agent.
3. The agent (`agent/investigator.py`) is a LangGraph graph: `model_turn → execute_tools → model_turn … → finalize`. Before every model call and browser action it checks cancellation and the step, call, token, time and cost budgets.
4. Tools (`agent/tool_specs.py`, validated with Pydantic in `browser/actions.py`):
   - page changes: `open_page`, `click`, `fill`, `press`, `select_option`, `reload_page`, `go_back`, `wait_for`
   - observations: `read_page_snapshot`, `read_visible_text`, `read_current_url`, `read_console_errors`, `read_network_errors`, `capture_screenshot`
   - retrieval, only when `rag_mode` is not `none`: `search_code`, `read_source`
   - control: `record_plan`, `finish_with_assessment`

   There is no `evaluate()` and no free-form script tool. Unknown tools and invalid arguments are returned to the model as errors.
5. Every step, event and console/network log is redacted (`observability/redaction.py`) before it is stored. Events are appended to `investigation_events` with a sequence number, which the SSE endpoint replays from `Last-Event-ID`.
6. `finish_with_assessment` carries the model's proposed status, the quotes it relies on and its hypotheses. `agent/verification.py` accepts `reproduced` only if each quote appears verbatim in a successful observation step that follows a page-changing step. Otherwise the status becomes `inconclusive`, and the report keeps the rejected claim and the reason.
7. For a verified reproduction, `reports/regression_test.py` builds a JSON test spec from the recorded steps plus the model's `regression_check`, a statement of expected behaviour. The test runner validates the spec against its allowlist, generates `.spec.ts` and, for demo projects, runs it on both builds:
   - `validated`: fails on buggy at an assertion, passes on fixed
   - `invalid`: ran, but not in that pattern (for example a bad selector fails during setup)
   - `unvalidated`: generated but not run (non-demo target, or no runner configured)

## Indexing and retrieval

- **Sources:** an operator-exported local snapshot (`python -m reprolab.indexing.local_snapshot export`) or a public GitHub repository pinned to a commit SHA. Only an explicit include list is read. `benchmarks/ground-truth/`, `demo-target/fixtures/` and `.git` are excluded in `indexing/paths.py`, and security tests assert it.
- **Chunking:** a regex-based chunker that splits code at top-level declarations and Markdown at headings, with overlapping windows for long declarations. Each chunk is exactly its cited line range of the stored document ([ADR-0003](ADR/0003-chunking-and-vector-index.md)).
- **Embeddings:** fastembed (`BAAI/bge-small-en-v1.5`, local ONNX). The model name and dimension are stored per snapshot. Unchanged chunks reuse their embeddings when a snapshot is replaced.
- **Search** (`retrieval/search.py`): PostgreSQL `tsvector` ranking and pgvector cosine distance, each over `RETRIEVAL_CANDIDATES`, fused with reciprocal rank fusion (`k = RETRIEVAL_RRF_K`). No ANN index; exact search is fast enough at this size.
- **In the agent:** results come back inside a fence the content cannot close, labelled as untrusted repository text. Retrieval steps are logged as retrieval events and never count as browser evidence.

## Demo store and its fixed build

The defects live in the store's normal source tree (`demo-target/src`, `demo-target/server`). The corrected files live in `demo-target/fixtures/fixed/` and replace the originals at build time: through a Vite resolve plugin for the client and a module loader for the server. So:

- The indexed source is what a developer of the buggy app would see. There are no `if (BUG_D01)` switches.
- Which build is served depends on the process (`--mode buggy|fixed`), not on anything in the page.
- Oracles (`demo-target/fixtures/oracles/`) assert the correct behaviour. `scripts/verify-oracles.mjs` requires each oracle to pass on fixed and to fail on buggy inside a step titled `oracle:`. A failure during `setup:` counts as a mismatch.

## Backend package

`backend/src/reprolab/`

| Package | Contents |
|---|---|
| `api/` | Routes, error envelope, SSE |
| `agent/` | LangGraph agent, model adapters (`model_client.py`, `openai_compatible.py`, replay), tool specs, verification, retrieval tool, `check_model` |
| `browser/` | Navigation policy, typed actions, Playwright session |
| `indexing/`, `retrieval/`, `github/` | Snapshot sources, chunking, embeddings, search |
| `reports/`, `artifacts/` | Result model, Markdown export, regression-test specs, artifact storage |
| `evaluation/` | `retrieval_eval`, `agent_bench` |
| `db/` | SQLAlchemy models, enums, seed. Schema changes go through Alembic (`backend/alembic/`). |
| `workers/` | Celery app and tasks |
| `observability/` | JSON logs, request IDs, redaction |
| `config/` | Settings ([CONFIGURATION.md](CONFIGURATION.md)) |

## Data model

Migration `0001` creates `projects`, `repo_snapshots`, `investigations`, `investigation_events`, `agent_steps`, `evidence_assets`, `findings` and `generated_tests`, and enables `vector`. Migration `0002` adds the source index: documents, chunks with `tsvector` and `vector` columns, and retrieval events.

Investigation statuses: `queued`, then working states (`planning`, `retrieving`, `browsing`, `analysing`, `reporting`), ending in one of `reproduced`, `not_reproduced`, `inconclusive`, `blocked` (for example no provider configured or rate-limited before any work), `cancelled` or `failed`.
