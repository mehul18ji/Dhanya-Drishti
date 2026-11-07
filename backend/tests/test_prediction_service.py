"""Prediction-composition tests (Phase 4 M6).

Synthetic images only: no dataset, no training and no held-out rows. The model is
either the real committed bundle (inference only) or a monkeypatched boundary, so
the composition rules can be tested without touching the artifacts.
"""

from __future__ import annotations

import dataclasses
import uuid

import numpy as np
import pytest

from app.core.exceptions import ModelNotLoadedError, UploadValidationError
from app.services import prediction_service, preprocessing_service
from app.services.inference_service import BundleIntegrityError, get_inference_service
from app.services.prediction_service import PredictionResult, predict_upload
from app.services.upload_validation import UploadValidationResult, validate_upload
from app.vision.severity import severity_for
from tests.vision_helpers import encode_png, leaf_with_spots


def _upload(image: np.ndarray, filename: str = "leaf.png") -> UploadValidationResult:
    return validate_upload(filename, encode_png(image))


def _leaf_upload() -> UploadValidationResult:
    image, _, _ = leaf_with_spots(480, 240)
    return _upload(image)


def _blank_upload() -> UploadValidationResult:
    return _upload(np.full((400, 400, 3), 250, dtype=np.uint8))


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def test_leaf_upload_is_composed_with_scores_severity_and_provenance() -> None:
    result = predict_upload(_leaf_upload())

    assert isinstance(result, PredictionResult)
    assert result.status in {"predicted", "uncertain"}
    assert result.has_label is True
    assert result.disease in get_inference_service().classes

    # Three decision-margin scores, ranked, margin = best - second.
    assert set(result.decision_scores) == set(get_inference_service().classes)
    assert len(result.ranking) == 3
    ordered = sorted(result.decision_scores.items(), key=lambda item: item[1], reverse=True)
    assert result.ranking == tuple(name for name, _ in ordered)
    assert result.margin == pytest.approx(ordered[0][1] - ordered[1][1])
    assert result.score_kind == "decision_margin"

    # Severity is either a real bucket from a reliable lesion or explicitly absent.
    if result.lesion_reliable:
        assert result.severity.severity in {"Mild", "Moderate", "Severe"}
        assert result.severity.lesion_area_percentage == pytest.approx(
            result.lesion_area_percentage
        )
    else:
        assert result.severity.severity is None
        assert result.status == "uncertain"

    assert result.severity.disclaimer.startswith("Severity is an experimental estimate")
    assert result.severity.config_version == "severity-v1"
    assert len(result.severity.config_sha256) == 64

    assert result.model_name == "svm"
    assert result.model_version == "svm-v1.0.0"
    assert result.feature_set_version == "1.0.0"
    assert result.segmentation_config_version == "seg-v2"
    assert result.quality_config_version == "quality-v1"
    assert result.stage_ms["total"] >= 0.0
    assert result.outcome.artifacts.available is True
    uuid.UUID(result.prediction_id)  # a real UUID, not an improvised string


def test_scores_are_deterministic_for_the_same_upload() -> None:
    upload = _leaf_upload()

    first = predict_upload(upload)
    second = predict_upload(upload)

    assert first.status == second.status
    assert first.disease == second.disease
    assert first.decision_scores == pytest.approx(second.decision_scores)
    assert first.severity.severity == second.severity.severity


def test_rejected_image_has_no_label_scores_or_severity() -> None:
    result = predict_upload(_blank_upload())

    assert result.status == "rejected"
    assert result.is_rejected is True
    assert result.has_label is False
    assert result.disease is None
    assert result.decision_scores == {}
    assert result.margin is None
    assert result.ranking == ()
    assert result.lesion_area_percentage is None
    assert result.lesion_reliable is False
    assert result.severity.severity is None
    assert result.severity.lesion_area_percentage is None
    assert "NO_CLEAR_LEAF_FOUND" in result.rejections
    # Even a refusal carries the PRD disclaimer, so the UI can never show a bare
    # severity value without it.
    assert result.severity.disclaimer.startswith("Severity is an experimental estimate")


def test_result_never_exposes_a_confidence_or_probability_field() -> None:
    payload = predict_upload(_leaf_upload()).as_dict()

    keys = set(payload)
    assert "confidence" not in keys
    assert "probability" not in keys
    assert "probabilities" not in keys
    assert not any("confidence" in key for key in keys)
    # `lesion_area_percentage` is a measured lesion area, not a score claim.
    assert "lesion_area_percentage" in keys
    assert payload["score_kind"] == "decision_margin"
    assert "not probabilities" in str(payload["score_note"])


def test_prediction_id_is_generated_or_preserved() -> None:
    first = predict_upload(_leaf_upload())
    second = predict_upload(_leaf_upload())
    fixed = predict_upload(_leaf_upload(), prediction_id="test-prediction-id")

    assert first.prediction_id != second.prediction_id
    assert fixed.prediction_id == "test-prediction-id"


# --------------------------------------------------------------------------- #
# Separation of the three statuses
# --------------------------------------------------------------------------- #


def test_uncertain_outcome_still_names_a_disease_but_stays_uncertain() -> None:
    # A pure close-up triggers the documented full-frame fallback warning.
    image = np.full((400, 400, 3), (60, 140, 70), dtype=np.uint8)
    rng = np.random.default_rng(3)
    image = np.clip(
        image.astype(np.int16) + rng.integers(-10, 11, image.shape), 0, 255
    ).astype(np.uint8)

    result = predict_upload(_upload(image))

    assert result.status == "uncertain"
    assert "FULL_FRAME_FALLBACK" in result.warnings
    assert result.has_label is True


def test_severity_refusal_downgrades_predicted_to_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable = severity_for(None, lesion_reliable=False)
    monkeypatch.setattr(prediction_service, "severity_for", lambda *a, **k: unavailable)

    result = predict_upload(_leaf_upload())

    assert result.status == "uncertain"
    assert result.has_label is True
    assert result.severity.severity is None
    assert result.severity.reason_code == "LESION_ESTIMATE_UNRELIABLE"


def test_unreliable_lesion_never_produces_mild(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.vision.feature_extraction import (
        LESION_DEPENDENT_FEATURES,
        extract_features_from_pipeline,
    )
    from app.vision.pipeline import run_segmentation

    upload = _leaf_upload()
    baseline = extract_features_from_pipeline(run_segmentation(upload.content))
    values = np.array(baseline.values, copy=True)
    values[-len(LESION_DEPENDENT_FEATURES) :] = np.nan
    degraded = dataclasses.replace(
        baseline,
        values=values,
        status="uncertain",
        lesion_reliable=False,
        lesion_reference_available=False,
        lesion_area_percentage=None,
        missing_features=LESION_DEPENDENT_FEATURES,
        warnings=("LESION_REFERENCE_UNAVAILABLE",),
    )
    monkeypatch.setattr(
        preprocessing_service, "extract_features_from_pipeline", lambda _: degraded
    )

    result = predict_upload(upload)

    assert result.status == "uncertain"
    assert result.lesion_area_percentage is None
    assert result.severity.severity is None
    assert result.severity.severity != "Mild"
    assert result.severity.reason_code == "LESION_ESTIMATE_UNRELIABLE"


# --------------------------------------------------------------------------- #
# Failure paths
# --------------------------------------------------------------------------- #


def test_missing_model_fails_before_any_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unavailable() -> None:
        raise BundleIntegrityError("model_pipeline.joblib is corrupted")

    def _must_not_run(*_args, **_kwargs):
        pytest.fail("the vision pipeline must not run without a verified model")

    monkeypatch.setattr(preprocessing_service, "get_inference_service", _unavailable)
    monkeypatch.setattr(preprocessing_service, "run_segmentation", _must_not_run)

    with pytest.raises(ModelNotLoadedError):
        predict_upload(_leaf_upload())


def test_undecodable_upload_stays_a_typed_422() -> None:
    content = b"definitely not an image"
    broken = UploadValidationResult(
        filename="broken.png",
        extension=".png",
        detected_format="PNG",
        size_bytes=len(content),
        width=120,
        height=120,
        mode="RGB",
        exif_orientation=None,
        content=content,
    )

    with pytest.raises(UploadValidationError):
        predict_upload(broken)


def test_service_writes_no_files(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    predict_upload(_leaf_upload())

    assert list(tmp_path.iterdir()) == []
