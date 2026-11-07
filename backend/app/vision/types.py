"""Shared value objects for the classical computer-vision pipeline.

Keeping geometry and result types here means preprocessing, segmentation and
the future API all speak the same language, and the aspect-ratio contract from
PRD §8 can be tested in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass(frozen=True)
class OrientedImage:
    """Decoded image after EXIF orientation correction, stored as BGR."""

    bgr: np.ndarray
    width: int
    height: int
    source_format: str
    exif_orientation: int
    source_path: str | None = None


@dataclass(frozen=True)
class WorkingImage:
    """Aspect-preserving downscale of the oriented image used for detection."""

    bgr: np.ndarray
    scale_x: float
    scale_y: float
    source_width: int
    source_height: int


@dataclass(frozen=True)
class LetterboxResult:
    """Uniform scale plus symmetric padding into a square canvas."""

    image: np.ndarray
    resized_width: int
    resized_height: int
    pad_left: int
    pad_top: int
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class CanvasTransform:
    """Mapping between the processing canvas and the original oriented image.

    The pipeline never stretches: canvas -> crop -> working -> source uses the
    same uniform scale on both axes (up to sub-pixel rounding).
    """

    source_width: int
    source_height: int
    working_width: int
    working_height: int
    working_scale_x: float
    working_scale_y: float
    crop_box: tuple[int, int, int, int]  # x, y, width, height in working pixels
    resize_scale_x: float
    resize_scale_y: float
    resized_width: int
    resized_height: int
    pad_left: int
    pad_top: int
    canvas_size: int

    def canvas_to_working(self, points: np.ndarray) -> np.ndarray:
        """Map ``(N, 2)`` canvas points to working-image coordinates."""
        points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        x = (points[:, 0] - self.pad_left) / self.resize_scale_x
        y = (points[:, 1] - self.pad_top) / self.resize_scale_y
        return np.stack([x + self.crop_box[0], y + self.crop_box[1]], axis=1)

    def canvas_to_source(self, points: np.ndarray) -> np.ndarray:
        """Map ``(N, 2)`` canvas points to oriented-source pixel coordinates."""
        working = self.canvas_to_working(points)
        return np.stack(
            [
                working[:, 0] / self.working_scale_x,
                working[:, 1] / self.working_scale_y,
            ],
            axis=1,
        )

    def canvas_mask_to_source(self, mask: np.ndarray) -> np.ndarray:
        """Expand a canvas-sized mask back to the oriented-source resolution."""
        canvas_mask = np.asarray(mask)
        if canvas_mask.shape[:2] != (self.canvas_size, self.canvas_size):
            raise ValueError(
                f"mask must be {self.canvas_size}x{self.canvas_size}, "
                f"got {canvas_mask.shape[:2]}"
            )

        unpadded = canvas_mask[
            self.pad_top : self.pad_top + self.resized_height,
            self.pad_left : self.pad_left + self.resized_width,
        ]
        crop_x, crop_y, crop_w, crop_h = self.crop_box
        crop_mask = cv2.resize(unpadded, (crop_w, crop_h), interpolation=cv2.INTER_NEAREST)

        working_mask = np.zeros((self.working_height, self.working_width), dtype=canvas_mask.dtype)
        working_mask[crop_y : crop_y + crop_h, crop_x : crop_x + crop_w] = crop_mask

        return cv2.resize(
            working_mask,
            (self.source_width, self.source_height),
            interpolation=cv2.INTER_NEAREST,
        )


@dataclass(frozen=True)
class QualityIssue:
    """A warning or rejection with a stable code and a human-readable message."""

    code: str
    message: str
    metric: float | int | None = None
    threshold: float | int | None = None


@dataclass
class QualityReport:
    """Metrics plus separate warning and rejection lists (PRD §8)."""

    metrics: dict[str, float | int] = field(default_factory=dict)
    warnings: list[QualityIssue] = field(default_factory=list)
    rejections: list[QualityIssue] = field(default_factory=list)
    config_version: str = ""

    @property
    def passed(self) -> bool:
        return not self.rejections

    def add_warning(
        self,
        code: str,
        *,
        message: str | None = None,
        metric: float | int | None = None,
        threshold: float | int | None = None,
    ) -> None:
        self._add(self.warnings, code, message, metric, threshold)

    def add_rejection(
        self,
        code: str,
        *,
        message: str | None = None,
        metric: float | int | None = None,
        threshold: float | int | None = None,
    ) -> None:
        self._add(self.rejections, code, message, metric, threshold)

    @staticmethod
    def _add(
        target: list[QualityIssue],
        code: str,
        message: str | None,
        metric: float | int | None,
        threshold: float | int | None,
    ) -> None:
        if any(issue.code == code for issue in target):
            return
        from app.vision.messages import WARNING_MESSAGES

        target.append(
            QualityIssue(
                code=code,
                message=message or WARNING_MESSAGES.get(code, code),
                metric=metric,
                threshold=threshold,
            )
        )

    def merge(self, other: "QualityReport") -> "QualityReport":
        """Merge another report into this one, de-duplicating issue codes."""
        self.metrics.update(other.metrics)
        for issue in other.warnings:
            self.add_warning(
                issue.code, message=issue.message, metric=issue.metric, threshold=issue.threshold
            )
        for issue in other.rejections:
            self.add_rejection(
                issue.code, message=issue.message, metric=issue.metric, threshold=issue.threshold
            )
        return self


@dataclass(frozen=True)
class LeafSegmentationResult:
    found: bool
    mask: np.ndarray | None
    bbox: tuple[int, int, int, int] | None
    area_fraction: float
    fill_ratio: float
    used_full_frame_fallback: bool
    multiple_leaves: bool
    candidate_count: int
    method: str
    warnings: tuple[str, ...] = ()
    failure_reason: str | None = None


@dataclass(frozen=True)
class LesionSegmentationResult:
    mask: np.ndarray
    lesion_area_fraction: float
    lesion_count: int
    largest_lesion_fraction: float
    mean_lesion_area_fraction: float
    method: str
    warnings: tuple[str, ...] = ()
    # False when the estimate could not be calibrated (e.g. no healthy-green
    # tissue to compare against). The API must not present such a result as a
    # normal prediction; it downgrades to `uncertain` (PRD §11).
    reliable: bool = True
