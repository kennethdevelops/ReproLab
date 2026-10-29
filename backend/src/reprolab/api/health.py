from __future__ import annotations

import logging

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from reprolab.config.settings import get_settings
from reprolab.db.session import get_engine

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("readyz_db_failed", extra={"error_type": type(exc).__name__})
        checks["database"] = "unavailable"
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)
        client.ping()
        checks["broker"] = "ok"
    except Exception as exc:
        log.warning("readyz_broker_failed", extra={"error_type": type(exc).__name__})
        checks["broker"] = "unavailable"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
