"""Temporary per-prediction image artifacts (Phase 4 M7).

Every artifact lives under ``RUNTIME_DIR/artifacts/<uuid>/`` and is deleted with
its history row (PRD §16). Paths are always built from a **re-serialised** UUID, so
a crafted id can never escape the runtime directory.

Only the three documented artifacts are served:

* ``original`` — the oriented source image,
* ``leaf_mask`` — the detected leaf mask,
* ``lesion_mask`` — the lesion mask inside that leaf.

Nothing here is permanent: the directory is wiped at startup and on shutdown.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np

from app.core.exceptions import ArtifactNotFoundError
from app.services.preprocessing_service import MeasurementArtifacts

ARTIFACT_KINDS: tuple[str, ...] = ("original", "leaf_mask", "lesion_mask")

FILENAMES: dict[str, str] = {
    "original": "original.png",
    "leaf_mask": "leaf_mask.png",
    "lesion_mask": "lesion_mask.png",
}

MEDIA_TYPE = "image/png"


def canonical_prediction_id(value: str | uuid.UUID) -> str:
    """Return the canonical UUID string; refuse anything that is not a UUID."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"not a prediction UUID: {value!r}") from exc


def _encode_png(image: np.ndarray) -> bytes:
    array = np.ascontiguousarray(image)
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    ok, buffer = cv2.imencode(".png", array)
    if not ok:  # pragma: no cover - impossible for a valid ndarray
        raise ValueError("could not encode artifact as PNG")
    return buffer.tobytes()


class ArtifactStore:
    """Writes and resolves the temporary PNG artifacts for one prediction."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def prediction_dir(self, prediction_id: str | uuid.UUID) -> Path:
        return self.root / canonical_prediction_id(prediction_id)

    def save(
        self, prediction_id: str | uuid.UUID, artifacts: MeasurementArtifacts
    ) -> dict[str, Path]:
        """Persist whichever of the three artifacts the pipeline produced."""
        directory = self.prediction_dir(prediction_id)
        directory.mkdir(parents=True, exist_ok=True)

        candidates = {
            "original": artifacts.original,
            "leaf_mask": artifacts.leaf_mask,
            "lesion_mask": artifacts.lesion_mask,
        }
        saved: dict[str, Path] = {}
        for kind, image in candidates.items():
            if image is None:
                continue
            path = directory / FILENAMES[kind]
            path.write_bytes(_encode_png(image))
            saved[kind] = path
        return saved

    def resolve(self, prediction_id: str | uuid.UUID, kind: str) -> Path:
        """Return the file for one artifact, or raise a 404."""
        if kind not in ARTIFACT_KINDS:
            raise ArtifactNotFoundError(f"Unknown artifact {kind!r}.")
        path = self.prediction_dir(prediction_id) / FILENAMES[kind]
        if not path.is_file():
            raise ArtifactNotFoundError()
        return path

    def delete(self, prediction_id: str | uuid.UUID) -> bool:
        directory = self.prediction_dir(prediction_id)
        if not directory.is_dir():
            return False
        for child in directory.iterdir():
            if child.is_file():
                child.unlink()
        directory.rmdir()
        return True

    def delete_all(self) -> int:
        """Remove every artifact directory; returns how many were removed."""
        if not self.root.is_dir():
            return 0
        removed = 0
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            for child in directory.iterdir():
                if child.is_file():
                    child.unlink()
            directory.rmdir()
            removed += 1
        return removed
