"""Health and root contract: the API reports the model it actually loaded."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["runtime_storage"] == "temporary"


def test_health_reports_the_loaded_model(client: TestClient) -> None:
    """Phase 4 M2: the bundle is loaded at startup, so health must say so."""
    body = client.get("/api/v1/health").json()

    assert body["model_loaded"] is True
    assert body["model_version"] == "svm-v1.0.0"


def test_root_advertises_docs_health_and_model_info(client: TestClient) -> None:
    body = client.get("/").json()

    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health"
    assert body["model_info"] == "/api/v1/model-info"
