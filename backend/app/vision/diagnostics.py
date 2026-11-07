"""Visual diagnostic renders for the segmentation stage (Phase 2 deliverable).

The mentor-facing evidence for PRD §25 Phase 2 ("visual mask outputs") is a
4-up panel per image: the letterboxed input canvas, the leaf mask, the lesion
mask and the final overlay. These helpers are pure: they take arrays and return
arrays, so the audit script (now) and the API artifact service (Phase 4) can
share one implementation and only differ in where they write the bytes.
"""

from __future__ import annotations

import cv2
import numpy as np

LEAF_COLOUR = (80, 220, 80)  # BGR green
LESION_COLOUR = (60, 60, 230)  # BGR red
PANEL_BACKGROUND = 24
LABEL_HEIGHT = 26
TITLE_HEIGHT = 30
GAP = 6
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _ascii(text: str) -> str:
    """OpenCV's Hershey fonts only render ASCII; keep the panel renderable."""
    return str(text).encode("ascii", "replace").decode("ascii")


def mask_preview(mask: np.ndarray, *, background: int = PANEL_BACKGROUND) -> np.ndarray:
    """Render a binary mask as a 3-channel image (white = selected)."""
    binary = (np.asarray(mask) > 0).astype(np.uint8) * 255
    grey = np.where(binary > 0, 255, background).astype(np.uint8)
    return cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)


def overlay_mask(
    bgr: np.ndarray,
    mask: np.ndarray,
    *,
    colour: tuple[int, int, int],
    alpha: float = 0.40,
    outline: bool = True,
) -> np.ndarray:
    """Tint ``mask`` over a copy of ``bgr`` and optionally outline its contours."""
    binary = (np.asarray(mask) > 0).astype(np.uint8) * 255
    overlay = bgr.copy()
    if not binary.any():
        return overlay

    selected = binary > 0
    tinted = np.full_like(overlay, colour, dtype=np.uint8)
    overlay[selected] = cv2.addWeighted(
        overlay[selected], 1.0 - alpha, tinted[selected], alpha, 0.0
    )

    if outline:
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, colour, 2)
    return overlay


def overlay_leaf(bgr: np.ndarray, leaf_mask: np.ndarray) -> np.ndarray:
    """Green tint + outline of the selected leaf."""
    return overlay_mask(bgr, leaf_mask, colour=LEAF_COLOUR, alpha=0.25)


def overlay_lesions(
    bgr: np.ndarray,
    leaf_mask: np.ndarray,
    lesion_mask: np.ndarray | None,
) -> np.ndarray:
    """Leaf outline in green with lesion tissue tinted red."""
    overlay = overlay_leaf(bgr, leaf_mask)
    if lesion_mask is None:
        return overlay
    return overlay_mask(overlay, lesion_mask, colour=LESION_COLOUR, alpha=0.55, outline=False)


def _label(tile: np.ndarray, text: str) -> np.ndarray:
    """Add a dark caption strip above a tile."""
    width = tile.shape[1]
    strip = np.full((LABEL_HEIGHT, width, 3), PANEL_BACKGROUND, dtype=np.uint8)
    cv2.putText(
        strip,
        _ascii(text)[:60],
        (6, LABEL_HEIGHT - 8),
        FONT,
        0.42,
        (225, 225, 225),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([strip, tile])


def _separator(height: int, colour: int = 70) -> np.ndarray:
    return np.full((height, GAP, 3), colour, dtype=np.uint8)


def build_diagnostic_panel(
    canvas_bgr: np.ndarray,
    leaf_mask: np.ndarray,
    lesion_mask: np.ndarray | None,
    *,
    title: str,
) -> np.ndarray:
    """Build the 4-up review panel: input, leaf mask, lesion mask, overlay.

    ``canvas_bgr``, ``leaf_mask`` and ``lesion_mask`` must share one size — that
    is the letterboxed processing canvas from ``prepare_processing_canvas``.
    """
    canvas = np.asarray(canvas_bgr)
    leaf = np.asarray(leaf_mask)
    if canvas.shape[:2] != leaf.shape[:2]:
        raise ValueError(
            f"leaf mask {leaf.shape[:2]} does not match canvas {canvas.shape[:2]}"
        )
    if lesion_mask is None:
        lesion_tile = np.zeros_like(leaf)
        lesion_label = "Lesion mask (not computed)"
    else:
        lesion_tile = np.asarray(lesion_mask)
        if lesion_tile.shape[:2] != canvas.shape[:2]:
            raise ValueError(
                f"lesion mask {lesion_tile.shape[:2]} does not match canvas "
                f"{canvas.shape[:2]}"
            )
        lesion_label = "Lesion mask"

    tiles = [
        _label(canvas, "Input canvas (letterboxed)"),
        _label(mask_preview(leaf), "Leaf mask"),
        _label(mask_preview(lesion_tile), lesion_label),
        _label(overlay_lesions(canvas, leaf, lesion_tile), "Overlay (leaf / lesion)"),
    ]

    body = tiles[0]
    for tile in tiles[1:]:
        body = np.hstack([body, _separator(body.shape[0]), tile])

    title_strip = np.full((TITLE_HEIGHT, body.shape[1], 3), 12, dtype=np.uint8)
    cv2.putText(
        title_strip,
        _ascii(title)[:110],
        (8, TITLE_HEIGHT - 9),
        FONT,
        0.5,
        (240, 240, 240),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([title_strip, body])
