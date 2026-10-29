"""Celery application. Queues: ``indexing`` and ``investigations``, served by separate workers."""

from __future__ import annotations

from celery import Celery

from reprolab.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "reprolab",
    broker=settings.redis_url,
    include=["reprolab.workers.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="investigations",
    task_routes={
        "reprolab.workers.tasks.run_investigation": {"queue": "investigations"},
        "reprolab.workers.tasks.index_snapshot": {"queue": "indexing"},
    },
    broker_connection_retry_on_startup=True,
)
