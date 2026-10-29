"""Shared fixtures.

Database fixtures: DATABASE_URL must point at a disposable test database (its name must contain
"test"); the schema is dropped and recreated through Alembic for the session.

Demo-store fixtures: start the buggy and fixed builds as real local servers. They require
`npm run build` in demo-target/ and Playwright Chromium for Python.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from reprolab.config.settings import get_settings
from reprolab.db.session import get_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEMO_DIR = BACKEND_DIR.parent / "demo-target"


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[None]:
    url = get_settings().database_url
    if "test" not in url.rsplit("/", 1)[-1]:
        pytest.exit(f"refusing to run integration tests against non-test database: {url}")
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture
def clean_db(migrated_db: None) -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE projects CASCADE"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start_demo(mode: str) -> Iterator[str]:
    if not (DEMO_DIR / "dist" / mode / "index.html").exists():
        pytest.skip(f"demo-target not built ({mode}); run npm run build in demo-target/")
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, test-only
        ["node", "server/index.mjs", "--mode", mode, "--port", str(port)],  # noqa: S607
        cwd=DEMO_DIR,
        env={**os.environ, "DEMO_ADMIN_TOKEN": "test-admin"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    origin = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{origin}/api/health", timeout=1):  # noqa: S310
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("demo server did not start")
    try:
        yield origin
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def buggy_origin() -> Iterator[str]:
    yield from _start_demo("buggy")


@pytest.fixture(scope="session")
def fixed_origin() -> Iterator[str]:
    yield from _start_demo("fixed")
