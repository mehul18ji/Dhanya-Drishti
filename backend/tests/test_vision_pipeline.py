"""Pipeline-composition tests: one call composes the Phase 2 stages honestly."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.vision.config import load_quality_config, load_segmentation_config
from app.vision.pipeline import run_segmentation
from app.vision.preprocessing import ImageDecodeError
from tests.vision_helpers import encode_png, leaf_with_spots, textured_leaf


def test_pipeline_reports_leaf_lesion_and_config_versions() -> None:
    image, leaf_mask, _ = leaf_with_spots(480, 240)
    result = run_segmentation(encode_png(image))

    assert result.rejected is False
    assert result.leaf.found is True
    assert result.leaf.mask is not None
    assert result.canvas_bgr is not None
    assert result.canvas_leaf_mask is not None
    assert result.transform is not None
    assert result.lesion is not None

    # The lesion stage runs on the canvas and never escapes the leaf mask.
    outside = np.logical_and(result.lesion.mask > 0, result.canvas_leaf_mask == 0)
    assert int(outside.sum()) == 0

    assert result.segmentation_config_version == "seg-v2"
    assert result.quality_config_version == "quality-v1"
    assert len(result.segmentation_config_sha256) == 64
    assert len(result.quality_config_sha256) == 64

    for stage in ("decode_and_working", "basic_quality", "leaf_segmentation", "lesion_segmentation"):
        assert stage in result.stage_ms
        assert result.stage_ms[stage] >= 0.0
    assert result.stage_ms["total"] >= result.stage_ms["leaf_segmentation"]

    assert result.lesion_area_percentage is not None
    assert 0.0 < result.lesion_area_percentage < 100.0


def test_non_leaf_image_is_rejected_without_lesion_stage() -> None:
    image = np.full((400, 400, 3), 250, dtype=np.uint8)
    for offset in range(60, 320, 40):
        cv2.rectangle(image, (80, offset), (320, offset + 10), (0, 0, 0), -1)

    result = run_segmentation(encode_png(image))

    assert result.rejected is True
    assert result.uncertain is False
    assert result.leaf.found is False
    assert result.lesion is None
    assert result.canvas_bgr is None
    assert result.lesion_area_percentage is None
    assert "NO_CLEAR_LEAF_FOUND" in {issue.code for issue in result.quality.rejections}
    assert "lesion_segmentation" not in result.stage_ms


def test_dark_image_is_rejected_even_when_a_leaf_is_visible() -> None:
    image, _, _ = leaf_with_spots(400, 200)
    dark = (image.astype(np.float32) * 0.06).astype(np.uint8)

    result = run_segmentation(encode_png(dark))

    assert result.rejected is True
    assert any(
        issue.code in {"VERY_DARK_IMAGE", "LOW_CONTRAST"}
        for issue in result.quality.rejections
    )


def test_decode_failure_propagates_as_an_upload_error() -> None:
    with pytest.raises(ImageDecodeError):
        run_segmentation(b"this is not an image")


def test_bytes_and_path_inputs_agree(tmp_path: Path) -> None:
    image, _, _ = leaf_with_spots(480, 240)
    payload = encode_png(image)
    path = tmp_path / "leaf.png"
    path.write_bytes(payload)

    from_bytes = run_segmentation(payload)
    from_path = run_segmentation(path)

    assert np.array_equal(from_bytes.leaf.mask, from_path.leaf.mask)
    assert from_bytes.lesion is not None and from_path.lesion is not None
    assert np.array_equal(from_bytes.lesion.mask, from_path.lesion.mask)


def test_pipeline_is_deterministic() -> None:
    image = textured_leaf(640, 360)
    payload = encode_png(image)

    first = run_segmentation(payload)
    second = run_segmentation(payload)

    assert first.leaf.found == second.leaf.found
    assert np.array_equal(first.leaf.mask, second.leaf.mask)
    assert first.lesion is not None and second.lesion is not None
    assert np.array_equal(first.lesion.mask, second.lesion.mask)
    assert first.lesion.lesion_area_fraction == second.lesion.lesion_area_fraction


def test_uncertain_reflects_warnings_not_rejections() -> None:
    # A pure close-up has no background, so the documented full-frame fallback
    # applies and the result must be flagged uncertain rather than confident.
    image = np.full((400, 400, 3), (60, 140, 70), dtype=np.uint8)
    rng = np.random.default_rng(3)
    image = np.clip(
        image.astype(np.int16) + rng.integers(-10, 11, image.shape), 0, 255
    ).astype(np.uint8)

    result = run_segmentation(encode_png(image))

    assert result.leaf.used_full_frame_fallback is True
    assert result.rejected is False
    assert any(issue.code == "FULL_FRAME_FALLBACK" for issue in result.quality.warnings)
    assert result.uncertain is True


def test_explicit_configs_are_honoured(tmp_path: Path) -> None:
    segmentation = load_segmentation_config()
    quality = load_quality_config()
    image, _, _ = leaf_with_spots(480, 240)

    result = run_segmentation(
        encode_png(image), segmentation_config=segmentation, quality_config=quality
    )
    assert result.segmentation_config_sha256 == segmentation.content_sha256
    assert result.quality_config_sha256 == quality.content_sha256
