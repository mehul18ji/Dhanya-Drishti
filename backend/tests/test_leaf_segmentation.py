"""Leaf-segmentation tests on synthetic images (no dataset required)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.vision.config import load_segmentation_config
from app.vision.leaf_segmentation import (
    build_colour_mask,
    score_candidates,
    segment_leaf,
)
from app.vision.preprocessing import load_oriented_image, make_working_image
from tests.vision_helpers import encode_png, leaf_on_background


def _load(bgr: np.ndarray) -> np.ndarray:
    return make_working_image(load_oriented_image(encode_png(bgr)), 768).bgr


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    a = first > 0
    b = second > 0
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(a, b).sum() / union)


def test_single_leaf_is_found_without_fallback() -> None:
    image, expected = leaf_on_background(640, 360, leaf_box=(120, 100, 400, 160))
    result = segment_leaf(_load(image), load_segmentation_config())

    assert result.found is True
    assert result.mask is not None
    assert result.used_full_frame_fallback is False
    assert result.multiple_leaves is False
    assert 0.20 < result.area_fraction < 0.35
    assert _iou(result.mask, expected) > 0.90
    assert result.bbox is not None


def test_close_up_uses_full_frame_fallback() -> None:
    image = np.full((400, 400, 3), (60, 140, 70), dtype=np.uint8)
    result = segment_leaf(_load(image), load_segmentation_config())

    assert result.found is True
    assert result.used_full_frame_fallback is True
    assert result.area_fraction == pytest.approx(1.0)
    assert result.method == "full_frame_fallback"
    assert "FULL_FRAME_FALLBACK" in result.warnings


def test_two_leaves_trigger_warning_and_select_the_larger() -> None:
    image = np.full((400, 800, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (60, 120), (359, 279), (60, 140, 70), -1)   # 300 x 160
    cv2.rectangle(image, (460, 140), (659, 259), (60, 140, 70), -1)  # 200 x 120

    result = segment_leaf(_load(image), load_segmentation_config())

    assert result.found is True
    assert result.used_full_frame_fallback is False
    assert result.multiple_leaves is True
    assert "MULTIPLE_LEAVES" in result.warnings
    assert result.candidate_count >= 2

    # The primary candidate must be the larger leaf.
    assert result.bbox is not None
    x, _, width, _ = result.bbox
    assert x < 400


def test_non_leaf_image_is_not_forced_into_a_prediction() -> None:
    image = np.full((400, 400, 3), 250, dtype=np.uint8)
    for offset in range(60, 320, 40):
        cv2.rectangle(image, (80, offset), (320, offset + 10), (0, 0, 0), -1)

    result = segment_leaf(_load(image), load_segmentation_config())

    assert result.found is False
    assert result.mask is None
    assert result.failure_reason == "NO_CLEAR_LEAF_FOUND"
    assert result.used_full_frame_fallback is False


def test_segmentation_is_deterministic() -> None:
    image, _ = leaf_on_background(640, 360, leaf_box=(100, 90, 420, 180))
    config = load_segmentation_config()
    working = _load(image)

    first = segment_leaf(working, config)
    second = segment_leaf(working, config)

    assert first.found == second.found
    assert np.array_equal(first.mask, second.mask)
    assert first.area_fraction == second.area_fraction
    assert first.bbox == second.bbox


def test_colour_mask_ignores_neutral_paper_and_grey() -> None:
    white = np.full((200, 200, 3), 250, dtype=np.uint8)
    grey = np.full((200, 200, 3), 128, dtype=np.uint8)
    config = load_segmentation_config()

    white_mask, _ = build_colour_mask(white, config.leaf)
    grey_mask, _ = build_colour_mask(grey, config.leaf)

    assert white_mask.sum() == 0
    assert grey_mask.sum() == 0


def test_candidate_scoring_ignores_specks() -> None:
    image, _ = leaf_on_background(640, 360, leaf_box=(200, 120, 240, 120))
    config = load_segmentation_config()
    working = _load(image)

    # A one-pixel speck must not become a candidate.
    working[10, 10] = (60, 140, 70)
    result = segment_leaf(working, config)
    assert result.found is True
    assert result.candidate_count == 1


def test_lab_and_hsv_agree_on_real_leaf_colours() -> None:
    image, _ = leaf_on_background(400, 300)
    config = load_segmentation_config()
    colour_mask, green_mask = build_colour_mask(_load(image), config.leaf)

    assert (colour_mask > 0).sum() > 0
    assert (green_mask > 0).sum() > 0
    # Green is a subset of the combined candidate mask.
    assert np.all(colour_mask[green_mask > 0] > 0)


def test_scored_candidates_are_sorted_by_score() -> None:
    mask = np.zeros((400, 800), dtype=np.uint8)
    cv2.rectangle(mask, (60, 120), (359, 279), 255, -1)
    cv2.rectangle(mask, (460, 140), (659, 259), 255, -1)
    config = load_segmentation_config()

    candidates = score_candidates(mask, config.leaf)
    scores = [candidate.score for candidate in candidates]
    assert scores == sorted(scores, reverse=True)
    assert candidates[0].area > candidates[1].area
