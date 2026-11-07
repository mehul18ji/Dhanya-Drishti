"""Quality-check tests: rejects, warnings, and mask-only exposure logic."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.vision.config import load_quality_config
from app.vision.preprocessing import load_oriented_image, make_working_image
from app.vision.quality import (
    assess_basic_quality,
    assess_leaf_quality,
    assess_lesion_quality,
)
from app.vision.types import (
    LeafSegmentationResult,
    LesionSegmentationResult,
    QualityReport,
    WorkingImage,
)
from tests.vision_helpers import encode_png, leaf_on_background, textured_leaf


def _working(bgr: np.ndarray) -> WorkingImage:
    return make_working_image(load_oriented_image(encode_png(bgr)), 768)


def _leaf(mask: np.ndarray, *, fill_ratio: float = 0.95, fallback: bool = False,
          multiple: bool = False) -> LeafSegmentationResult:
    ys, xs = np.nonzero(mask)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
            int(ys.max() - ys.min() + 1))
    return LeafSegmentationResult(
        found=True,
        mask=mask,
        bbox=bbox,
        area_fraction=float((mask > 0).mean()),
        fill_ratio=fill_ratio,
        used_full_frame_fallback=fallback,
        multiple_leaves=multiple,
        candidate_count=2 if multiple else 1,
        method="test",
    )


def test_tiny_image_is_rejected() -> None:
    image = np.full((50, 50, 3), 200, dtype=np.uint8)
    report = assess_basic_quality(_working(image), load_quality_config())
    assert any(issue.code == "VERY_SMALL_IMAGE" for issue in report.rejections)
    assert not report.passed


def test_dark_image_is_rejected() -> None:
    image = np.full((400, 400, 3), 20, dtype=np.uint8)
    report = assess_basic_quality(_working(image), load_quality_config())
    assert any(issue.code == "VERY_DARK_IMAGE" for issue in report.rejections)


def test_uniform_image_has_low_contrast() -> None:
    image = np.full((400, 400, 3), 128, dtype=np.uint8)
    report = assess_basic_quality(_working(image), load_quality_config())
    codes = {issue.code for issue in report.rejections}
    assert "LOW_CONTRAST" in codes


def test_blurred_noise_warns_or_rejects_for_blur() -> None:
    rng = np.random.default_rng(5)
    noise = rng.integers(60, 200, size=(400, 400, 3), dtype=np.uint8)
    blurred = cv2.GaussianBlur(noise, (31, 31), 0)
    report = assess_basic_quality(_working(blurred), load_quality_config())
    codes = {issue.code for issue in report.warnings + report.rejections}
    assert "BLURRY_IMAGE" in codes or "VERY_BLURRY_IMAGE" in codes


def test_normal_leaf_image_is_not_rejected() -> None:
    report = assess_basic_quality(_working(textured_leaf()), load_quality_config())
    assert report.passed, [issue.code for issue in report.rejections]


def test_overexposure_is_judged_inside_the_leaf_only() -> None:
    # Bright white paper background + a dark leaf. Global exposure is high,
    # but the leaf pixels are not over-exposed.
    image, mask = leaf_on_background(
        640, 360, background=252, leaf_color=(40, 90, 50)
    )
    working = _working(image)
    config = load_quality_config()

    report = assess_basic_quality(working, config)
    assert report.metrics["global_overexposed_fraction"] > 0.4

    assess_leaf_quality(working, _leaf(mask), report, config)
    assert report.metrics["leaf_overexposed_fraction"] == pytest.approx(0.0)
    assert "LEAF_OVEREXPOSED" not in {issue.code for issue in report.warnings}


def test_leaf_overexposure_is_rejected_when_it_is_real() -> None:
    image = np.full((400, 400, 3), 250, dtype=np.uint8)
    mask = np.full((400, 400), 255, dtype=np.uint8)
    working = _working(image)
    report = _clean_report()

    assess_leaf_quality(working, _leaf(mask), report, load_quality_config())
    assert any(issue.code == "LEAF_OVEREXPOSED" for issue in report.rejections)


def _clean_report() -> QualityReport:
    report = QualityReport(config_version="quality-v1")
    report.metrics.update({"mean_brightness": 128.0, "contrast_std": 40.0})
    return report


def test_tiny_leaf_region_is_rejected() -> None:
    image, _ = leaf_on_background(400, 400)
    mask = np.zeros((400, 400), dtype=np.uint8)
    mask[200:206, 200:206] = 255
    report = _clean_report()

    assess_leaf_quality(_working(image), _leaf(mask), report, load_quality_config())
    assert any(issue.code == "LEAF_TOO_SMALL" for issue in report.rejections)


def test_fallback_multi_leaf_and_weak_mask_warnings() -> None:
    image, mask = leaf_on_background(400, 300)
    report = _clean_report()
    leaf = _leaf(mask, fill_ratio=0.2, fallback=True, multiple=True)

    assess_leaf_quality(_working(image), leaf, report, load_quality_config())
    codes = {issue.code for issue in report.warnings}
    assert {"FULL_FRAME_FALLBACK", "MULTIPLE_LEAVES", "WEAK_LEAF_MASK"} <= codes


def test_implausible_lesion_fraction_warns_but_does_not_reject() -> None:
    mask = np.full((512, 512), 255, dtype=np.uint8)
    lesion = LesionSegmentationResult(
        mask=mask,
        lesion_area_fraction=0.80,
        lesion_count=1,
        largest_lesion_fraction=0.80,
        mean_lesion_area_fraction=0.80,
        method="test",
    )
    report = _clean_report()
    assess_lesion_quality(lesion, report, load_quality_config())

    assert report.passed
    assert any(issue.code == "WEAK_LESION_MASK" for issue in report.warnings)


def test_issues_are_deduplicated_when_merging() -> None:
    first = QualityReport()
    first.add_warning("BLURRY_IMAGE")
    second = QualityReport()
    second.add_warning("BLURRY_IMAGE")
    second.add_rejection("LEAF_TOO_SMALL")

    first.merge(second)
    assert [issue.code for issue in first.warnings].count("BLURRY_IMAGE") == 1
    assert len(first.rejections) == 1
