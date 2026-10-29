# ReproLab

AI-assisted web bug investigation: given a bug report and an authorised test target, ReproLab drives a constrained Playwright browser agent, retrieves relevant repository code with hybrid RAG, and produces an evidence-backed report with a proposed regression test.

> **Status: early development.** Milestones M0 (foundation) and M1 (demo target and oracles) are in progress. No AI investigation runs yet. See [`docs/PROGRESS.md`](docs/PROGRESS.md) for what is verified.

## Repository

| Path | Contents |
|---|---|
| `backend/` | FastAPI API, Celery workers, agent, retrieval (Python 3.12+, `uv`) |
| `frontend/` | React + Vite + Tailwind UI |
| `demo-target/` | Synthetic storefront with injected defects, fixed variants and oracle tests |
| `benchmarks/` | Public cases, private ground truth, runners, measured results |
| `docs/` | Plan, progress, architecture, security, ADRs |

## Quick start (Docker)

Prerequisites: Docker Desktop (Windows: with WSL2) or Docker Engine + Compose.

```bash
cp .env.example .env          # set POSTGRES_PASSWORD and DEMO_ADMIN_TOKEN
docker compose up --build -d  # runs migrations and seeds the demo project
```

- Web UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Demo store (buggy): http://localhost:4173, fixed variant: http://localhost:4174

Windows without `make`: `.\scripts\rl.ps1 <target>` mirrors the Makefile targets.

## Development without Docker

```bash
cd backend && uv sync && uv run pytest
cd frontend && npm ci && npm test && npm run dev
cd demo-target && npm ci && npm run build && npm run verify-oracles -- --runs 2
```

Integration tests need a disposable PostgreSQL with pgvector whose database name contains `test`:

```bash
DATABASE_URL=postgresql+psycopg://user@host:5432/reprolab_test uv run pytest -m integration
```

## Licence

MIT (pending owner confirmation) — see [`LICENSE`](LICENSE).
