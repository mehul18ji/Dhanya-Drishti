"""`GET /api/v1/model-info` contract (Phase 4 M2).

The endpoint must describe the bundle that is actually loaded, and must stay honest
when the bundle cannot be loaded: no fake model version, no invented metrics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.main as main_module  # noqa: E402
from app.services import inference_service  # noqa: E402
from app.services.inference_service import BundleIntegrityError  # noqa: E402
from app.vision.feature_extraction import FEATURE_NAMES  # noqa: E402

BUNDLE_DIR = REPO_ROOT / "backend" / "app" / "artifacts" / "production"
CLASS_LABELS = ["bacterial_leaf_blight", "brown_spot", "leaf_smut"]


def test_model_info_describes_the_loaded_bundle(client: TestClient) -> None:
    response = client.get("/api/v1/model-info")
    assert response.status_code == 200
    body = response.json()

    manifest = json.loads((BUNDLE_DIR / "model_manifest.json").read_text(encoding="utf-8"))

    assert body["model_name"] == "svm"
    assert body["model_version"] == "svm-v1.0.0"
    assert body["bundle_version"] == manifest["bundle_version"]
    assert body["feature_set_version"] == "1.0.0"
    assert body["feature_count"] == len(FEATURE_NAMES) == 50
    assert body["classes"] == CLASS_LABELS

    assert body["segmentation_config_version"] == "seg-v2"
    assert body["quality_config_version"] == "quality-v1"
    assert body["split_protocol"] == "v1"
    assert body["dataset_version"] == "ds-cc74ed659044"
    assert body["training_rows"] == 96

    # Metrics are restated from the manifest, not recomputed.
    assert body["cv_macro_f1_mean"] == pytest.approx(0.8411814, rel=1e-6)
    assert body["cv_macro_f1_std"] == pytest.approx(0.0603702, rel=1e-6)
    assert body["held_out_rows"] == 24
    assert body["held_out_macro_f1"] == pytest.approx(0.7854636, rel=1e-6)
    assert body["held_out_status"] == "evaluated_once_after_selection_not_recomputed"

    # Score honesty: margins, never probabilities.
    assert body["calibrated_probabilities"] is False
    assert body["score_kind"] == "decision_margin"
    assert "not probabilities" in body["score_note"]
    assert "confidence" not in body
    assert "probability" not in body

    assert "experimental estimate" in body["severity_disclaimer"]
    assert body["known_failure_cases"], "limitations must be exposed to the UI"


def test_model_info_matches_the_manifest_held_out_block(client: TestClient) -> None:
    body = client.get("/api/v1/model-info").json()
    manifest = json.loads((BUNDLE_DIR / "model_manifest.json").read_text(encoding="utf-8"))
    held_out = manifest["evaluation"]["held_out"]

    assert body["held_out_macro_f1"] == pytest.approx(held_out["metrics"]["macro_f1"])
    assert body["held_out_accuracy"] == pytest.approx(held_out["metrics"]["accuracy"])


def test_api_stays_honest_when_the_bundle_cannot_be_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _broken() -> None:
        raise BundleIntegrityError("simulated corrupted artifact")

    monkeypatch.setattr(inference_service, "get_inference_service", _broken)

    with TestClient(main_module.create_app()) as client:
        health = client.get("/api/v1/health").json()
        assert health["model_loaded"] is False
        assert health["model_version"] is None

        response = client.get("/api/v1/model-info")
        assert response.status_code == 503
        payload = response.json()
        assert payload["reason_code"] == "MODEL_NOT_LOADED"
        assert payload["status"] == "error"
