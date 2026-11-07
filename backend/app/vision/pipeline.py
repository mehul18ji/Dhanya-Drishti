"""One composition of the Phase 2 computer-vision stages (PRD §8, §9).

The audit script (`scripts/run_segmentation_audit.py`) and the Phase 4 API service
must run **the same** sequence: decode → working image → basic quality → leaf
segmentation → leaf quality → leaf crop/letterbox → lesion segmentation →
lesion quality. Keeping it here means calibration numbers measured by the audit
are the numbers the API will produce.

This module is deliberately transport-agnostic: it never touches the filesystem
except to read the image, never persists anything and imports no web framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

import numpy as np

from app.vision.config import (
    QualityConfig,
    SegmentationConfig,
    load_quality_config,
    load_segmentation_config,
)
from app.vision.leaf_segmentation import segment_leaf
from app.vision.lesion_segmentation import segment_lesions
from app.vision.preprocessing import (
    load_oriented_image,
    make_working_image,
    prepare_processing_canvas,
)
from app.vision.quality import (
    assess_basic_quality,
    assess_leaf_quality,
    assess_lesion_quality,
)
from app.vision.types import (
    CanvasTransform,
    LeafSegmentationResult,
    LesionSegmentationResult,
    OrientedImage,
    QualityReport,
    WorkingImage,
)


@dataclass(frozen=True)
class SegmentationPipelineResult:
    """Everything one image produced, including the versioned configuration used."""

    oriented: OrientedImage
    working: WorkingImage
    leaf: LeafSegmentationResult
    quality: QualityReport
    canvas_bgr: np.ndarray | None = None
    canvas_leaf_mask: np.ndarray | None = None
    lesion: LesionSegmentationResult | None = None
    transform: CanvasTransform | None = None
    stage_ms: dict[str, float] = field(default_factory=dict)
    segmentation_config_version: str = ""
    segmentation_config_sha256: str = ""
    quality_config_version: str = ""
    quality_config_sha256: str = ""

    @property
    def rejected(self) -> bool:
        """A rejection means the pipeline refuses to classify this image."""
        return bool(self.quality.rejections)

    @property
    def uncertain(self) -> bool:
        """A non-rejected image with warnings must not be shown as a confident result."""
        return not self.rejected and bool(self.quality.warnings)

    @property
    def lesion_area_percentage(self) -> float | None:
        if self.lesion is None:
            return None
        return self.lesion.lesion_area_fraction * 100.0


def run_segmentation(
    source: str | Path | bytes,
    *,
    segmentation_config: SegmentationConfig | None = None,
    quality_config: QualityConfig | None = None,
) -> SegmentationPipelineResult:
    """Run the full deterministic pipeline on one image.

    ``ImageDecodeError`` propagates from preprocessing: an unreadable file is an
    upload failure, not a segmentation result. Every other failure is reported
    through ``quality.rejections`` / ``leaf.found`` so the caller can classify
    the outcome honestly.
    """
    segmentation = segmentation_config or load_segmentation_config()
    quality = quality_config or load_quality_config()
    stage_ms: dict[str, float] = {}

    start = perf_counter()
    oriented = load_oriented_image(source)
    working = make_working_image(oriented, segmentation.preprocessing.working_long_side)
    stage_ms["decode_and_working"] = round((perf_counter() - start) * 1000.0, 2)

    start = perf_counter()
    report = assess_basic_quality(working, quality)
    stage_ms["basic_quality"] = round((perf_counter() - start) * 1000.0, 2)

    start = perf_counter()
    leaf = segment_leaf(working.bgr, segmentation)
    stage_ms["leaf_segmentation"] = round((perf_counter() - start) * 1000.0, 2)

    start = perf_counter()
    assess_leaf_quality(working, leaf, report, quality)
    stage_ms["leaf_quality"] = round((perf_counter() - start) * 1000.0, 2)

    canvas_bgr: np.ndarray | None = None
    canvas_leaf_mask: np.ndarray | None = None
    transform: CanvasTransform | None = None
    lesion: LesionSegmentationResult | None = None

    # Without a leaf mask there is nothing to analyse; the rejection code was
    # already recorded by `assess_leaf_quality`.
    if leaf.found and leaf.mask is not None and leaf.bbox is not None:
        start = perf_counter()
        canvas_bgr, canvas_leaf_mask, transform = prepare_processing_canvas(
            working, leaf.mask, leaf.bbox, segmentation.preprocessing
        )
        stage_ms["canvas"] = round((perf_counter() - start) * 1000.0, 2)

        start = perf_counter()
        lesion = segment_lesions(canvas_bgr, canvas_leaf_mask, segmentation)
        stage_ms["lesion_segmentation"] = round((perf_counter() - start) * 1000.0, 2)

        start = perf_counter()
        assess_lesion_quality(lesion, report, quality)
        # Warnings raised by the lesion stage (e.g. an unusable healthy reference)
        # belong in the same report so the API can downgrade the result.
        for code in lesion.warnings:
            report.add_warning(code)
        stage_ms["lesion_quality"] = round((perf_counter() - start) * 1000.0, 2)

    stage_ms["total"] = round(sum(value for value in stage_ms.values()), 2)

    return SegmentationPipelineResult(
        oriented=oriented,
        working=working,
        leaf=leaf,
        quality=report,
        canvas_bgr=canvas_bgr,
        canvas_leaf_mask=canvas_leaf_mask,
        lesion=lesion,
        transform=transform,
        stage_ms=stage_ms,
        segmentation_config_version=segmentation.segmentation_config_version,
        segmentation_config_sha256=segmentation.content_sha256,
        quality_config_version=quality.quality_config_version,
        quality_config_sha256=quality.content_sha256,
    )
