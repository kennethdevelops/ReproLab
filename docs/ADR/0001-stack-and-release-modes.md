# ADR-0001: Stack and local-first / public-demo split

- **Status:** Accepted
- **Date:** 2026-10-28

## Context

The original design brief fixed a default stack and two release modes for the MVP: a local self-hosted tool and a public portfolio demo restricted to an operator-controlled target.

## Decision

Adopt that default stack without substitution:

- React + TypeScript + Vite + Tailwind + TanStack Query for the UI.
- Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic for the API.
- PostgreSQL 16 with pgvector; PostgreSQL full-text search for lexical retrieval.
- Celery + Redis for background jobs; PostgreSQL stays the canonical record of runs.
- LangGraph for the investigation state machine.
- Python Playwright (official image, pinned) for investigations; a separate Node Playwright Test container for regression-test validation.
- Docker Compose for local infrastructure.

One setting, `APP_MODE`, selects behaviour:

- `local`: project creation and public GitHub import enabled; extra local origins allowed only when listed in `LOCAL_EXTRA_ALLOWED_ORIGINS`.
- `public_demo`: project creation, evaluation start and reset are disabled for anonymous callers; only the preconfigured demo project and origin are usable; rate and cost caps apply.

Policy is enforced in API and worker code and, for the public deployment, at the container network boundary.

## Consequences

- One backend package serves API and both worker types; process role is chosen by the container command.
- The public demo cannot become a general browsing or code-execution service, because the mode switch removes those code paths rather than hiding them in the UI.
