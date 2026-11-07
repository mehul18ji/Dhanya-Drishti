"""Upload validation (Phase 4 M3).

Validates an uploaded file **before** any decoding, cropping or segmentation work:

1. an allowlist on the *filename extension* (jpg / jpeg / png / webp);
2. the configured size limit, enforced while reading as well as on the final buffer;
3. a real-format sniff with Pillow — the bytes must be a readable JPEG/PNG/WEBP and
   must match the extension family, so a renamed `.gif`/`.svg`/text file is refused;
4. the hard dimension limits from `backend/configs/quality_thresholds.yaml`;
5. EXIF orientation, recorded (never silently "fixed") so later stages can report it.

Failures are the typed `AppError` subclasses already mapped to HTTP status codes
(413 too large, 415 unsupported type, 422 unreadable/too small), so routes do not
need to invent error handling. Nothing here touches the model, the dataset or the
held-out rows.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from starlette.datastructures import UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    UploadValidationError,
)
from app.vision.config import QualityConfig, load_quality_config

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})
FORMATS_BY_EXTENSION: dict[str, frozenset[str]] = {
    ".jpg": frozenset({"JPEG"}),
    ".jpeg": frozenset({"JPEG"}),
    ".png": frozenset({"PNG"}),
    ".webp": frozenset({"WEBP"}),
}
ALLOWED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})
EXIF_ORIENTATION_TAG: int = 0x0112
READ_CHUNK_BYTES: int = 1 << 20


@dataclass(frozen=True)
class UploadValidationResult:
    """A validated upload, ready for the preprocessing/segmentation stage."""

    filename: str
    extension: str
    detected_format: str
    size_bytes: int
    width: int
    height: int
    mode: str
    exif_orientation: int | None
    content: bytes

    @property
    def short_side(self) -> int:
        return min(self.width, self.height)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0


def _limit_bytes(settings: Settings) -> int:
    return int(settings.max_upload_mb) * 1024 * 1024


def _check_extension(filename: str) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            "Unsupported file type. Allowed types: JPG, JPEG, PNG, WEBP."
        )
    return extension


def _probe_image(content: bytes) -> tuple[str, int, int, str, int | None]:
    """Sniff the real format and geometry with Pillow (never trusts the name)."""
    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(content)) as image:
            detected = (image.format or "").upper()
            width, height = image.size
            mode = image.mode
            orientation = image.getexif().get(EXIF_ORIENTATION_TAG)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise UploadValidationError(
            "The uploaded file is not a readable image."
        ) from exc

    if detected not in ALLOWED_FORMATS:
        raise UnsupportedFileTypeError(
            f"Unsupported image format {detected or 'unknown'!r}. "
            "Allowed types: JPG, JPEG, PNG, WEBP."
        )
    if width < 1 or height < 1:
        raise UploadValidationError("The uploaded image has no usable dimensions.")
    return detected, int(width), int(height), str(mode), (
        int(orientation) if orientation is not None else None
    )


def validate_upload(
    filename: str,
    content: bytes,
    *,
    settings: Settings | None = None,
    quality_config: QualityConfig | None = None,
) -> UploadValidationResult:
    """Validate one upload by name, size, real format and hard dimension limits."""
    resolved_settings = settings or get_settings()
    limit = _limit_bytes(resolved_settings)

    if not content:
        raise UploadValidationError("The uploaded file is empty.")
    if len(content) > limit:
        raise FileTooLargeError(
            "The uploaded file exceeds the maximum allowed size of "
            f"{resolved_settings.max_upload_mb} MB."
        )

    extension = _check_extension(filename)
    detected, width, height, mode, orientation = _probe_image(content)

    if detected not in FORMATS_BY_EXTENSION[extension]:
        raise UnsupportedFileTypeError(
            f"The file is named {extension} but its contents are {detected}. "
            "Rename it to the real format or re-export it."
        )

    limits = (quality_config or load_quality_config()).dimensions
    if min(width, height) < limits.hard_reject_short_side_px:
        raise UploadValidationError(
            "The image is too small to analyse: "
            f"{width}x{height} px, minimum short side "
            f"{limits.hard_reject_short_side_px} px.",
            reason_code="IMAGE_TOO_SMALL",
        )
    if width * height < limits.hard_reject_total_pixels:
        raise UploadValidationError(
            "The image has too few pixels to analyse: "
            f"{width * height} px, minimum {limits.hard_reject_total_pixels}.",
            reason_code="IMAGE_TOO_SMALL",
        )

    return UploadValidationResult(
        filename=Path(filename or "").name,
        extension=extension,
        detected_format=detected,
        size_bytes=len(content),
        width=width,
        height=height,
        mode=mode,
        exif_orientation=orientation,
        content=content,
    )


async def read_and_validate(
    upload: UploadFile,
    *,
    settings: Settings | None = None,
    quality_config: QualityConfig | None = None,
) -> UploadValidationResult:
    """Read an `UploadFile` with a hard size guard, then validate it.

    The limit is enforced while reading, so an oversized upload is rejected without
    buffering the whole body first.
    """
    resolved_settings = settings or get_settings()
    limit = _limit_bytes(resolved_settings)

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise FileTooLargeError(
                "The uploaded file exceeds the maximum allowed size of "
                f"{resolved_settings.max_upload_mb} MB."
            )
        chunks.append(chunk)

    return validate_upload(
        upload.filename or "",
        b"".join(chunks),
        settings=resolved_settings,
        quality_config=quality_config,
    )
