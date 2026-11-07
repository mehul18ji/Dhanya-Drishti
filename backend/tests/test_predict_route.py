"""`POST /api/v1/predict` contract tests (Phase 4 M8).

Synthetic images only; the real committed bundle is used for inference (no
training, no tuning, no held-out data).
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import inference_service, upload_validation
from tests.vision_helpers import encode_png, leaf_with_spots


def _files(image: np.ndarray, name: str = "leaf.png"):
    return {"file": (name, encode_png(image), "image/png")}


def _leaf_image() -> np.ndarray:
    image, _, _ = leaf_with_spots(480, 240)
    return image


def _blank_image() -> np.ndarray:
    return np.full((400, 400, 3), 250, dtype=np.uint8)


def test_predict_returns_a_labelled_result_without_confidence(client: TestClient) -> None:
    response = client.post("/api/v1/predict", files=_files(_leaf_image()))

    assert response.status_code == 200
    body = response.json()

    assert body["status"] in {"predicted", "uncertain"}
    assert body["disease"] in {"bacterial_leaf_blight", "brown_spot", "leaf_smut"}
    assert set(body["decision_scores"]) == {
        "bacterial_leaf_blight",
        "brown_spot",
        "leaf_smut",
    }
    assert body["ranking"][0] == max(body["decision_scores"], key=body["decision_scores"].get)
    assert body["score_kind"] == "decision_margin"
    assert "not probabilities" in body["score_note"]

    assert "confidence" not in body
    assert "probability" not in body
    assert not any("confidence" in key for key in body)

    assert body["severity_disclaimer"].startswith("Severity is an experimental estimate")
    assert body["severity_config_version"] == "severity-v1"
    if body["status"] == "predicted":
        assert body["severity"] in {"Mild", "Moderate", "Severe"}

    assert body["artifacts"]["original_url"].endswith("/original")
    assert body["model_version"] == "svm-v1.0.0"
    assert body["feature_set_version"] == "1.0.0"
    assert body["runtime_storage"] == "temporary"
    uuid.UUID(body["prediction_id"])
    assert body["created_at"]


def test_predict_result_is_stored_and_artifacts_are_served(client: TestClient) -> None:
    body = client.post("/api/v1/predict", files=_files(_leaf_image())).json()

    listed = client.get("/api/v1/history").json()
    assert listed["count"] == 1
    assert listed["items"][0]["prediction_id"] == body["prediction_id"]

    original = client.get(body["artifacts"]["original_url"])
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/png"
    assert len(original.content) > 0

    leaf_mask = client.get(body["artifacts"]["leaf_mask_url"])
    assert leaf_mask.status_code == 200


def test_rejected_image_returns_no_id_and_is_not_stored(client: TestClient) -> None:
    response = client.post("/api/v1/predict", files=_files(_blank_image(), "blank.png"))

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "rejected"
    assert body["reason_code"] == "NO_CLEAR_LEAF_FOUND"
    assert "message" in body and body["message"]
    assert "prediction_id" not in body
    assert "artifacts" not in body
    assert "severity" not in body

    assert client.get("/api/v1/history").json()["count"] == 0


def test_text_screenshot_is_rejected_with_no_clear_leaf(client: TestClient) -> None:
    """A readable image with no leaf must reach the pipeline and be rejected."""
    screenshot = np.full((420, 420, 3), 255, dtype=np.uint8)
    for row in range(40, 380, 24):
        screenshot[row : row + 8, 40:380] = 20

    response = client.post("/api/v1/predict", files=_files(screenshot, "text.png"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "NO_CLEAR_LEAF_FOUND"
    assert client.get("/api/v1/history").json()["count"] == 0


def test_upload_level_failures_use_typed_http_errors(client: TestClient) -> None:
    unsupported = client.post(
        "/api/v1/predict", files={"file": ("leaf.gif", b"GIF89a", "image/gif")}
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["reason_code"] == "UNSUPPORTED_FILE_TYPE"

    corrupt = client.post(
        "/api/v1/predict", files={"file": ("leaf.png", b"not an image", "image/png")}
    )
    assert corrupt.status_code == 422
    assert corrupt.json()["reason_code"] == "INVALID_UPLOAD"


def test_oversize_upload_is_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upload_validation, "_limit_bytes", lambda _settings: 8)

    response = client.post("/api/v1/predict", files=_files(_leaf_image()))

    assert response.status_code == 413
    assert response.json()["reason_code"] == "FILE_TOO_LARGE"


def test_missing_model_returns_503_before_any_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unavailable():
        raise inference_service.BundleIntegrityError("bundle is corrupted")

    monkeypatch.setattr(inference_service, "get_inference_service", _unavailable)

    with TestClient(create_app()) as degraded:
        health = degraded.get("/api/v1/health").json()
        response = degraded.post("/api/v1/predict", files=_files(_leaf_image()))

    assert health["model_loaded"] is False
    assert response.status_code == 503
    assert response.json()["reason_code"] == "MODEL_NOT_LOADED"
    assert response.json()["status"] == "error"
