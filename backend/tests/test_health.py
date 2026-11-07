"""Phase 0 contract: the health endpoint exists and reports honestly."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["runtime_storage"] == "temporary"


def test_health_reports_no_model_before_phase_4(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()

    assert body["model_loaded"] is False
    assert body["model_version"] is None


def test_root_advertises_docs_and_health(client: TestClient) -> None:
    body = client.get("/").json()

    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health"
