# reprolab backend

FastAPI API, Celery workers (indexing, investigation), LangGraph agent and hybrid retrieval.

```bash
uv sync
uv run pytest                    # offline unit tests
uv run pytest -m integration     # needs DATABASE_URL pointing at a disposable test DB
uv run ruff check . && uv run mypy
uv run alembic upgrade head
uv run uvicorn reprolab.api.app:create_app --factory --reload
```
