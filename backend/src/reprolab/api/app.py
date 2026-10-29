from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from reprolab.api import health
from reprolab.api.errors import install_error_handlers
from reprolab.api.v1 import router as v1_router
from reprolab.config.settings import get_settings
from reprolab.observability.logging import configure_logging, request_id_var


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(title="ReproLab API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = (
            incoming if 0 < len(incoming) <= 64 and incoming.isalnum() else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router.router, prefix="/api/v1")
    return app
