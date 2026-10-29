"""Full API flow: POST investigation -> job (inline, stub model, real browser) -> status, SSE,
artifacts, report. Needs PostgreSQL (integration) and the demo store (browser)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reprolab.agent.model_client import ModelUnavailable, StubModelClient
from reprolab.api.app import create_app
from reprolab.api.v1 import investigations as inv_api
from reprolab.config.settings import Settings, get_settings
from reprolab.db.models import Project
from reprolab.db.session import session_scope
from reprolab.workers.investigation_job import execute_investigation
from tests.browser.test_agent_d01 import d01_script

pytestmark = [pytest.mark.integration, pytest.mark.browser]


@pytest.fixture
def project_id(clean_db: None, buggy_origin: str) -> uuid.UUID:
    pid = uuid.uuid4()
    with session_scope() as db:
        db.add(Project(id=pid, name="Demo Store", test_origin=buggy_origin, mode="demo"))
    return pid


@pytest.fixture
def artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(get_settings(), "artifacts_dir", tmp_path)
    yield tmp_path


def _inline(factory):  # type: ignore[no-untyped-def]
    return lambda investigation_id: execute_investigation(investigation_id, model_factory=factory)


def test_d01_through_api(
    project_id: uuid.UUID, artifacts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inv_api, "enqueue_investigation", [_inline(lambda s: StubModelClient(d01_script()))]
    )
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/investigations",
        json={
            "project_id": str(project_id),
            "bug_report": "Coupon disappears after checkout refresh.",
            "start_path": "/shop",
        },  # fmt: skip
    )
    assert response.status_code == 202, response.text
    inv_id = response.json()["investigation_id"]

    detail = client.get(f"/api/v1/investigations/{inv_id}").json()
    assert detail["status"] == "reproduced", detail["status_reason"]
    assert detail["result"]["verification"]["level"] == "browser_observation"
    assert any(f["verification_status"] == "verified_observation" for f in detail["findings"])
    tools = [s["tool"] for s in detail["steps"] if s["node"] == "act"]
    assert tools[:3] == ["open_page", "click", "open_page"]

    types = sorted(e["type"] for e in detail["evidence"])
    assert types == ["screenshot", "screenshot", "screenshot", "trace"]
    trace = next(e for e in detail["evidence"] if e["type"] == "trace")
    dl = client.get(f"/api/v1/artifacts/{trace['id']}/download")
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    assert dl.content[:2] == b"PK"

    with client.stream("GET", f"/api/v1/investigations/{inv_id}/events") as stream:
        body = "".join(stream.iter_text())
    assert "event: investigation.queued" in body
    assert "event: browser.action_completed" in body
    assert "event: investigation.completed" in body
    assert body.rstrip().endswith("data: {}")  # stream.end

    # Reconnect after a known event replays only later events.
    with client.stream(
        "GET", f"/api/v1/investigations/{inv_id}/events", headers={"Last-Event-ID": "3"}
    ) as s:
        replay = "".join(s.iter_text())
    assert "id: 3\n" not in replay and "id: 4\n" in replay

    md = client.get(f"/api/v1/investigations/{inv_id}/report.md")
    assert md.status_code == 200 and "**Status:** REPRODUCED" in md.text

    # A second job delivery for the same run must not re-execute it.
    assert execute_investigation(uuid.UUID(inv_id)) == "reproduced"


def test_missing_provider_key_blocks_honestly(
    project_id: uuid.UUID, artifacts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_key(settings: Settings) -> StubModelClient:
        raise ModelUnavailable("PROVIDER_NOT_CONFIGURED", "ANTHROPIC_API_KEY is not set.")

    monkeypatch.setattr(inv_api, "enqueue_investigation", [_inline(no_key)])
    client = TestClient(create_app())
    inv_id = client.post(
        "/api/v1/investigations",
        json={"project_id": str(project_id), "bug_report": "Something is broken here."},
    ).json()["investigation_id"]
    detail = client.get(f"/api/v1/investigations/{inv_id}").json()
    assert detail["status"] == "blocked"
    assert "PROVIDER_NOT_CONFIGURED" in detail["status_reason"]
    assert detail["evidence"] == []


def test_cancel_before_start(
    project_id: uuid.UUID, artifacts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queued: list[uuid.UUID] = []
    monkeypatch.setattr(inv_api, "enqueue_investigation", [queued.append])
    client = TestClient(create_app())
    inv_id = client.post(
        "/api/v1/investigations",
        json={"project_id": str(project_id), "bug_report": "Something is broken here."},
    ).json()["investigation_id"]
    assert client.post(f"/api/v1/investigations/{inv_id}/cancel").json()["cancel_requested"] is True
    status = execute_investigation(queued[0], model_factory=lambda s: StubModelClient(d01_script()))
    assert status == "cancelled"
    # Idempotent once terminal.
    assert client.post(f"/api/v1/investigations/{inv_id}/cancel").status_code == 200


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"start_path": "https://evil.test/"}, "VALIDATION_ERROR"),
        ({"start_path": "//evil.test"}, "VALIDATION_ERROR"),
        ({"test_origin": "http://evil.test"}, "VALIDATION_ERROR"),
        ({"max_browser_steps": 10_000}, "VALIDATION_ERROR"),
        ({"rag_mode": "hybrid"}, "RAG_UNAVAILABLE"),
        ({"bug_report": "x" * 5000}, "BUG_REPORT_TOO_LONG"),
    ],
)
def test_start_rejects_policy_overrides(
    project_id: uuid.UUID, payload: dict[str, object], code: str
) -> None:
    client = TestClient(create_app())
    body = {"project_id": str(project_id), "bug_report": "Something is broken here.", **payload}
    response = client.post("/api/v1/investigations", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
