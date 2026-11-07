"""rag_mode through the API: index required, retrieval events tied to the run, browser still decides."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from reprolab.agent.model_client import StubModelClient
from reprolab.api.app import create_app
from reprolab.api.v1 import investigations as inv_api
from reprolab.api.v1 import projects as projects_api
from reprolab.config.settings import get_settings
from reprolab.db.models import Project, RetrievalEvent
from reprolab.db.session import session_scope
from reprolab.indexing.local_snapshot import export_snapshot
from reprolab.indexing.pipeline import index_snapshot
from reprolab.workers.investigation_job import execute_investigation
from tests.browser.test_agent_d01 import d01_script

pytestmark = [pytest.mark.integration, pytest.mark.browser]

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def env(
    clean_db: None, buggy_origin: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, uuid.UUID]]:
    settings = get_settings()
    monkeypatch.setattr(settings, "snapshots_dir", tmp_path / "snap")
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path / "art")
    monkeypatch.setattr(settings, "embedding_provider", "hashing")
    monkeypatch.setattr(projects_api, "enqueue_index", [index_snapshot])
    pid = uuid.uuid4()
    with session_scope() as db:
        db.add(Project(id=pid, name="Demo", test_origin=buggy_origin, mode="demo",
                       repo_url="local://demo-target"))  # fmt: skip
    yield TestClient(create_app()), pid


def _rag_script() -> list[Any]:
    script = d01_script()
    return [script[0], [("search_code", {"query": "coupon sessionStorage", "kind": None})],
            *script[1:]]  # fmt: skip


def _start(client: TestClient, pid: uuid.UUID, rag_mode: str) -> Any:
    return client.post("/api/v1/investigations", json={
        "project_id": str(pid), "bug_report": "Coupon disappears after checkout refresh.",
        "start_path": "/shop", "rag_mode": rag_mode})  # fmt: skip


def test_rag_requires_index_then_runs_with_retrieval(
    env: tuple[TestClient, uuid.UUID], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, pid = env
    monkeypatch.setattr(inv_api, "enqueue_investigation", [
        lambda i: execute_investigation(i, model_factory=lambda s: StubModelClient(_rag_script()))
    ])  # fmt: skip

    r = _start(client, pid, "hybrid")
    assert r.status_code == 422 and r.json()["error"]["code"] == "RAG_INDEX_MISSING"

    export_snapshot(REPO, "demo-target", "demo-target", tmp_path / "snap")
    assert client.post(f"/api/v1/projects/{pid}/index").status_code == 202

    r = _start(client, pid, "hybrid")
    assert r.status_code == 202, r.text
    inv_id = r.json()["investigation_id"]
    detail = client.get(f"/api/v1/investigations/{inv_id}").json()
    assert detail["status"] == "reproduced", detail["status_reason"]
    retrieve = [s for s in detail["steps"] if s["node"] == "retrieve"]
    assert len(retrieve) == 1 and retrieve[0]["ok"]
    with session_scope() as db:
        events = db.scalars(
            select(RetrievalEvent).where(RetrievalEvent.investigation_id == uuid.UUID(inv_id))
        ).all()
    assert len(events) == 1 and events[0].mode == "hybrid" and events[0].chunk_ids
