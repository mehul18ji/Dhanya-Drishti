"""Preprocessing orchestration tests (Phase 4 M4).

Synthetic images only: no raw dataset, no model fitting and no held-out rows are
touched. The tests pin the three public statuses, the never-healthy rule, the
``NaN``-not-``0 %`` lesion rule, the model/provenance guards and the artifacts the
response will serve.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import numpy as np
import pytest

from app.core.exceptions import ModelNotLoadedError, UploadValidationError
from app.services import preprocessing_service
from app.services.inference_service import (
    BundleIntegrityError,
    ConfigMismatchError,
    SchemaMismatchError,
)
from app.services.preprocessing_service import (
    PUBLIC_STATUSES,
    STATUS_PREDICTED,
    STATUS_REJECTED,
    STATUS_UNCERTAIN,
    PreprocessingOutcome,
    preprocess_upload,
)
from app.services.upload_validation import UploadValidationResult, validate_upload
from app.vision.feature_extraction import (
    FEATURE_NAMES,
    LESION_DEPENDENT_FEATURES,
    extract_features_from_pipeline,
)
from app.vision.pipeline import run_segmentation
from tests.vision_helpers import encode_png, leaf_with_spots


def _upload(image: np.ndarray, filename: str = "leaf.png") -> UploadValidationResult:
    return validate_upload(filename, encode_png(image))


def _leaf_upload() -> UploadValidationResult:
    image, _, _ = leaf_with_spots(480, 240)
    return _upload(image)


def _baseline_features(upload: UploadValidationResult):
    assert upload.detected_format == "PNG"
    baseline = extract_features_from_pipeline(run_segmentation(upload.content))
    assert baseline.values is not None
    return baseline


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_outcome_carries_features_artifacts_and_provenance() -> None:
    upload = _leaf_upload()

    outcome = preprocess_upload(upload)

    assert isinstance(outcome, PreprocessingOutcome)
    assert outcome.status in PUBLIC_STATUSES
    assert outcome.status != STATUS_REJECTED
    assert outcome.upload is upload

    assert outcome.values is not None
    assert outcome.values.shape == (len(FEATURE_NAMES),)
    assert outcome.feature_names == FEATURE_NAMES
    assert set(outcome.missing_features) <= set(LESION_DEPENDENT_FEATURES)

    # Artefacts a later `/predict` response or diagnostic view can serve.
    assert outcome.artifacts.available is True
    assert outcome.artifacts.original.ndim == 3
    assert outcome.artifacts.working.ndim == 3
    assert outcome.artifacts.leaf_mask is not None
    assert outcome.artifacts.canvas is not None
    assert outcome.artifacts.canvas_leaf_mask is not None
    assert outcome.artifacts.lesion_mask is not None

    assert outcome.feature_set_version == "1.0.0"
    assert outcome.model_version == "svm-v1.0.0"
    assert outcome.segmentation_config_version == "seg-v2"
    assert outcome.quality_config_version == "quality-v1"
    assert "decode_and_working" in outcome.stage_ms
    assert "total" in outcome.stage_ms

    if outcome.lesion_reliable:
        assert outcome.lesion_area_percentage is not None
        assert 0.0 <= outcome.lesion_area_percentage <= 100.0
    else:
        assert outcome.lesion_area_percentage is None


def test_outcome_is_deterministic() -> None:
    upload = _leaf_upload()

    first = preprocess_upload(upload)
    second = preprocess_upload(upload)

    assert first.status == second.status
    assert first.values is not None and second.values is not None
    assert np.array_equal(np.nan_to_num(first.values), np.nan_to_num(second.values))
    assert first.missing_features == second.missing_features
    assert np.array_equal(first.artifacts.lesion_mask, second.artifacts.lesion_mask)


# --------------------------------------------------------------------------- #
# Status mapping
# --------------------------------------------------------------------------- #


def test_rejected_image_is_rejected_without_any_measurement() -> None:
    blank = np.full((400, 400, 3), 250, dtype=np.uint8)

    outcome = preprocess_upload(_upload(blank))

    assert outcome.status == STATUS_REJECTED
    assert outcome.is_rejected is True
    assert outcome.values is None
    assert outcome.lesion_area_percentage is None
    assert outcome.lesion_reliable is False
    assert "NO_CLEAR_LEAF_FOUND" in outcome.rejections
    assert set(outcome.missing_features) == set(FEATURE_NAMES)
    assert outcome.artifacts.available is False
    assert outcome.artifacts.lesion_mask is None


def test_degraded_image_is_uncertain_never_confident() -> None:
    # A pure close-up triggers the documented full-frame fallback warning.
    image = np.full((400, 400, 3), (60, 140, 70), dtype=np.uint8)
    rng = np.random.default_rng(3)
    image = np.clip(
        image.astype(np.int16) + rng.integers(-10, 11, image.shape), 0, 255
    ).astype(np.uint8)

    outcome = preprocess_upload(_upload(image))

    assert outcome.status == STATUS_UNCERTAIN
    assert "FULL_FRAME_FALLBACK" in outcome.warnings
    assert outcome.values is not None


def test_public_status_set_has_no_healthy_state() -> None:
    assert PUBLIC_STATUSES == ("predicted", "uncertain", "rejected")
    assert all("healthy" not in status for status in PUBLIC_STATUSES)


def test_clean_leaf_maps_to_predicted_or_uncertain_only() -> None:
    outcome = preprocess_upload(_leaf_upload())

    assert outcome.status in {STATUS_PREDICTED, STATUS_UNCERTAIN}
    assert outcome.status != STATUS_REJECTED


# --------------------------------------------------------------------------- #
# Lesion honesty
# --------------------------------------------------------------------------- #


def test_unreliable_lesion_stays_nan_and_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    upload = _leaf_upload()
    baseline = _baseline_features(upload)

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

    outcome = preprocess_upload(upload)

    assert outcome.status == STATUS_UNCERTAIN
    assert outcome.lesion_reliable is False
    assert outcome.lesion_area_percentage is None
    lesion_slice = outcome.values[-len(LESION_DEPENDENT_FEATURES) :]
    assert np.isnan(lesion_slice).all()
    assert not np.any(lesion_slice == 0.0)
    assert "LESION_REFERENCE_UNAVAILABLE" in outcome.warnings


def test_unreliable_lesion_area_is_never_coerced_from_the_pipeline() -> None:
    """Even if a pipeline carried a number, an unreliable estimate exposes ``None``."""
    upload = _leaf_upload()
    outcome = preprocess_upload(upload)
    forced = replace(
        outcome,
        feature_result=replace(
            outcome.feature_result,
            lesion_reliable=False,
            lesion_area_percentage=12.5,
        ),
    )

    assert forced.lesion_area_percentage is None


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #


def test_missing_model_refuses_before_any_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unavailable() -> None:
        raise BundleIntegrityError("model_pipeline.joblib is corrupted")

    def _must_not_run(*_args, **_kwargs):
        pytest.fail("the vision pipeline must not run without a verified model")

    monkeypatch.setattr(preprocessing_service, "get_inference_service", _unavailable)
    monkeypatch.setattr(preprocessing_service, "run_segmentation", _must_not_run)

    image, _, _ = leaf_with_spots(320, 160)
    with pytest.raises(ModelNotLoadedError):
        preprocess_upload(_upload(image))


def test_undecodable_bytes_become_a_typed_upload_error() -> None:
    content = b"this is not an image"
    broken = UploadValidationResult(
        filename="broken.png",
        extension=".png",
        detected_format="PNG",
        size_bytes=len(content),
        width=100,
        height=100,
        mode="RGB",
        exif_orientation=None,
        content=content,
    )

    with pytest.raises(UploadValidationError):
        preprocess_upload(broken)


def test_features_from_a_different_configuration_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = _leaf_upload()
    stale = replace(_baseline_features(upload), segmentation_config_sha256="0" * 64)
    monkeypatch.setattr(
        preprocessing_service, "extract_features_from_pipeline", lambda _: stale
    )

    with pytest.raises(ConfigMismatchError):
        preprocess_upload(upload)


def test_features_from_a_different_schema_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = _leaf_upload()
    stale = replace(_baseline_features(upload), schema_version="0.9.0")
    monkeypatch.setattr(
        preprocessing_service, "extract_features_from_pipeline", lambda _: stale
    )

    with pytest.raises(SchemaMismatchError):
        preprocess_upload(upload)
