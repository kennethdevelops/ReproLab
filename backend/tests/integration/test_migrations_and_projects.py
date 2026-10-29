from __future__ import annotations

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from reprolab.api.app import create_app
from reprolab.db.seed import DEMO_PROJECT_ID, seed
from reprolab.db.session import get_engine

from .conftest import alembic_config

pytestmark = pytest.mark.integration


def test_migrations_create_tables_and_vector_extension(migrated_db: None) -> None:
    tables = set(inspect(get_engine()).get_table_names())
    assert {"projects", "investigations", "agent_steps", "evidence_assets"} <= tables
    with get_engine().connect() as conn:
        ext = conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
        assert ext.scalar() == "vector"


def test_downgrade_then_upgrade_round_trips(migrated_db: None) -> None:
    command.downgrade(alembic_config(), "base")
    assert "projects" not in inspect(get_engine()).get_table_names()
    command.upgrade(alembic_config(), "head")
    assert "projects" in inspect(get_engine()).get_table_names()


def test_seed_is_idempotent_and_project_is_listed(clean_db: None) -> None:
    seed()
    seed()
    client = TestClient(create_app())
    projects = client.get("/api/v1/projects").json()
    assert [p["id"] for p in projects] == [str(DEMO_PROJECT_ID)]
    assert projects[0]["current_snapshot"] is None

    detail = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}")
    assert detail.status_code == 200


def test_unknown_project_is_404_envelope(clean_db: None) -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/projects/00000000-0000-0000-0000-00000000dead")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
