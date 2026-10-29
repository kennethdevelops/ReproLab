"""Celery task entry points. Business logic lives in the agent/indexing packages."""

from __future__ import annotations

import uuid

from reprolab.config.settings import get_settings
from reprolab.workers.celery_app import celery_app


@celery_app.task(name="reprolab.workers.tasks.ping")
def ping() -> str:
    return "pong"


# Hard ceiling above the in-code wall-clock limit, in case a browser or provider call hangs.
_settings = get_settings()


@celery_app.task(
    name="reprolab.workers.tasks.run_investigation",
    acks_late=True,
    time_limit=_settings.max_investigation_seconds + 180,
)
def run_investigation(investigation_id: str) -> str:
    from reprolab.workers.investigation_job import execute_investigation

    return execute_investigation(uuid.UUID(investigation_id))
