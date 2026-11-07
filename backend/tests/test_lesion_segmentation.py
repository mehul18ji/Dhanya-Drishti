"""Lesion-segmentation tests on synthetic leaves (no dataset required)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.vision.config import load_segmentation_config
from app.vision.lesion_segmentation import segment_lesions
from tests.vision_helpers import leaf_on_background, leaf_with_spots


def test_two_brown_spots_are_detected() -> None:
    image, leaf_mask, expected = leaf_with_spots(400, 200)
    result = segment_lesions(image, leaf_mask, load_segmentation_config())

    expected_fraction = (expected > 0).sum() / (leaf_mask > 0).sum()
    assert result.lesion_count == 2
    assert result.lesion_area_fraction == pytest.approx(expected_fraction, abs=0.006)
    assert result.largest_lesion_fraction > 0.005

    recall = np.logical_and(result.mask > 0, expected > 0).sum() / (expected > 0).sum()
    assert recall > 0.90


def test_healthy_leaf_has_no_lesions() -> None:
    image, leaf_mask, _ = leaf_with_spots(400, 200, spot_boxes=[])
    result = segment_lesions(image, leaf_mask, load_segmentation_config())

    assert result.lesion_area_fraction < 0.002
    assert result.lesion_count == 0


def test_lesion_mask_never_leaves_the_leaf() -> None:
    image, leaf_mask, _ = leaf_with_spots(400, 200)
    # Brown paint outside the leaf must never be reported as a lesion.
    cv2.rectangle(image, (5, 5), (35, 35), (40, 70, 120), -1)

    result = segment_lesions(image, leaf_mask, load_segmentation_config())
    outside = np.logical_and(result.mask > 0, leaf_mask == 0)
    assert outside.sum() == 0
    assert np.all(result.mask[leaf_mask == 0] == 0)


def test_lesion_segmentation_is_deterministic() -> None:
    image, leaf_mask, _ = leaf_with_spots(400, 200)
    config = load_segmentation_config()

    first = segment_lesions(image, leaf_mask, config)
    second = segment_lesions(image, leaf_mask, config)

    assert np.array_equal(first.mask, second.mask)
    assert first.lesion_area_fraction == second.lesion_area_fraction
    assert first.lesion_count == second.lesion_count


def test_tiny_speck_is_ignored() -> None:
    image, leaf_mask, _ = leaf_with_spots(400, 200, spot_boxes=[])
    leaf_area = int((leaf_mask > 0).sum())
    # A 2x2 speck is below the configured minimum lesion component.
    cv2.rectangle(image, (200, 100), (201, 101), (40, 70, 120), -1)

    result = segment_lesions(image, leaf_mask, load_segmentation_config())
    assert result.lesion_count == 0
    assert result.lesion_area_fraction < 1.0 / leaf_area


def test_mostly_brown_leaf_is_flagged_as_weak() -> None:
    image, leaf_mask = leaf_on_background(
        400, 200, leaf_box=(40, 40, 320, 120), leaf_color=(40, 70, 120)
    )
    result = segment_lesions(image, leaf_mask, load_segmentation_config())

    assert result.lesion_area_fraction > 0.65
    assert "WEAK_LESION_MASK" in result.warnings


def test_necrotic_leaf_without_healthy_reference_is_unreliable() -> None:
    """A leaf with no healthy tissue must never be reported as "0 % lesions".

    Using the necrotic tissue as its own colour reference made the old pipeline
    find no lesions at all on a fully brown leaf. The result is now marked
    unreliable so the API answers `uncertain` instead of a confident value.
    """
    image, leaf_mask = leaf_on_background(
        400, 200, leaf_box=(40, 40, 320, 120), leaf_color=(40, 70, 120)
    )
    result = segment_lesions(image, leaf_mask, load_segmentation_config())

    assert result.reliable is False
    assert result.method == "no_healthy_reference"
    assert result.lesion_area_fraction > 0.9
    assert "LESION_REFERENCE_UNAVAILABLE" in result.warnings
    # The mask still respects the leaf boundary.
    assert np.all(result.mask[leaf_mask == 0] == 0)


def test_healthy_reference_present_keeps_the_estimate_reliable() -> None:
    image, leaf_mask, _ = leaf_with_spots(400, 200)
    result = segment_lesions(image, leaf_mask, load_segmentation_config())
    assert result.reliable is True
    assert result.method == "relative_colour_kmeans"


def test_empty_leaf_mask_is_safe() -> None:
    image = np.full((100, 100, 3), 240, dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    result = segment_lesions(image, mask, load_segmentation_config())

    assert result.lesion_area_fraction == 0.0
    assert result.lesion_count == 0
    assert "WEAK_LESION_MASK" in result.warnings
