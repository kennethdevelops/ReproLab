"""Celery task entry points. Business logic lives in the agent/indexing packages."""

from __future__ import annotations

from reprolab.workers.celery_app import celery_app


@celery_app.task(name="reprolab.workers.tasks.ping")
def ping() -> str:
    return "pong"
