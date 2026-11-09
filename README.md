# ReproLab

ReproLab takes a bug report for a web app and tries to reproduce it in a real browser. An LLM agent drives Chromium through a small set of tools. It can optionally search the app's source code. The output is a report backed by screenshots, a trace and quoted page text, plus a Playwright regression test when the bug is reproduced.

The point of the project is the part around the model. Navigation limits, budgets and the decision on whether a bug was reproduced all live in code, and the model cannot override them.

It ships with a small demo storefront that has known defects, a buggy and a fixed build of it, and a benchmark built on top of both.

## The problem

Turning "the coupon disappears when I reload checkout" into a reliable reproduction takes time, and LLM agents asked to do it tend to report success without proof. ReproLab treats every model claim as a proposal:

- A `reproduced` status survives only if each piece of evidence the model quotes appears verbatim in a browser observation recorded *after* a page interaction. Otherwise the run is downgraded to `inconclusive` and the report shows the rejected claim.
- Source code found through retrieval can support a root-cause hypothesis. It never counts as reproduction evidence.
- The regression test is assembled from the recorded browser steps. The model contributes only a statement of the expected behaviour, never code. On the demo store the test must fail on the buggy build *at an assertion* and pass on the fixed build before it is marked `validated`.

## How it works

```
 React UI ──HTTP/SSE──▶ FastAPI ──Celery/Redis──▶ workers
                           │                        │
                PostgreSQL + pgvector       ┌───────┴──────────────┐
                (runs, steps, evidence,     │ indexing worker      │ snapshot → chunks → embeddings
                 chunks, retrieval log)     │ investigation worker │ LangGraph agent + Playwright ──▶ model provider
                                            └───────┬──────────────┘
                                   sandbox network  │ (internal, no outside route)
                       ┌────────────────────────────┼────────────────────────┐
                       ▼                            ▼                        ▼
               demo store (buggy)           demo store (fixed)        test runner (Node,
                                                                       JSON specs only)
```

1. **Investigate.** A LangGraph state machine alternates model turns and tool calls. Browser tools are typed and allowlisted: open a path, click, fill, read text, screenshot. Every request and redirect is checked against the project's origin. Step, model-call, token, time and cost budgets are checked before each call.
2. **Retrieve (optional).** With `rag_mode` set, the agent gets `search_code` and `read_source` over an indexed snapshot of the repository: PostgreSQL full-text search and pgvector, fused with reciprocal rank fusion. Retrieved text is fenced as untrusted input.
3. **Verify.** `agent/verification.py` decides the final status from the recorded steps.
4. **Generate a test.** A separate Node service accepts only an allowlisted JSON spec, generates the `.spec.ts` deterministically and, for the demo store, runs it against both builds.
5. **Report.** Live progress over SSE, a step timeline, screenshots, a Playwright trace, Markdown/JSON export.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SECURITY.md](docs/SECURITY.md). Design decisions are recorded in [docs/ADR/](docs/ADR/).

## Quick start (Docker)

You need Docker with Compose (on Windows, Docker Desktop with WSL2) and a model that supports tool calling. See the next section.

```bash
cp .env.example .env
# edit .env: POSTGRES_PASSWORD, DEMO_ADMIN_TOKEN, and one model preset
docker compose up --build -d
```

- UI: http://localhost:3000 (API docs at http://localhost:8000/docs)
- Demo store: buggy build on http://localhost:4173, fixed build on http://localhost:4174

The stack seeds a demo project pointing at the buggy store. Open it in the UI, paste one of the bug reports from `benchmarks/cases/cases.v1.json` and start an investigation.

To let the agent search the demo store's code, export a snapshot and index it from the **RAG Explorer** page:

```bash
cd backend && uv run python -m reprolab.indexing.local_snapshot export --out ../data/snapshots
```

Running without Docker is covered in [docs/SETUP.md](docs/SETUP.md). On Windows without `make`, `scripts/rl.ps1 <target>` mirrors the Makefile.

## Bring your own model

There is no default model. Until you set one, investigations stop with `PROVIDER_NOT_CONFIGURED`. Pick a preset in `.env`:

| Provider | `.env` |
|---|---|
| Groq | `LLM_PROVIDER=openai_compatible`<br>`LLM_BASE_URL=https://api.groq.com/openai/v1`<br>`LLM_MODEL=openai/gpt-oss-120b`<br>`LLM_API_KEY=gsk_...` |
| Gemini | `LLM_PROVIDER=openai_compatible`<br>`LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`<br>`LLM_MODEL=<model>`<br>`LLM_API_KEY=...` |
| Ollama | `LLM_PROVIDER=openai_compatible`<br>`LLM_BASE_URL=http://localhost:11434/v1` (from Docker: `http://host.docker.internal:11434/v1`)<br>`LLM_MODEL=<model with tool calling>` |
| Anthropic | `LLM_PROVIDER=anthropic`<br>`LLM_MODEL=<model id>`<br>`ANTHROPIC_API_KEY=...` |
| OpenAI or any OpenAI-compatible server (LM Studio, vLLM, OpenRouter) | `LLM_PROVIDER=openai_compatible`<br>`LLM_BASE_URL=<server>/v1`<br>`LLM_MODEL=<model>`<br>`LLM_API_KEY=...` (OpenAI: also `LLM_STRICT_TOOLS=true`) |

Check that the model answers with a tool call before running anything:

```bash
cd backend && uv run python -m reprolab.agent.check_model
```

Notes:

- The model must support function calling. On an 8 GB GPU, the local models I tried either ran out of memory or answered without calling tools.
- Gemini models return a `thought_signature` with tool calls. The adapter echoes it back, as Gemini requires.
- Rate limits from free tiers are reported as `PROVIDER_RATE_LIMITED` and the run ends without a final assessment. Transient errors are retried.
- Cost is estimated only for models in the price table or in `LLM_PRICES_FILE`. Other models run under token, step and time budgets, and their cost shows as "not estimated".
- `LLM_RECORD_PATH` records a live run. `LLM_PROVIDER=replay` plays it back through the real browser and verification, labelled `replay:<model>`. A replay says nothing about model quality.

Every variable is listed in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Results

**Retrieval** (published): Recall@5 is 0.667 for lexical, 0.722 for vector and 0.778 for hybrid, over the three demo cases. Three queries make this an anecdote, not a statistic. See [docs/EVALUATION.md](docs/EVALUATION.md).

**Agent benchmark: pending.** It is running on Groq's free tier, which allows 200k tokens per day, so a full pass (3 cases × buggy/fixed × RAG off/on × 2 runs) spans several days. Rows that ended in a rate limit are not results and are not published.

So far one real-model result is verified: `openai/gpt-oss-120b` (via Groq) reproduced D01, the coupon lost on reload, on the buggy store, and the verification code accepted its evidence. One run on one case shows the pipeline works with a real model. It does not measure agent quality.

How the benchmark is run: [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Limits

- Agent quality is not measured yet (see above). The end-to-end tests use a scripted stub model against a real browser. They cover tools, budgets, verification and test validation, not how well a model investigates.
- The demo store has ten planned defects. Three (D01, D02, D05) have oracles and benchmark cases.
- Regression tests are executed only against the demo store's two builds. For any other target the generated test is for a person to review and is never run.
- Origin limits are enforced at the application level, on every browser request. The investigation worker also needs outbound access to the model provider, and a network-level egress proxy is not built. Do not point it at sites you don't control. See [docs/SECURITY.md](docs/SECURITY.md).
- Screenshots and traces are stored unredacted. The demo store only contains synthetic data.
- Retrieval uses a regex-based chunker and no ANN index, which is fine for a small repository and not tuned for large ones ([ADR-0003](docs/ADR/0003-chunking-and-vector-index.md)).
- There is no authentication. It is a local, single-user tool.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI API, Celery workers, agent, browser tools, indexing and retrieval (Python 3.12, `uv`) |
| `frontend/` | React + Vite + Tailwind UI |
| `demo-target/` | Demo storefront: buggy source, fixed overlays, oracle tests |
| `test-runner/` | Isolated Node service that validates JSON test specs and runs them with Playwright Test |
| `benchmarks/` | Cases, ground truth (evaluation only), published results |
| `docs/` | Setup, configuration, architecture, security, evaluation, ADRs |

## Development

```bash
cd backend && uv sync && uv run pytest && uv run ruff check . && uv run mypy
cd frontend && npm ci && npm run lint && npm run typecheck && npm test
cd demo-target && npm ci && npm run build && npm test && npm run verify-oracles -- --runs 2
cd test-runner && npm ci && npm test
```

Integration and browser tests need PostgreSQL with pgvector. See [docs/SETUP.md](docs/SETUP.md#tests).

## Licence

MIT. See [LICENSE](LICENSE).
