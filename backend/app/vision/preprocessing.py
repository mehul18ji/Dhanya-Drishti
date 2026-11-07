"""Deterministic, aspect-ratio-preserving preprocessing (PRD §8).

The pipeline never stretches an image. Every resize is a uniform scale; any
square canvas is produced by symmetric letterbox padding, and the returned
``CanvasTransform`` maps canvas coordinates/masks back to the original image.

Only the CV-relevant steps live here: decode + EXIF orientation, working
downscale, margin crop, letterbox, denoise. Nothing persists to disk.
"""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.vision.config import DenoiseSettings, PreprocessingSettings
from app.vision.types import (
    CanvasTransform,
    LetterboxResult,
    OrientedImage,
    WorkingImage,
)

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageDecodeError(ValueError):
    """The bytes are not a supported, decodable image."""


def _decode_pillow(image: Image.Image, source_path: str | None) -> OrientedImage:
    source_format = (image.format or "").upper()
    if source_format == "JPG":
        source_format = "JPEG"
    if source_format not in ALLOWED_FORMATS:
        raise ImageDecodeError(
            f"Unsupported image format {source_format or 'unknown'}; "
            f"allowed: {', '.join(sorted(ALLOWED_FORMATS))}"
        )

    exif = image.getexif()
    orientation = int(exif.get(274, 1) or 1)
    rgb = ImageOps.exif_transpose(image).convert("RGB")
    bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    height, width = bgr.shape[:2]
    return OrientedImage(
        bgr=bgr,
        width=width,
        height=height,
        source_format=source_format,
        exif_orientation=orientation,
        source_path=source_path,
    )


def load_oriented_image(source: str | Path | bytes) -> OrientedImage:
    """Decode an uploaded image and apply EXIF orientation (PRD §9 Stage A)."""
    try:
        if isinstance(source, (bytes, bytearray)):
            with Image.open(io.BytesIO(bytes(source))) as image:
                return _decode_pillow(image, source_path=None)
        path = Path(source)
        with Image.open(path) as image:
            return _decode_pillow(image, source_path=str(path))
    except UnidentifiedImageError as exc:
        raise ImageDecodeError("The file is not a recognised image.") from exc
    except (OSError, ValueError) as exc:
        if isinstance(exc, ImageDecodeError):
            raise
        raise ImageDecodeError(f"The image could not be decoded: {exc}") from exc


def resize_preserving_aspect(
    image: np.ndarray, long_side: int
) -> tuple[np.ndarray, float, float]:
    """Uniformly downscale so the longest side is at most ``long_side``.

    Returns ``(resized, scale_x, scale_y)``. Upscaling never happens here.
    """
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= long_side:
        return image.copy(), 1.0, 1.0

    if width >= height:
        new_width = long_side
        new_height = max(1, int(round(height * long_side / width)))
    else:
        new_height = long_side
        new_width = max(1, int(round(width * long_side / height)))

    resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
    return resized, new_width / width, new_height / height


def make_working_image(oriented: OrientedImage, long_side: int) -> WorkingImage:
    """Create the aspect-preserving detection/preview image."""
    resized, scale_x, scale_y = resize_preserving_aspect(oriented.bgr, long_side)
    return WorkingImage(
        bgr=resized,
        scale_x=scale_x,
        scale_y=scale_y,
        source_width=oriented.width,
        source_height=oriented.height,
    )


def _fit_and_pad(
    image: np.ndarray,
    canvas_size: int,
    pad_value: int,
) -> tuple[np.ndarray, int, int, int, int, float, float]:
    height, width = image.shape[:2]
    scale = min(canvas_size / width, canvas_size / height)
    resized_width = min(canvas_size, max(1, int(round(width * scale))))
    resized_height = min(canvas_size, max(1, int(round(height * scale))))

    if (resized_width, resized_height) == (width, height):
        resized = image.copy()
    else:
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized = cv2.resize(image, (resized_width, resized_height), interpolation=interpolation)

    pad_left = (canvas_size - resized_width) // 2
    pad_top = (canvas_size - resized_height) // 2

    channels = image.shape[2:]
    canvas = np.full(
        (canvas_size, canvas_size, *channels),
        pad_value,
        dtype=image.dtype,
    )
    canvas[
        pad_top : pad_top + resized_height,
        pad_left : pad_left + resized_width,
    ] = resized

    return (
        canvas,
        resized_width,
        resized_height,
        pad_left,
        pad_top,
        resized_width / width,
        resized_height / height,
    )


def letterbox(image: np.ndarray, canvas_size: int, pad_value: int = 0) -> LetterboxResult:
    """Scale uniformly and pad symmetrically into a square canvas."""
    canvas, resized_width, resized_height, pad_left, pad_top, scale_x, scale_y = _fit_and_pad(
        image, canvas_size, pad_value
    )
    return LetterboxResult(
        image=canvas,
        resized_width=resized_width,
        resized_height=resized_height,
        pad_left=pad_left,
        pad_top=pad_top,
        scale_x=scale_x,
        scale_y=scale_y,
    )


def crop_with_margin(
    image: np.ndarray,
    bbox: tuple[int, int, int, int],
    margin_fraction: float,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Crop a bbox with a safety margin so edge lesions are not clipped."""
    x, y, width, height = bbox
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid bbox: {bbox}")

    image_height, image_width = image.shape[:2]
    margin = int(round(margin_fraction * max(width, height)))

    x0 = max(0, x - margin)
    y0 = max(0, y - margin)
    x1 = min(image_width, x + width + margin)
    y1 = min(image_height, y + height + margin)

    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"bbox {bbox} lies outside the image")

    return image[y0:y1, x0:x1].copy(), (x0, y0, x1 - x0, y1 - y0)


def denoise_image(image: np.ndarray, settings: DenoiseSettings) -> np.ndarray:
    """Apply the configured denoiser; never returns an in-place modification."""
    if settings.method == "none":
        return image.copy()
    if settings.method == "bilateral":
        return cv2.bilateralFilter(
            image,
            settings.bilateral_diameter,
            settings.bilateral_sigma_color,
            settings.bilateral_sigma_space,
        )
    if settings.method == "fast_nlmeans":
        if image.ndim == 3:
            return cv2.fastNlMeansDenoisingColored(
                image,
                None,
                settings.nlmeans_h,
                settings.nlmeans_h,
                settings.nlmeans_template_window,
                settings.nlmeans_search_window,
            )
        return cv2.fastNlMeansDenoising(
            image,
            None,
            settings.nlmeans_h,
            settings.nlmeans_template_window,
            settings.nlmeans_search_window,
        )
    raise ValueError(f"unknown denoise method: {settings.method}")


def prepare_processing_canvas(
    working: WorkingImage,
    leaf_mask: np.ndarray,
    leaf_bbox: tuple[int, int, int, int],
    settings: PreprocessingSettings,
) -> tuple[np.ndarray, np.ndarray, CanvasTransform]:
    """Crop around the leaf, resize uniformly, denoise and letterbox.

    Returns ``(canvas_bgr, canvas_leaf_mask, transform)`` where the mask is
    already aligned to the canvas (255 inside the leaf, 0 in padding).
    """
    crop_bgr, crop_box = crop_with_margin(
        working.bgr, leaf_bbox, settings.crop_margin_fraction
    )
    crop_mask = leaf_mask[
        crop_box[1] : crop_box[1] + crop_box[3],
        crop_box[0] : crop_box[0] + crop_box[2],
    ]

    canvas_bgr, resized_width, resized_height, pad_left, pad_top, scale_x, scale_y = (
        _fit_and_pad(crop_bgr, settings.canvas_size, settings.pad_value)
    )
    padded_mask = np.zeros((settings.canvas_size, settings.canvas_size), dtype=np.uint8)

    resized_mask = cv2.resize(
        crop_mask,
        (resized_width, resized_height),
        interpolation=cv2.INTER_NEAREST,
    )
    padded_mask[
        pad_top : pad_top + resized_height,
        pad_left : pad_left + resized_width,
    ] = resized_mask

    resized_bgr = canvas_bgr[
        pad_top : pad_top + resized_height,
        pad_left : pad_left + resized_width,
    ]
    denoised = denoise_image(resized_bgr, settings.denoise)
    canvas_bgr[
        pad_top : pad_top + resized_height,
        pad_left : pad_left + resized_width,
    ] = denoised

    working_height, working_width = working.bgr.shape[:2]
    transform = CanvasTransform(
        source_width=working.source_width,
        source_height=working.source_height,
        working_width=working_width,
        working_height=working_height,
        working_scale_x=working.scale_x,
        working_scale_y=working.scale_y,
        crop_box=crop_box,
        resize_scale_x=scale_x,
        resize_scale_y=scale_y,
        resized_width=resized_width,
        resized_height=resized_height,
        pad_left=pad_left,
        pad_top=pad_top,
        canvas_size=settings.canvas_size,
    )

    return canvas_bgr, padded_mask, transform
