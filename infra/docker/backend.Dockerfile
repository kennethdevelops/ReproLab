# syntax=docker/dockerfile:1.7
# Backend image with two targets:
#   app     - API and indexing worker (no browser)
#   browser - investigation worker; official Playwright Python image, version matches pyproject pin
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.64.1-noble

FROM ghcr.io/astral-sh/uv:0.10.12 AS uv

FROM ${PYTHON_IMAGE} AS app
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
# Public problem statements only; benchmarks/ground-truth is never copied into any image.
COPY benchmarks/cases /app/benchmarks/cases
ENV DEMO_CASES_PATH=/app/benchmarks/cases/cases.v1.json
RUN uv sync --frozen --no-dev \
 && useradd --uid 10001 --create-home reprolab \
 && mkdir -p /data/artifacts && chown -R reprolab /data
USER reprolab
EXPOSE 8000
CMD ["uvicorn", "reprolab.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM ${PLAYWRIGHT_IMAGE} AS browser
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev \
 && mkdir -p /data/artifacts && chown -R pwuser /data
# Non-root user shipped with the Playwright image; Chromium sandbox stays enabled.
USER pwuser
CMD ["celery", "-A", "reprolab.workers.celery_app", "worker", "-Q", "investigations", "--concurrency", "1", "--loglevel", "INFO"]
