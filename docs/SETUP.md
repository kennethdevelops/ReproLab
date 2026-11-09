# Setup

Two ways to run ReproLab: the full stack in Docker, or each service natively for development. Both need a model with tool calling. See [Bring your own model](../README.md#bring-your-own-model) and [CONFIGURATION.md](CONFIGURATION.md).

## Docker

Requirements: Docker Engine with Compose v2, or Docker Desktop. On Windows, Docker Desktop needs WSL2 (`wsl --install` in an admin shell, then reboot).

```bash
cp .env.example .env
```

Edit `.env`:

- `POSTGRES_PASSWORD`: any value. Compose builds `DATABASE_URL` from it for the containers.
- `DEMO_ADMIN_TOKEN`: any value. Compose refuses to start without it. The demo store's reset endpoint requires it.
- A model: `LLM_PROVIDER`, `LLM_MODEL`, and the base URL and key the provider needs. For a model server on the host, such as Ollama, use `http://host.docker.internal:<port>/v1`. `localhost` inside a container is the container.

```bash
docker compose up --build -d
docker compose ps          # migrate should have exited 0; everything else running
docker compose logs -f worker-investigation
```

| Service | URL |
|---|---|
| UI | http://localhost:3000 |
| API, OpenAPI docs | http://localhost:8000/docs |
| Health / readiness | http://localhost:8000/healthz, http://localhost:8000/readyz |
| Demo store, buggy | http://localhost:4173 |
| Demo store, fixed | http://localhost:4174 |

Inside the stack the agent reaches the store at `http://demo-target:4173`. That is the seeded project's origin and the default `DEMO_ALLOWED_ORIGIN`.

### Indexing the demo store for retrieval

The indexer reads operator-exported snapshots. Export one from the host:

```bash
cd backend && uv sync
uv run python -m reprolab.indexing.local_snapshot export --out ../data/snapshots
```

Then open **RAG Explorer** in the UI and click **Index**. The first run downloads the embedding model (`BAAI/bge-small-en-v1.5`, about 130 MB) into the `models` volume.

The snapshot contains only the indexable paths (`demo-target/src`, `server`, `docs`, `tests`). Fixed overlays, oracles and `benchmarks/ground-truth/` are never part of it.

### Stopping and resetting

```bash
docker compose down        # keep data
docker compose down -v     # also delete the database, artifacts and model cache
```

## Native (development)

Requirements:

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 24
- PostgreSQL 16 with the `pgvector` extension
- Redis 7, only if you run the Celery workers

### Backend

```bash
cd backend
uv sync
uv run playwright install chromium
```

Settings are read from `../.env`, then `backend/.env`, then the real environment (later wins). For native runs, point the URLs at localhost:

```dotenv
DATABASE_URL=postgresql+psycopg://reprolab:<password>@localhost:5432/reprolab
REDIS_URL=redis://localhost:6379/0
ARTIFACTS_DIR=./data/artifacts
DEMO_ALLOWED_ORIGIN=http://localhost:4173
DEMO_FIXED_ORIGIN=http://localhost:4174
TEST_RUNNER_URL=http://localhost:4300
```

```bash
uv run alembic upgrade head
uv run python -m reprolab.db.seed
uv run uvicorn reprolab.api.app:create_app --factory --reload --port 8000
```

Workers, in two more shells (on Windows add `--pool solo`):

```bash
uv run celery -A reprolab.workers.celery_app worker -Q investigations --concurrency 1
uv run celery -A reprolab.workers.celery_app worker -Q indexing --concurrency 1
```

### Demo store

```bash
cd demo-target
npm ci
npm run build                                   # builds dist/buggy and dist/fixed
DEMO_ADMIN_TOKEN=<token> node server/index.mjs --mode buggy --port 4173
DEMO_ADMIN_TOKEN=<token> node server/index.mjs --mode fixed --port 4174
```

### Test runner

```bash
cd test-runner
npm ci
npx playwright install chromium
BUGGY_URL=http://localhost:4173 FIXED_URL=http://localhost:4174 DEMO_ADMIN_TOKEN=<token> npm start   # listens on 127.0.0.1:4300
```

Without `TEST_RUNNER_URL` the backend still works, but no regression tests are generated.

### Frontend

```bash
cd frontend
npm ci
npm run dev        # http://localhost:3000, API from VITE_API_BASE_URL
```

## Tests

| Suite | Command | Needs |
|---|---|---|
| Backend unit + security | `cd backend && uv run pytest` | nothing external |
| Backend lint / types | `uv run ruff check . && uv run ruff format --check . && uv run mypy` | |
| Backend integration | `uv run pytest -m integration` | PostgreSQL + pgvector |
| Backend browser | `uv run pytest -m browser` | PostgreSQL, Chromium, built demo store, `test-runner` dependencies |
| Frontend | `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` | |
| Demo store | `cd demo-target && npm run typecheck && npm test` | |
| Defect oracles | `cd demo-target && npm run build && npm run verify-oracles -- --runs 2` | Chromium |
| Test runner | `cd test-runner && npm test` | built demo store, Chromium |

Integration and browser tests refuse to run unless the database name in `DATABASE_URL` contains `test`, because they drop and recreate tables:

```bash
DATABASE_URL=postgresql+psycopg://reprolab:reprolab@localhost:5432/reprolab_test \
  uv run pytest -m "integration or browser"
```

The tests use the deterministic `stub` model and the `hashing` embedder. They make no network calls to model providers.
