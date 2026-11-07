"""Image-quality assessment for the classical pipeline (PRD §8, §9).

Quality problems are split into two lists:

- ``rejections``: analysis must stop (too small, unreadable, no leaf, ...)
- ``warnings``: analysis continues but the user must be told

Exposure is judged **inside the leaf mask** (decision E-19): the dataset's white
paper background dominates global exposure statistics and would otherwise
produce false over-exposure warnings.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.vision.config import QualityConfig
from app.vision.types import (
    LeafSegmentationResult,
    LesionSegmentationResult,
    QualityReport,
    WorkingImage,
)


def _hsv(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2HSV)


def assess_basic_quality(working: WorkingImage, config: QualityConfig) -> QualityReport:
    """Checks that do not need a leaf mask: dimensions, brightness, blur."""
    report = QualityReport(config_version=config.quality_config_version)

    height = working.source_height
    width = working.source_width
    short_side = min(height, width)
    total_pixels = height * width

    hsv = _hsv(working.bgr)
    value = hsv[:, :, 2]
    mean_brightness = float(value.mean())
    contrast_std = float(value.std())
    global_overexposed = float((value >= 245).mean())

    gray = cv2.cvtColor(working.bgr, cv2.COLOR_BGR2GRAY)
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    report.metrics.update(
        {
            "width": width,
            "height": height,
            "short_side": short_side,
            "total_pixels": total_pixels,
            "mean_brightness": round(mean_brightness, 3),
            "contrast_std": round(contrast_std, 3),
            "laplacian_variance": round(laplacian_variance, 3),
            "global_overexposed_fraction": round(global_overexposed, 6),
        }
    )

    dims = config.dimensions
    if short_side < dims.hard_reject_short_side_px or total_pixels < dims.hard_reject_total_pixels:
        report.add_rejection(
            "VERY_SMALL_IMAGE",
            metric=short_side,
            threshold=dims.hard_reject_short_side_px,
        )
    elif short_side < dims.soft_warn_short_side_px or total_pixels < dims.soft_warn_total_pixels:
        report.add_warning(
            "SMALL_IMAGE",
            metric=short_side,
            threshold=dims.soft_warn_short_side_px,
        )

    brightness = config.brightness
    if mean_brightness < brightness.hard_reject_mean_v_below:
        report.add_rejection(
            "VERY_DARK_IMAGE",
            metric=round(mean_brightness, 3),
            threshold=brightness.hard_reject_mean_v_below,
        )
    elif mean_brightness < brightness.warn_mean_v_below:
        report.add_warning(
            "DARK_IMAGE",
            metric=round(mean_brightness, 3),
            threshold=brightness.warn_mean_v_below,
        )

    if mean_brightness > brightness.hard_reject_mean_v_above:
        report.add_rejection(
            "OVEREXPOSED_IMAGE",
            metric=round(mean_brightness, 3),
            threshold=brightness.hard_reject_mean_v_above,
        )
    elif mean_brightness > brightness.warn_mean_v_above:
        report.add_warning(
            "BRIGHT_IMAGE",
            metric=round(mean_brightness, 3),
            threshold=brightness.warn_mean_v_above,
        )

    contrast = config.contrast
    if contrast_std < contrast.hard_reject_std_v_below:
        report.add_rejection(
            "LOW_CONTRAST",
            metric=round(contrast_std, 3),
            threshold=contrast.hard_reject_std_v_below,
        )
    elif contrast_std < contrast.warn_std_v_below:
        report.add_warning(
            "LOW_CONTRAST",
            metric=round(contrast_std, 3),
            threshold=contrast.warn_std_v_below,
        )

    blur = config.blur
    if laplacian_variance < blur.hard_reject_laplacian_variance_below:
        report.add_rejection(
            "VERY_BLURRY_IMAGE",
            metric=round(laplacian_variance, 3),
            threshold=blur.hard_reject_laplacian_variance_below,
        )
    elif laplacian_variance < blur.warn_laplacian_variance_below:
        report.add_warning(
            "BLURRY_IMAGE",
            metric=round(laplacian_variance, 3),
            threshold=blur.warn_laplacian_variance_below,
        )

    return report


def assess_leaf_quality(
    working: WorkingImage,
    leaf: LeafSegmentationResult,
    report: QualityReport,
    config: QualityConfig,
) -> QualityReport:
    """Mask-dependent checks, including exposure inside the leaf."""
    if not leaf.found or leaf.mask is None:
        report.add_rejection("NO_CLEAR_LEAF_FOUND")
        return report

    mask = leaf.mask > 0
    leaf_pixels = int(mask.sum())
    total_pixels = int(mask.size)
    leaf_area_fraction = leaf_pixels / total_pixels if total_pixels else 0.0

    report.metrics.update(
        {
            "leaf_area_fraction": round(leaf_area_fraction, 6),
            "leaf_fill_ratio": round(leaf.fill_ratio, 6),
            "leaf_candidate_count": leaf.candidate_count,
            "leaf_full_frame_fallback": int(leaf.used_full_frame_fallback),
            "leaf_multiple": int(leaf.multiple_leaves),
        }
    )

    leaf_limits = config.leaf
    if leaf_area_fraction < leaf_limits.hard_reject_area_fraction_below:
        report.add_rejection(
            "LEAF_TOO_SMALL",
            metric=round(leaf_area_fraction, 6),
            threshold=leaf_limits.hard_reject_area_fraction_below,
        )
    elif leaf_area_fraction < leaf_limits.warn_area_fraction_below:
        report.add_warning(
            "SMALL_LEAF_REGION",
            metric=round(leaf_area_fraction, 6),
            threshold=leaf_limits.warn_area_fraction_below,
        )

    if leaf.used_full_frame_fallback and leaf_limits.warn_full_frame_fallback:
        report.add_warning("FULL_FRAME_FALLBACK")
    if leaf.multiple_leaves and leaf_limits.warn_multi_leaf:
        report.add_warning("MULTIPLE_LEAVES")
    if leaf.fill_ratio < leaf_limits.warn_weak_fill_ratio_below:
        report.add_warning(
            "WEAK_LEAF_MASK",
            metric=round(leaf.fill_ratio, 6),
            threshold=leaf_limits.warn_weak_fill_ratio_below,
        )

    hsv = _hsv(working.bgr)
    value = hsv[:, :, 2][mask]
    if value.size:
        exposure = config.exposure
        over = float((value >= exposure.leaf_overexposed_v_above).mean())
        under = float((value < exposure.underexposed_v_below).mean())
        report.metrics["leaf_overexposed_fraction"] = round(over, 6)
        report.metrics["leaf_underexposed_fraction"] = round(under, 6)

        if over > exposure.hard_reject_leaf_overexposed_fraction_above:
            report.add_rejection(
                "LEAF_OVEREXPOSED",
                metric=round(over, 6),
                threshold=exposure.hard_reject_leaf_overexposed_fraction_above,
            )
        elif over > exposure.warn_leaf_overexposed_fraction_above:
            report.add_warning(
                "LEAF_OVEREXPOSED",
                metric=round(over, 6),
                threshold=exposure.warn_leaf_overexposed_fraction_above,
            )

        if under > exposure.warn_leaf_underexposed_fraction_above:
            report.add_warning(
                "LEAF_UNDEREXPOSED",
                metric=round(under, 6),
                threshold=exposure.warn_leaf_underexposed_fraction_above,
            )

    return report


def assess_lesion_quality(
    lesion: LesionSegmentationResult,
    report: QualityReport,
    config: QualityConfig,
) -> QualityReport:
    """Flag implausibly large lesion masks; never reject on this alone."""
    report.metrics["lesion_area_fraction"] = round(lesion.lesion_area_fraction, 6)
    report.metrics["lesion_area_percentage"] = round(lesion.lesion_area_fraction * 100, 3)
    report.metrics["lesion_count"] = lesion.lesion_count

    threshold = config.segmentation.warn_lesion_fraction_above
    if lesion.lesion_area_fraction > threshold:
        report.add_warning(
            "WEAK_LESION_MASK",
            metric=round(lesion.lesion_area_fraction, 6),
            threshold=threshold,
        )
    return report
