"""Contract tests for the versioned feature extractor (Phase 3 M1).

These tests protect the two things a saved model depends on:

1. the **order** of the feature vector equals the schema order, and
2. an uncalibrated lesion estimate is never turned into ``0 %`` lesion.

No dataset and no training are required.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from app.vision.feature_extraction import (
    FEATURE_GROUPS,
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
    SHAPE_FEATURES,
    TEXTURE_FEATURES,
    extract_features,
    extract_features_from_pipeline,
    feature_schema,
)
from app.vision.pipeline import run_segmentation
from app.vision.types import LesionSegmentationResult
from tests.vision_helpers import encode_png, leaf_with_spots, textured_leaf


def _clean_result():
    image, _, _ = leaf_with_spots(480, 240)
    return run_segmentation(encode_png(image))


def test_schema_is_versioned_and_machine_readable() -> None:
    schema = feature_schema()

    assert FEATURE_SET_VERSION == "1.0.0"
    assert schema["feature_set_version"] == FEATURE_SET_VERSION
    assert schema["feature_count"] == len(FEATURE_NAMES)
    assert schema["feature_names"] == list(FEATURE_NAMES)
    assert schema["glcm"]["levels"] == 32
    assert "NaN" in schema["missing_value_policy"]


def test_groups_partition_the_schema_without_duplicates() -> None:
    grouped: list[str] = []
    for names in FEATURE_GROUPS.values():
        grouped.extend(names)

    assert tuple(grouped) == FEATURE_NAMES
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    assert "missing" not in " ".join(FEATURE_NAMES).lower()
    # Lesion- and spatial-derived names are the tail of the vector.
    assert FEATURE_NAMES[-len(LESION_DEPENDENT_FEATURES) :] == LESION_DEPENDENT_FEATURES


def test_extracted_vector_matches_schema_order_and_length() -> None:
    result = extract_features_from_pipeline(_clean_result())

    assert result.usable is True
    assert result.schema_version == FEATURE_SET_VERSION
    assert result.values is not None
    assert result.values.dtype == np.float32
    assert result.values.shape == (len(FEATURE_NAMES),)
    assert result.feature_names == FEATURE_NAMES

    mapped = result.as_dict()
    assert list(mapped) == list(FEATURE_NAMES)

    # Colour and shape are always measurable and stay inside sane bounds.
    for name in ("rgb_r_mean", "hsv_h_mean", "lab_a_mean", "leaf_area_fraction"):
        value = mapped[name]
        assert value is not None and 0.0 <= value <= 1.0


def test_feature_vector_is_deterministic() -> None:
    payload = encode_png(textured_leaf(640, 360))

    first = extract_features(payload)
    second = extract_features(payload)

    assert first.values is not None and second.values is not None
    assert np.array_equal(np.nan_to_num(first.values), np.nan_to_num(second.values))
    assert first.status == second.status
    assert first.missing_features == second.missing_features


def test_schema_reports_segmentation_and_quality_provenance() -> None:
    result = extract_features_from_pipeline(_clean_result())
    schema = result.schema()

    assert schema["segmentation_config_version"] == "seg-v2"
    assert schema["quality_config_version"] == "quality-v1"
    assert len(schema["segmentation_config_sha256"]) == 64
    assert len(schema["quality_config_sha256"]) == 64
    assert schema["feature_names"] == list(FEATURE_NAMES)


def test_rejected_image_has_no_feature_vector_and_no_zeros() -> None:
    blank = np.full((400, 400, 3), 250, dtype=np.uint8)

    result = extract_features(encode_png(blank))

    assert result.status == "rejected"
    assert result.values is None
    assert result.usable is False
    assert result.lesion_area_percentage is None
    assert result.lesion_reliable is False
    assert set(result.missing_features) == set(FEATURE_NAMES)
    assert "NO_CLEAR_LEAF_FOUND" in result.rejections
    assert all(value is None for value in result.as_dict().values())


def test_uncalibrated_lesion_features_are_missing_not_zero() -> None:
    """"Uncertain" must never be written as `0 %` lesion (Phase 3 input contract)."""
    baseline = _clean_result()
    assert baseline.lesion is not None

    unavailable = replace(
        baseline,
        lesion=LesionSegmentationResult(
            mask=np.zeros_like(baseline.lesion.mask),
            lesion_area_fraction=0.0,
            lesion_count=0,
            largest_lesion_fraction=0.0,
            mean_lesion_area_fraction=0.0,
            method="relative_colour_kmeans",
            warnings=("LESION_REFERENCE_UNAVAILABLE",),
            reliable=False,
        ),
    )

    result = extract_features_from_pipeline(unavailable)

    assert result.lesion_reliable is False
    assert result.lesion_reference_available is False
    assert result.lesion_area_percentage is None
    assert result.status == "uncertain"
    assert set(result.missing_features) == set(LESION_DEPENDENT_FEATURES)
    assert "LESION_REFERENCE_UNAVAILABLE" in result.warnings

    assert result.values is not None
    mapped = result.as_dict()
    for name in LESION_DEPENDENT_FEATURES:
        value = mapped[name]
        assert value is None, f"{name} must be missing, not 0.0"
    for name in SHAPE_FEATURES + TEXTURE_FEATURES:
        assert mapped[name] is not None, f"{name} does not depend on the lesion stage"

    lesion_slice = result.values[len(FEATURE_NAMES) - len(LESION_DEPENDENT_FEATURES) :]
    assert np.isnan(lesion_slice).all()
    assert not np.any(lesion_slice == 0.0)


def test_measured_zero_lesion_is_reported_as_zero_not_missing() -> None:
    """A calibrated leaf with no detected lesion is a real 0, not a missing value."""
    baseline = _clean_result()
    assert baseline.lesion is not None

    no_lesion = replace(
        baseline,
        lesion=replace(
            baseline.lesion,
            mask=np.zeros_like(baseline.lesion.mask),
            lesion_area_fraction=0.0,
            lesion_count=0,
            largest_lesion_fraction=0.0,
            mean_lesion_area_fraction=0.0,
            warnings=(),
            reliable=True,
        ),
    )

    result = extract_features_from_pipeline(no_lesion)

    assert result.lesion_reliable is True
    assert result.lesion_area_percentage == pytest.approx(0.0)
    assert result.values is not None
    mapped = result.as_dict()
    assert mapped["lesion_area_ratio"] == pytest.approx(0.0)
    assert mapped["lesion_count_per_kpx"] == pytest.approx(0.0)
    assert set(result.missing_features) == set()
