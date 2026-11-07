"""Synthetic-image helpers shared by the vision tests (no dataset required)."""

from __future__ import annotations

import cv2
import numpy as np


def encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:  # pragma: no cover - impossible for a valid ndarray
        raise RuntimeError("could not encode synthetic PNG")
    return buffer.tobytes()


def leaf_on_background(
    width: int,
    height: int,
    *,
    leaf_box: tuple[int, int, int, int] | None = None,
    background: int = 245,
    leaf_color: tuple[int, int, int] = (60, 140, 70),
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(bgr, mask)`` for a rectangular leaf on a bright background."""
    image = np.full((height, width, 3), background, dtype=np.uint8)
    if leaf_box is None:
        margin_x = max(2, width // 6)
        margin_y = max(2, height // 3)
        leaf_box = (margin_x, margin_y, width - 2 * margin_x, height - 2 * margin_y)
    x, y, w, h = leaf_box
    cv2.rectangle(image, (x, y), (x + w - 1, y + h - 1), leaf_color, -1)

    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y : y + h, x : x + w] = 255
    return image, mask


def leaf_with_spots(
    width: int = 400,
    height: int = 200,
    *,
    spot_boxes: list[tuple[int, int, int, int]] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Green leaf with brown rectangular lesions.

    Returns ``(bgr, leaf_mask, expected_lesion_mask)``.
    """
    image, leaf_mask = leaf_on_background(
        width,
        height,
        leaf_box=(40, 40, width - 80, height - 80),
        leaf_color=(70, 150, 80),
    )
    expected = np.zeros((height, width), dtype=np.uint8)
    if spot_boxes is None:
        spot_boxes = [
            (100, 80, 24, 20),
            (220, 110, 18, 16),
        ]
    for x, y, w, h in spot_boxes:
        cv2.rectangle(image, (x, y), (x + w - 1, y + h - 1), (40, 70, 120), -1)
        expected[y : y + h, x : x + w] = 255
    return image, leaf_mask, expected


def textured_leaf(width: int = 640, height: int = 360) -> np.ndarray:
    """Leaf image with enough texture that the blur check does not fire."""
    image, _ = leaf_on_background(width, height)
    rng = np.random.default_rng(7)
    noise = rng.integers(-12, 13, size=image.shape, dtype=np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
