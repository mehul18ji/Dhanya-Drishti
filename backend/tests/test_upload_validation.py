"""Upload validation tests (Phase 4 M3).

Images are generated in memory with Pillow; nothing reads the dataset, the model or
the held-out rows.
"""

from __future__ import annotations

import asyncio
import io
import math
import sys
from pathlib import Path

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.exceptions import (  # noqa: E402
    FileTooLargeError,
    UnsupportedFileTypeError,
    UploadValidationError,
)
from app.services.upload_validation import (  # noqa: E402
    EXIF_ORIENTATION_TAG,
    read_and_validate,
    validate_upload,
)
from app.vision.config import load_quality_config  # noqa: E402


def _valid_size() -> tuple[int, int]:
    """A geometry comfortably inside the hard dimension limits."""
    limits = load_quality_config().dimensions
    short = max(limits.hard_reject_short_side_px, 64)
    side = max(short, int(math.ceil(math.sqrt(limits.hard_reject_total_pixels))))
    return (side + 16, side + 16)


def _image_bytes(
    fmt: str = "JPEG",
    *,
    size: tuple[int, int] | None = None,
    orientation: int | None = None,
) -> bytes:
    image = Image.new("RGB", size or _valid_size(), (110, 150, 80))
    buffer = io.BytesIO()
    save_kwargs: dict = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION_TAG] = orientation
        save_kwargs["exif"] = exif
    try:
        image.save(buffer, format=fmt, **save_kwargs)
    except (OSError, KeyError):  # pragma: no cover - depends on Pillow build
        pytest.skip(f"Pillow cannot encode {fmt} in this environment")
    return buffer.getvalue()


def test_accepts_jpeg_png_and_webp() -> None:
    for fmt, name in (("JPEG", "leaf.jpg"), ("PNG", "leaf.png"), ("WEBP", "leaf.webp")):
        result = validate_upload(name, _image_bytes(fmt))

        assert result.detected_format == fmt
        assert result.filename == name
        assert result.width >= 1 and result.height >= 1
        assert result.size_bytes == len(result.content)


def test_jpeg_extension_family_is_accepted() -> None:
    result = validate_upload("leaf.JPEG", _image_bytes("JPEG"))
    assert result.extension == ".jpeg"
    assert result.detected_format == "JPEG"


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(UploadValidationError, match="empty"):
        validate_upload("leaf.jpg", b"")


def test_oversized_upload_is_rejected() -> None:
    payload = _image_bytes("PNG")
    # A zero-megabyte limit makes any non-empty upload too large.
    with pytest.raises(FileTooLargeError, match="maximum allowed size"):
        validate_upload("leaf.png", payload, settings=Settings(max_upload_mb=0))


def test_disallowed_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("leaf.gif", _image_bytes("GIF"))
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("notes.txt", b"hello")


def test_unreadable_bytes_are_rejected() -> None:
    with pytest.raises(UploadValidationError, match="not a readable image"):
        validate_upload("leaf.png", b"this is definitely not a png")


def test_renamed_file_is_rejected_by_real_format_sniffing() -> None:
    """A PNG renamed to .jpg must not slip through as a JPEG."""
    with pytest.raises(UnsupportedFileTypeError, match="contents are PNG"):
        validate_upload("leaf.jpg", _image_bytes("PNG"))


def test_too_small_image_is_rejected() -> None:
    limits = load_quality_config().dimensions
    if limits.hard_reject_short_side_px <= 1:
        pytest.skip("no hard short-side limit configured")
    tiny = limits.hard_reject_short_side_px - 1

    with pytest.raises(UploadValidationError) as error:
        validate_upload("leaf.png", _image_bytes("PNG", size=(tiny, tiny)))

    assert error.value.reason_code == "IMAGE_TOO_SMALL"


def test_exif_orientation_is_recorded_not_silently_fixed() -> None:
    result = validate_upload("leaf.jpg", _image_bytes("JPEG", orientation=6))
    assert result.exif_orientation == 6

    plain = validate_upload("leaf.jpg", _image_bytes("JPEG"))
    assert plain.exif_orientation is None


def test_read_and_validate_streams_and_reports_size() -> None:
    payload = _image_bytes("PNG")
    upload = UploadFile(file=io.BytesIO(payload), filename="leaf.png")

    result = asyncio.run(read_and_validate(upload))

    assert result.detected_format == "PNG"
    assert result.size_bytes == len(payload)
    assert result.content == payload


def test_read_and_validate_stops_an_oversized_upload() -> None:
    payload = _image_bytes("PNG")
    upload = UploadFile(file=io.BytesIO(payload), filename="leaf.png")

    with pytest.raises(FileTooLargeError):
        asyncio.run(read_and_validate(upload, settings=Settings(max_upload_mb=0)))
