"""Temporary history + artifact route tests (Phase 4 M9).

Uses the app's own lifespan (which wipes the runtime directory), synthetic images
and the real bundle for inference only.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.db.history_repository import iso, utc_now
from tests.vision_helpers import encode_png, leaf_with_spots


def _predict(client: TestClient) -> dict:
    image, _, _ = leaf_with_spots(480, 240)
    response = client.post(
        "/api/v1/predict",
        files={"file": ("leaf.png", encode_png(image), "image/png")},
    )
    assert response.status_code == 200
    return response.json()


def test_history_is_empty_before_any_prediction(client: TestClient) -> None:
    body = client.get("/api/v1/history").json()

    assert body["count"] == 0
    assert body["items"] == []
    assert body["runtime_storage"] == "temporary"


def test_history_row_exposes_metadata_and_artifact_links(client: TestClient) -> None:
    predicted = _predict(client)

    item = client.get("/api/v1/history").json()["items"][0]

    assert item["prediction_id"] == predicted["prediction_id"]
    assert item["status"] == predicted["status"]
    assert item["disease"] == predicted["disease"]
    assert item["model_version"] == "svm-v1.0.0"
    assert item["severity_config_version"] == "severity-v1"
    assert item["created_at"] and item["expires_at"]
    assert item["artifacts"]["original_url"] == predicted["artifacts"]["original_url"]
    assert "confidence" not in item

    single = client.get(f"/api/v1/history/{predicted['prediction_id']}")
    assert single.status_code == 200
    assert single.json()["prediction_id"] == predicted["prediction_id"]


def test_history_respects_the_limit_parameter(client: TestClient) -> None:
    first = _predict(client)
    second = _predict(client)

    listed = client.get("/api/v1/history", params={"limit": 1}).json()

    assert listed["count"] == 1
    assert listed["items"][0]["prediction_id"] == second["prediction_id"]
    assert first["prediction_id"] != second["prediction_id"]


def test_unknown_prediction_ids_are_404_and_invalid_ones_422(client: TestClient) -> None:
    missing = client.get(f"/api/v1/history/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["reason_code"] == "PREDICTION_NOT_FOUND"

    invalid = client.get("/api/v1/history/not-a-uuid")
    assert invalid.status_code == 422

    unknown_artifact = client.get(f"/api/v1/history/{uuid.uuid4()}/original")
    assert unknown_artifact.status_code == 404
    assert unknown_artifact.json()["reason_code"] == "ARTIFACT_NOT_FOUND"


def test_delete_removes_rows_and_files(client: TestClient) -> None:
    predicted = _predict(client)
    assert client.get(predicted["artifacts"]["original_url"]).status_code == 200

    deleted = client.delete("/api/v1/history")

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1
    assert client.get("/api/v1/history").json()["count"] == 0

    # Both the row and the artifact file are gone.
    assert client.get(f"/api/v1/history/{predicted['prediction_id']}").status_code == 404
    assert client.get(predicted["artifacts"]["original_url"]).status_code == 404
    assert client.get(predicted["artifacts"]["leaf_mask_url"]).status_code == 404


def test_expired_rows_and_artifacts_disappear(client: TestClient) -> None:
    predicted = _predict(client)
    history = client.app.state.history
    record = history.repository.get(predicted["prediction_id"])
    assert record is not None

    expired = dataclasses.replace(
        record, expires_at=iso(utc_now() - timedelta(minutes=1))
    )
    history.repository.upsert(expired)

    listed = client.get("/api/v1/history").json()
    assert listed["count"] == 0
    assert client.get(predicted["artifacts"]["original_url"]).status_code == 404


def test_history_status_matches_the_prediction_status(client: TestClient) -> None:
    predicted = _predict(client)

    assert predicted["status"] in {"predicted", "uncertain"}
    assert client.get("/api/v1/history").json()["items"][0]["status"] == predicted["status"]
