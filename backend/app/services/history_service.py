"""Temporary prediction history (Phase 4 M7).

Composes the SQLite repository with the artifact store so a history record and its
PNG files always move together:

* :meth:`HistoryService.record` writes the row **and** the three artifacts;
* :meth:`HistoryService.delete` removes the row **and** the directory;
* :meth:`HistoryService.delete_all` empties both;
* :meth:`HistoryService.sweep_expired` drops expired rows and their files;
* :meth:`HistoryService.start_fresh` / ``close`` wipe the runtime storage at
  startup and shutdown (PRD §16).

Nothing here is permanent and nothing is promised across a restart. A missing row
raises :class:`app.core.exceptions.PredictionNotFoundError` (404) so routes never
have to guess.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.config import Settings, get_settings
from app.core.exceptions import PredictionNotFoundError
from app.db.history_repository import HistoryRecord, HistoryRepository, iso, utc_now
from app.services.image_artifact_service import ArtifactStore, canonical_prediction_id
from app.services.prediction_service import PredictionResult

DEFAULT_HISTORY_LIMIT: int = 50
DEFAULT_API_PREFIX: str = "/api/v1"

#: URL suffix per artifact kind (PRD §15 `artifacts` block).
ARTIFACT_ROUTES: dict[str, str] = {
    "original": "original",
    "leaf_mask": "leaf-mask",
    "lesion_mask": "lesion-mask",
}


@dataclass(frozen=True)
class HistoryEntry:
    """One stored prediction plus the URLs its artifacts will be served from."""

    record: HistoryRecord
    artifact_urls: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = dict(self.record.as_dict())
        payload["artifacts"] = dict(self.artifact_urls)
        return payload


class HistoryService:
    """Runtime-only prediction history (SQLite rows + temporary PNG artifacts)."""

    def __init__(
        self,
        repository: HistoryRepository,
        artifacts: ArtifactStore,
        *,
        expiry_minutes: int = 60,
        api_prefix: str = DEFAULT_API_PREFIX,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts
        self.expiry_minutes = int(expiry_minutes)
        self.api_prefix = api_prefix.rstrip("/") or DEFAULT_API_PREFIX

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "HistoryService":
        resolved = settings or get_settings()
        runtime_dir = resolved.resolve_path(resolved.runtime_dir)
        return cls(
            HistoryRepository(runtime_dir / "history.sqlite3"),
            ArtifactStore(runtime_dir / "artifacts"),
            expiry_minutes=resolved.history_expiry_minutes,
            api_prefix=resolved.api_v1_prefix,
        )

    # -- lifecycle ---------------------------------------------------------- #

    def start_fresh(self) -> None:
        """Wipe anything left by a previous run, then create the schema."""
        self.repository.wipe()
        self.artifacts.delete_all()
        self.repository.initialize()

    def close(self) -> None:
        """Remove runtime storage on graceful shutdown where possible."""
        self.repository.wipe()
        self.artifacts.delete_all()

    # -- writes ------------------------------------------------------------- #

    def record(
        self, result: PredictionResult, *, now: datetime | None = None
    ) -> HistoryEntry:
        """Persist one composed prediction (row + artifacts) and return its entry."""
        prediction_id = canonical_prediction_id(result.prediction_id)
        created = now or utc_now()
        saved = self.artifacts.save(prediction_id, result.outcome.artifacts)

        record = HistoryRecord(
            prediction_id=prediction_id,
            created_at=iso(created),
            expires_at=iso(created + timedelta(minutes=self.expiry_minutes)),
            status=result.status,
            disease=result.disease,
            decision_scores=dict(result.decision_scores),
            margin=result.margin,
            severity=result.severity.severity,
            severity_reason_code=result.severity.reason_code,
            severity_config_version=result.severity.config_version,
            lesion_area_percentage=result.lesion_area_percentage,
            lesion_reliable=bool(result.lesion_reliable),
            model_name=result.model_name,
            model_version=result.model_version,
            feature_set_version=result.feature_set_version,
            segmentation_config_version=result.segmentation_config_version,
            quality_config_version=result.quality_config_version,
            warnings=list(result.warnings),
            rejections=list(result.rejections),
            missing_features=list(result.missing_features),
            stage_ms=dict(result.stage_ms),
            has_original="original" in saved,
            has_leaf_mask="leaf_mask" in saved,
            has_lesion_mask="lesion_mask" in saved,
        )
        self.repository.upsert(record)
        return HistoryEntry(record=record, artifact_urls=self._artifact_urls(record))

    def delete(self, prediction_id: str) -> bool:
        """Remove one prediction's row and files together."""
        canonical = canonical_prediction_id(prediction_id)
        row_deleted = self.repository.delete(canonical)
        file_deleted = self.artifacts.delete(canonical)
        if not row_deleted and not file_deleted:
            raise PredictionNotFoundError()
        return True

    def delete_all(self) -> int:
        """Empty the history: every row and every artifact file."""
        removed = self.repository.delete_all()
        self.artifacts.delete_all()
        return removed

    def sweep_expired(self, *, now: datetime | None = None) -> int:
        """Drop expired rows and their files; returns how many rows were removed."""
        expired = self.repository.purge_expired(now=now)
        for prediction_id in expired:
            self.artifacts.delete(prediction_id)
        return len(expired)

    # -- reads -------------------------------------------------------------- #

    def list_recent(self, limit: int = DEFAULT_HISTORY_LIMIT) -> list[HistoryEntry]:
        self.sweep_expired()
        return [
            HistoryEntry(record=record, artifact_urls=self._artifact_urls(record))
            for record in self.repository.list_recent(limit)
        ]

    def get(self, prediction_id: str) -> HistoryEntry:
        """Return one entry, sweeping first so expired rows answer 404 honestly."""
        canonical = canonical_prediction_id(prediction_id)
        record = self.repository.get(canonical)
        if record is None or record.expires_at <= iso(utc_now()):
            # Expired but not yet swept: remove it and report it as gone.
            self.repository.delete(canonical)
            self.artifacts.delete(canonical)
            raise PredictionNotFoundError()
        return HistoryEntry(record=record, artifact_urls=self._artifact_urls(record))

    def _artifact_urls(self, record: HistoryRecord) -> dict[str, str]:
        available = {
            "original": record.has_original,
            "leaf_mask": record.has_leaf_mask,
            "lesion_mask": record.has_lesion_mask,
        }
        return {
            f"{kind}_url": f"{self.api_prefix}/history/{record.prediction_id}/{ARTIFACT_ROUTES[kind]}"
            for kind, present in available.items()
            if present
        }

    def artifact_urls(self, prediction_id: str) -> dict[str, str]:
        """Artifact URLs for a stored prediction (404 when unknown)."""
        return self.get(prediction_id).artifact_urls


# --------------------------------------------------------------------------- #
# Process-wide service (built once, wiped at startup)
# --------------------------------------------------------------------------- #

_service: HistoryService | None = None
_service_lock = threading.Lock()


def get_history_service() -> HistoryService:
    """Return the process-wide history service (created on first use)."""
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is None:
            _service = HistoryService.from_settings()
    return _service


def reset_history_service() -> None:
    """Drop the cached service (tests and explicit reloads only)."""
    global _service
    with _service_lock:
        _service = None
