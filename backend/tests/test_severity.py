"""Severity-bucket tests (Phase 4 M5, PRD §12).

No dataset, no model and no held-out rows: the module is a pure mapping from a
measured lesion area plus its reliability to one of three labels.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from pydantic import ValidationError

from app.services import preprocessing_service
from app.services.preprocessing_service import preprocess_upload
from app.services.upload_validation import validate_upload
from app.vision.config import (
    SeverityConfig,
    load_severity_config,
    SeverityThresholds,
)
from app.vision.severity import (
    REASON_INVALID,
    REASON_MISSING,
    REASON_UNRELIABLE,
    UNRELIABLE_WARNING,
    severity_for,
)
from tests.vision_helpers import encode_png, leaf_with_spots

#: The exact wording PRD §12 requires under "Required disclaimer".
PRD_DISCLAIMER = (
    "Severity is an experimental estimate based on the visible lesion area in "
    "this image. It is not a validated agronomic severity grade."
)


# --------------------------------------------------------------------------- #
# Configuration contract
# --------------------------------------------------------------------------- #


def test_config_is_versioned_and_matches_the_prd_policy() -> None:
    config = load_severity_config()

    assert config.severity_config_version == "severity-v1"
    assert config.severity_method == "experimental_lesion_area_thresholds"
    assert config.thresholds.mild_max_percent == 10.0
    assert config.thresholds.moderate_max_percent == 25.0
    assert (config.labels.mild, config.labels.moderate, config.labels.severe) == (
        "Mild",
        "Moderate",
        "Severe",
    )
    assert config.disclaimer == PRD_DISCLAIMER
    assert config.short_note == "Experimental lesion-area estimate."


def test_config_is_hashable_and_every_result_records_it() -> None:
    config = load_severity_config()
    assert len(config.content_sha256) == 64
    assert config.source_path.endswith("severity.yaml")

    available = severity_for(12.0, config=config)
    unavailable = severity_for(None, config=config)

    for result in (available, unavailable):
        assert result.config_version == "severity-v1"
        assert result.config_sha256 == config.content_sha256
        assert result.method == "experimental_lesion_area_thresholds"
        assert result.disclaimer == PRD_DISCLAIMER


def test_changed_thresholds_change_the_config_hash(tmp_path) -> None:
    original = load_severity_config()
    edited = tmp_path / "severity.yaml"
    edited.write_text(
        original.model_dump_json(exclude={"source_path", "content_sha256"}),
        encoding="utf-8",
    )
    # JSON is valid YAML; the loader must still validate and hash it.
    reloaded = load_severity_config(edited)

    assert reloaded.severity_config_version == "severity-v1"
    assert reloaded.content_sha256 != original.content_sha256
    assert len(reloaded.content_sha256) == 64


def test_thresholds_come_from_configuration_not_from_code() -> None:
    config = load_severity_config()
    custom = config.model_copy(
        update={"thresholds": SeverityThresholds(mild_max_percent=5.0, moderate_max_percent=12.0)}
    )

    assert severity_for(7.0, config=config).severity == "Mild"
    assert severity_for(7.0, config=custom).severity == "Moderate"
    assert severity_for(12.0, config=custom).severity == "Severe"


# --------------------------------------------------------------------------- #
# Buckets and exact boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        (0.0, "Mild"),
        (0.01, "Mild"),
        (9.999, "Mild"),
        (10.0, "Moderate"),
        (12.4, "Moderate"),
        (24.999, "Moderate"),
        (25.0, "Severe"),
        (61.5, "Severe"),
        (100.0, "Severe"),
    ],
)
def test_locked_buckets_and_boundaries(area: float, expected: str) -> None:
    result = severity_for(area)

    assert result.severity == expected
    assert result.available is True
    assert result.reason_code is None
    assert result.lesion_area_percentage == pytest.approx(area)


def test_measured_zero_is_mild_not_unavailable() -> None:
    """A calibrated leaf with no detected lesion is a real 0 %, not missing data."""
    result = severity_for(0.0, lesion_reliable=True)

    assert result.severity == "Mild"
    assert result.lesion_area_percentage == 0.0


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_unreliable_lesion_never_becomes_a_label() -> None:
    result = severity_for(40.0, lesion_reliable=False)

    assert result.severity is None
    assert result.available is False
    assert result.reason_code == REASON_UNRELIABLE
    assert result.disclaimer == PRD_DISCLAIMER
    assert result.short_note == "Experimental lesion-area estimate."


def test_reference_unavailable_warning_overrides_a_reliable_flag() -> None:
    result = severity_for(5.0, lesion_reliable=True, warnings=(UNRELIABLE_WARNING,))

    assert result.severity is None
    assert result.reason_code == REASON_UNRELIABLE


def test_missing_lesion_area_is_none_not_zero() -> None:
    result = severity_for(None)

    assert result.severity is None
    assert result.lesion_area_percentage is None
    assert result.reason_code == REASON_MISSING
    assert result.disclaimer == PRD_DISCLAIMER


@pytest.mark.parametrize("area", [float("nan"), float("inf"), -1.0, 100.5])
def test_invalid_lesion_area_is_refused(area: float) -> None:
    result = severity_for(area)

    assert result.severity is None
    assert result.reason_code == REASON_INVALID
    assert result.disclaimer == PRD_DISCLAIMER


# --------------------------------------------------------------------------- #
# Integration with the M4 orchestration (synthetic images only)
# --------------------------------------------------------------------------- #


def test_outcome_drives_severity_honestly() -> None:
    image, _, _ = leaf_with_spots(480, 240)
    upload = validate_upload("leaf.png", encode_png(image))

    outcome = preprocess_upload(upload)
    result = severity_for(
        outcome.lesion_area_percentage,
        lesion_reliable=outcome.lesion_reliable,
        warnings=outcome.warnings,
    )

    if outcome.lesion_reliable:
        assert result.severity in {"Mild", "Moderate", "Severe"}
        assert result.lesion_area_percentage == pytest.approx(
            outcome.lesion_area_percentage
        )
    else:
        assert result.severity is None
        assert result.reason_code == REASON_UNRELIABLE


def test_rejected_image_yields_no_severity() -> None:
    blank = np.full((400, 400, 3), 250, dtype=np.uint8)
    outcome = preprocess_upload(validate_upload("blank.png", encode_png(blank)))

    result = severity_for(
        outcome.lesion_area_percentage,
        lesion_reliable=outcome.lesion_reliable,
        warnings=outcome.warnings,
    )

    assert outcome.status == "rejected"
    assert result.severity is None
    assert result.lesion_area_percentage is None


def test_unreliable_outcome_never_reports_mild(monkeypatch: pytest.MonkeyPatch) -> None:
    image, _, _ = leaf_with_spots(480, 240)
    upload = validate_upload("leaf.png", encode_png(image))

    from app.vision.feature_extraction import extract_features_from_pipeline
    from app.vision.pipeline import run_segmentation

    baseline = extract_features_from_pipeline(run_segmentation(upload.content))
    degraded = dataclasses.replace(
        baseline,
        status="uncertain",
        lesion_reliable=False,
        lesion_reference_available=False,
        lesion_area_percentage=None,
        warnings=("LESION_REFERENCE_UNAVAILABLE",),
    )
    monkeypatch.setattr(
        preprocessing_service, "extract_features_from_pipeline", lambda _: degraded
    )

    outcome = preprocess_upload(upload)
    result = severity_for(
        outcome.lesion_area_percentage,
        lesion_reliable=outcome.lesion_reliable,
        warnings=outcome.warnings,
    )

    assert outcome.status == "uncertain"
    assert result.severity is None
    assert result.severity != "Mild"
    assert result.reason_code == REASON_UNRELIABLE


def test_config_rejects_inverted_thresholds() -> None:
    with pytest.raises(ValidationError):
        SeverityConfig.model_validate(
            {
                "severity_config_version": "severity-v1",
                "severity_method": "experimental_lesion_area_thresholds",
                "thresholds": {"mild_max_percent": 30.0, "moderate_max_percent": 10.0},
                "labels": {"mild": "Mild", "moderate": "Moderate", "severe": "Severe"},
                "disclaimer": PRD_DISCLAIMER,
                "short_note": "Experimental lesion-area estimate.",
            }
        )
