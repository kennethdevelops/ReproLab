"""Integration fixtures. DATABASE_URL must point at a disposable test database; tables are
dropped and recreated through Alembic for the session."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from reprolab.config.settings import get_settings
from reprolab.db.session import get_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


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
