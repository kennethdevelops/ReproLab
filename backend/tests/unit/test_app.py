from __future__ import annotations

from fastapi.testclient import TestClient

from reprolab.api.app import create_app
from reprolab.config.settings import Settings
from reprolab.db.enums import InvestigationStatus


def test_healthz_returns_ok_and_request_id() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) == 32


def test_unknown_route_uses_error_envelope() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]


def test_untrusted_request_id_is_replaced() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz", headers={"X-Request-ID": "<script>bad</script>"})
    assert response.headers["x-request-id"] != "<script>bad</script>"


def test_public_settings_never_include_secrets() -> None:
    settings = Settings(anthropic_api_key="sk-ant-secret-value", demo_admin_token="admin-secret")  # type: ignore[arg-type]
    view = settings.public_view()
    rendered = repr(view)
    assert "sk-ant-secret-value" not in rendered
    assert "admin-secret" not in rendered
    assert view["llm_configured"] is True


def test_csv_settings_are_split() -> None:
    settings = Settings(cors_allowed_origins="http://a.test, http://b.test")  # type: ignore[arg-type]
    assert settings.cors_allowed_origins == ["http://a.test", "http://b.test"]


def test_terminal_statuses() -> None:
    assert InvestigationStatus.REPRODUCED.is_terminal
    assert not InvestigationStatus.BROWSING.is_terminal
