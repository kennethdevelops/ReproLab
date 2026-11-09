# Configuration reference

The backend reads its settings with pydantic-settings, in this order (later wins): `../.env`, `backend/.env`, real environment variables. Names are case-insensitive. An empty value (`KEY=`) means "not set". `docker-compose.yml` overrides a few values for the containers. Those are marked *Compose sets this*.

The source of truth is `backend/src/reprolab/config/settings.py`. `.env.example` lists the variables most people need.

## Application

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `local` | Free-form environment label. Not read anywhere yet. |
| `APP_MODE` | `local` | `local` or `public_demo`. Public-demo mode refuses the stub model and ignores `LOCAL_EXTRA_ALLOWED_ORIGINS`. |
| `API_BASE_URL`, `WEB_BASE_URL` | `http://localhost:8000`, `http://localhost:3000` | Reserved; not read anywhere yet. The UI's API URL is `VITE_API_BASE_URL`. |
| `DATABASE_URL` | `postgresql+psycopg://reprolab:reprolab@localhost:5432/reprolab` | SQLAlchemy URL. *Compose sets this* from the `POSTGRES_*` values. Tests require `test` in the database name; the agent benchmark requires `test` or `eval`. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `reprolab` | Used by Compose to create the database and build `DATABASE_URL`. Not read by the backend directly. |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker. *Compose sets this.* |
| `ARTIFACTS_DIR` | `./data/artifacts` | Screenshots, traces and generated tests. *Compose sets this* to a volume. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated browser origins allowed to call the API. |

## Model provider

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `openai_compatible` | `anthropic`, `openai_compatible` or `replay`. `stub` exists for tests and is refused in public-demo mode. |
| `LLM_MODEL` | *(empty)* | Model id as the provider names it. Required. Without it, runs end `blocked` with `PROVIDER_NOT_CONFIGURED`. |
| `LLM_BASE_URL` | *(unset)* | `openai_compatible` only: base URL ending in `/v1` (or the provider's equivalent). |
| `LLM_API_KEY` | *(unset)* | `openai_compatible` only: bearer key. Local servers usually need none. |
| `ANTHROPIC_API_KEY` | *(unset)* | `anthropic` only. |
| `LLM_EFFORT` | `medium` | `anthropic` only: `low`, `medium`, `high`, `xhigh`, `max`. |
| `LLM_REFUSAL_FALLBACK` | `true` | `anthropic` only: server-side refusal fallback (beta). Set `false` if your account lacks access. |
| `LLM_MAX_TOKENS_PER_CALL` | `8000` | Output token cap per model call. |
| `LLM_TIMEOUT_SECONDS` | `180` | HTTP timeout per model call. |
| `LLM_STRICT_TOOLS` | `false` | Send `strict: true` on function schemas. OpenAI supports it; many local servers reject it. Arguments are validated server-side either way. |
| `LLM_PRICES_FILE` | *(unset)* | JSON price table in USD per million tokens, e.g. `{"my-model": {"input": 0.5, "output": 1.5, "cache_read": 0.05, "cache_write": 0.6}}`. Merged over the built-in table. Unpriced models show cost as "not estimated", and `MAX_RUN_COST_USD` cannot protect them. |
| `LLM_RECORD_PATH` | *(unset)* | Write each live model turn to this JSON file. |
| `LLM_REPLAY_PATH` | *(unset)* | `replay` only: transcript recorded with `LLM_RECORD_PATH`. |

## Embeddings and retrieval

| Variable | Default | Meaning |
|---|---|---|
| `EMBEDDING_PROVIDER` | `fastembed` | `fastembed` (local ONNX model, no key) or `hashing` (deterministic, for tests). |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model name. Stored with each snapshot. Changing it requires re-indexing. |
| `EMBEDDING_CACHE_DIR` | *(fastembed default)* | Where model files are cached. In Compose the default cache path is the `models` volume. |
| `SNAPSHOTS_DIR` | `./data/snapshots` | Directory of operator-exported local snapshots. |
| `GITHUB_API_URL` | `https://api.github.com` | GitHub API base for public-repository indexing. |
| `GITHUB_PUBLIC_REPO_ENABLED` | `true` | Allow indexing public GitHub repositories. |
| `ALLOW_PRIVATE_REPOS` | `false` | Reserved. Private repositories are not supported, whatever this says. |
| `GITHUB_TOKEN` | *(unset)* | Optional, raises GitHub's anonymous rate limit. Read-only access is enough. |
| `MAX_INDEX_FILES` | `2000` | Files per snapshot. |
| `MAX_INDEX_FILE_BYTES` | `200000` | Larger files are skipped. |
| `MAX_INDEX_CHUNKS` | `20000` | Chunks per snapshot. |
| `RETRIEVAL_TOP_K` | `6` | Results returned per search. |
| `RETRIEVAL_CANDIDATES` | `30` | Candidates taken from each of lexical and vector search before fusion. |
| `RETRIEVAL_RRF_K` | `60` | Reciprocal rank fusion constant. |

## Budgets

All are checked in code before each model call or browser action. A run that hits one ends with the reason recorded.

| Variable | Default | Meaning |
|---|---|---|
| `MAX_BROWSER_STEPS` | `25` | Browser tool calls per run. |
| `MAX_RETRIEVAL_CALLS` | `10` | `search_code` + `read_source` calls per run. |
| `MAX_MODEL_CALLS` | `30` | Model calls per run. |
| `MAX_INVESTIGATION_SECONDS` | `300` | Wall-clock limit per run. |
| `MAX_INPUT_TOKENS_PER_RUN` | `400000` | Cumulative input tokens. |
| `MAX_OUTPUT_TOKENS_PER_RUN` | `40000` | Cumulative output tokens. |
| `MAX_RUN_COST_USD` | `1.00` | Estimated cost per run (priced models only). |
| `MAX_CONCURRENT_INVESTIGATIONS` | `1` | Reserved. Concurrency is set by the worker's `--concurrency 1`. |
| `MAX_QUEUED_INVESTIGATIONS` | `10` | New runs are refused while this many are queued or running. |
| `MAX_BUG_REPORT_CHARS` | `4000` | Bug report length limit. |
| `PUBLIC_DEMO_DAILY_COST_CAP_USD` | `2.00` | Reserved for public-demo mode; not enforced yet. |

## Browser scope and demo

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_ALLOWED_ORIGIN` | `http://demo-target:4173` | Origin of the buggy demo store. The seeded project uses it. |
| `DEMO_FIXED_ORIGIN` | `http://demo-target-fixed:4173` | Fixed build, used only for test validation and evaluation, never as an investigation target. |
| `LOCAL_EXTRA_ALLOWED_ORIGINS` | *(empty)* | Comma-separated extra origins allowed in `local` mode. Only add sites you control. |
| `PUBLIC_DEMO_ENABLED` | `false` | Reserved for public-demo mode; not read yet. |
| `DEMO_ADMIN_TOKEN` | *(unset)* | Shared secret for the demo store's `POST /__admin/reset`. Required by Compose and by the test runner. |
| `DEMO_FIXTURE_MODE` | `buggy` | Read by the demo store server: which build to serve. Compose sets it per service. |
| `TEST_RUNNER_URL` | *(unset)* | URL of the `test-runner` service. Unset: no regression tests are generated. *Compose sets this.* |
| `DEMO_CASES_PATH` | `../benchmarks/cases/cases.v1.json` | Public benchmark cases, offered as sample bug reports. |

## Frontend

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | API URL compiled into the UI at build time. Not a secret. |

## Node services

| Service | Variable | Meaning |
|---|---|---|
| `demo-target` | `PORT` (`4173`), `DEMO_FIXTURE_MODE`, `DEMO_ADMIN_TOKEN` | Also accepted as `--port` and `--mode` flags. |
| `demo-target` oracles | `ORACLE_BASE_URL` (`http://localhost:4173`) | Store under test for the Playwright oracles. |
| `test-runner` | `PORT` (`4300`), `HOST` (`127.0.0.1`), `BUGGY_URL`, `FIXED_URL`, `DEMO_ADMIN_TOKEN` | Targets are fixed by environment. A spec cannot choose where it runs. |
