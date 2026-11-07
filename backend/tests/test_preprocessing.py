"""Preprocessing tests: EXIF, aspect preservation, letterbox, transform mapping."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.vision.config import load_segmentation_config
from app.vision.preprocessing import (
    ImageDecodeError,
    crop_with_margin,
    denoise_image,
    letterbox,
    load_oriented_image,
    make_working_image,
    prepare_processing_canvas,
    resize_preserving_aspect,
)
from app.vision.types import OrientedImage, WorkingImage
from tests.vision_helpers import encode_png, leaf_on_background


def _oriented_from_bgr(bgr: np.ndarray) -> OrientedImage:
    return load_oriented_image(encode_png(bgr))


def test_exif_orientation_three_is_applied(tmp_path: Path) -> None:
    bgr = np.zeros((80, 120, 3), dtype=np.uint8)
    bgr[:, :60] = (0, 0, 255)    # red in BGR
    bgr[:, 60:] = (255, 0, 0)    # blue in BGR

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    exif = pil.getexif()
    exif[274] = 3  # 180-degree rotation
    path = tmp_path / "rotated.jpg"
    pil.save(path, exif=exif, quality=95)

    loaded = load_oriented_image(path)
    assert loaded.exif_orientation == 3
    assert (loaded.width, loaded.height) == (120, 80)

    left = loaded.bgr[:, :20].reshape(-1, 3).mean(axis=0)
    right = loaded.bgr[:, -20:].reshape(-1, 3).mean(axis=0)
    # After 180 degrees the blue half is on the left.
    assert left[0] > 150 and left[2] < 100
    assert right[2] > 150 and right[0] < 100


def test_orientation_six_swaps_dimensions(tmp_path: Path) -> None:
    bgr = np.full((80, 120, 3), 200, dtype=np.uint8)
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    exif = pil.getexif()
    exif[274] = 6  # 90-degree rotation
    path = tmp_path / "rotated6.jpg"
    pil.save(path, exif=exif, quality=95)

    loaded = load_oriented_image(path)
    assert loaded.exif_orientation == 6
    assert (loaded.width, loaded.height) == (80, 120)


def test_unsupported_and_corrupt_bytes_are_rejected() -> None:
    bmp = np.full((20, 20, 3), 128, dtype=np.uint8)
    ok, buffer = cv2.imencode(".bmp", bmp)
    assert ok
    with pytest.raises(ImageDecodeError):
        load_oriented_image(buffer.tobytes())

    with pytest.raises(ImageDecodeError):
        load_oriented_image(b"definitely not an image")


def test_resize_preserves_aspect_and_never_upscales() -> None:
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    resized, scale_x, scale_y = resize_preserving_aspect(image, 200)

    assert resized.shape[:2] == (100, 200)
    assert scale_x == pytest.approx(0.5)
    assert scale_y == pytest.approx(0.5)

    small = np.zeros((50, 100, 3), dtype=np.uint8)
    untouched, scale_x, scale_y = resize_preserving_aspect(small, 200)
    assert untouched.shape[:2] == (50, 100)
    assert (scale_x, scale_y) == (1.0, 1.0)


def test_letterbox_is_symmetric_and_never_crops() -> None:
    image = np.full((200, 400, 3), 200, dtype=np.uint8)
    result = letterbox(image, canvas_size=100, pad_value=7)

    assert result.image.shape == (100, 100, 3)
    assert (result.resized_width, result.resized_height) == (100, 50)
    assert (result.pad_left, result.pad_top) == (0, 25)
    assert np.all(result.image[:25] == 7)
    assert np.all(result.image[-25:] == 7)
    assert np.all(result.image[50, :] == 200)


def test_crop_margin_is_clamped_to_image() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    crop, box = crop_with_margin(image, (0, 0, 20, 20), margin_fraction=0.5)
    assert box == (0, 0, 30, 30)
    assert crop.shape[:2] == (30, 30)


def test_canvas_transform_maps_points_and_masks_back() -> None:
    image, mask = leaf_on_background(640, 360)
    oriented = _oriented_from_bgr(image)
    working = make_working_image(oriented, 768)
    bbox = cv2.boundingRect(mask)

    config = load_segmentation_config()
    canvas, canvas_mask, transform = prepare_processing_canvas(
        working, mask, bbox, config.preprocessing
    )

    assert canvas.shape == (512, 512, 3)
    assert canvas_mask.shape == (512, 512)
    assert canvas_mask.sum() > 0

    top_left = transform.canvas_to_working(
        np.array([[transform.pad_left, transform.pad_top]], dtype=np.float64)
    )
    # Padding starts exactly at the crop origin.
    assert top_left[0, 0] == pytest.approx(transform.crop_box[0], abs=1e-6)
    assert top_left[0, 1] == pytest.approx(transform.crop_box[1], abs=1e-6)

    mapped = transform.canvas_mask_to_source(canvas_mask)
    assert mapped.shape == mask.shape
    assert (mapped > 0).sum() > 0
    # The mapped mask should overlap the source leaf substantially.
    overlap = np.logical_and(mapped > 0, mask > 0).sum()
    assert overlap / max(1, (mask > 0).sum()) > 0.90


@pytest.mark.parametrize(
    ("width", "height"),
    [(640, 360), (360, 640), (400, 400), (500, 100), (100, 500)],
)
def test_aspect_ratio_is_preserved_through_the_pipeline(width: int, height: int) -> None:
    leaf_w = max(20, int(width * 0.6))
    leaf_h = max(12, int(height * 0.5))
    x = (width - leaf_w) // 2
    y = (height - leaf_h) // 2
    image, mask = leaf_on_background(width, height, leaf_box=(x, y, leaf_w, leaf_h))

    oriented = _oriented_from_bgr(image)
    working = make_working_image(oriented, 768)
    config = load_segmentation_config()
    _, canvas_mask, transform = prepare_processing_canvas(
        working, mask, (x, y, leaf_w, leaf_h), config.preprocessing
    )

    y_coords, x_coords = np.nonzero(canvas_mask)
    canvas_aspect = (x_coords.max() - x_coords.min() + 1) / (
        y_coords.max() - y_coords.min() + 1
    )
    source_aspect = leaf_w / leaf_h

    relative_error = abs(canvas_aspect / source_aspect - 1.0)
    assert relative_error < 0.01, f"aspect changed by {relative_error:.4%}"

    scale_error = abs(transform.resize_scale_x - transform.resize_scale_y) / max(
        transform.resize_scale_x, transform.resize_scale_y
    )
    assert scale_error < 0.01


def test_denoise_modes() -> None:
    rng = np.random.default_rng(11)
    image = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    config = load_segmentation_config().preprocessing.denoise

    copied = denoise_image(image, config.model_copy(update={"method": "none"}))
    assert np.array_equal(copied, image)
    assert copied is not image

    filtered = denoise_image(image, config)
    assert filtered.shape == image.shape
    assert not np.array_equal(filtered, image)

    with pytest.raises(ValueError):
        bad = config.model_copy(update={"method": "unknown"})
        denoise_image(image, bad)


def test_working_image_scales_large_inputs() -> None:
    image = np.zeros((2000, 4000, 3), dtype=np.uint8)
    oriented = _oriented_from_bgr(image)
    working = make_working_image(oriented, 768)

    assert max(working.bgr.shape[:2]) == 768
    assert working.source_width == 4000
    assert working.source_height == 2000
    assert working.scale_x == pytest.approx(768 / 4000)
