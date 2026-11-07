"""Diagnostic-render tests: panels are shaped correctly and never alter the input."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.vision.diagnostics import (
    GAP,
    LABEL_HEIGHT,
    TITLE_HEIGHT,
    build_diagnostic_panel,
    mask_preview,
    overlay_lesions,
    overlay_mask,
)


def _canvas(mask: np.ndarray) -> np.ndarray:
    return np.full((*mask.shape, 3), 200, dtype=np.uint8)


def _masks(size: int = 96) -> tuple[np.ndarray, np.ndarray]:
    leaf = np.zeros((size, size), dtype=np.uint8)
    cv2.rectangle(leaf, (12, 20), (size - 13, size - 21), 255, -1)
    lesion = np.zeros((size, size), dtype=np.uint8)
    cv2.rectangle(lesion, (30, 34), (44, 48), 255, -1)
    return leaf, lesion


def test_mask_preview_is_binary_and_three_channel() -> None:
    leaf, _ = _masks()
    preview = mask_preview(leaf)

    assert preview.shape == (*leaf.shape, 3)
    assert preview.dtype == np.uint8
    assert (preview[0, 0] != 255).all()  # background
    assert (preview[30, 30] == 255).all()  # selected


def test_overlay_only_changes_selected_pixels() -> None:
    leaf, _ = _masks()
    canvas = _canvas(leaf)
    overlaid = overlay_mask(canvas, leaf, colour=(0, 255, 0), alpha=0.5)

    assert overlaid.shape == canvas.shape
    assert np.array_equal(overlaid[0, 0], canvas[0, 0])  # outside the mask
    assert not np.array_equal(overlaid[30, 30], canvas[30, 30])  # inside the mask
    # The input array must never be modified in place.
    assert np.array_equal(canvas, _canvas(leaf))


def test_overlay_of_an_empty_mask_is_a_copy() -> None:
    leaf, _ = _masks()
    canvas = _canvas(leaf)
    empty = np.zeros_like(leaf)

    result = overlay_mask(canvas, empty, colour=(0, 255, 0))
    assert np.array_equal(result, canvas)


def test_lesion_overlay_tints_lesions_red_and_keeps_shape() -> None:
    leaf, lesion = _masks()
    canvas = _canvas(leaf)
    result = overlay_lesions(canvas, leaf, lesion)

    assert result.shape == canvas.shape
    blue, green, red = result[40, 35].tolist()
    assert red > blue and red > green  # lesion tint is red-dominant


def test_panel_layout_has_four_tiles_and_a_title() -> None:
    leaf, lesion = _masks()
    canvas = _canvas(leaf)
    panel = build_diagnostic_panel(canvas, leaf, lesion, title="test.png | seg-v1")

    expected_width = canvas.shape[1] * 4 + GAP * 3
    expected_height = TITLE_HEIGHT + LABEL_HEIGHT + canvas.shape[0]
    assert panel.shape == (expected_height, expected_width, 3)
    assert panel.dtype == np.uint8


def test_panel_accepts_a_missing_lesion_mask() -> None:
    leaf, _ = _masks()
    panel = build_diagnostic_panel(_canvas(leaf), leaf, None, title="no leaf")
    assert panel.shape[0] == TITLE_HEIGHT + LABEL_HEIGHT + leaf.shape[0]


def test_panel_rejects_mismatched_shapes() -> None:
    leaf, _ = _masks()
    canvas = _canvas(leaf)

    with pytest.raises(ValueError):
        build_diagnostic_panel(canvas, np.zeros((10, 10), dtype=np.uint8), None, title="bad")

    with pytest.raises(ValueError):
        build_diagnostic_panel(canvas, leaf, np.zeros((10, 10), dtype=np.uint8), title="bad")


def test_panel_survives_non_ascii_titles() -> None:
    leaf, lesion = _masks()
    panel = build_diagnostic_panel(
        _canvas(leaf), leaf, lesion, title="Brown spot \\u2014 DSC_0508.jpg"
    )
    assert panel.size > 0
