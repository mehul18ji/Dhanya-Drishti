"""Runtime SQLite storage for temporary prediction history (Phase 4 M7).

SQLite is used **only** as a temporary session database under `RUNTIME_DIR`
(PRD §16). The repository is deleted at startup, expires rows on demand and never
holds anything that must survive a restart.

A row is keyed by the prediction UUID and stores exactly what the history page
needs: identity, status, disease, decision scores, severity, lesion measurement,
documented warnings and model/feature/config provenance. Artifact *files* live in
the sibling artifact directory and are handled by
:mod:`app.services.image_artifact_service`; the row only records which files exist.

Writes and reads open short-lived connections so the repository is safe to use from
FastAPI's threadpool without sharing a connection across threads.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id           TEXT PRIMARY KEY,
    created_at              TEXT NOT NULL,
    expires_at              TEXT NOT NULL,
    status                  TEXT NOT NULL,
    disease                 TEXT,
    decision_scores         TEXT NOT NULL,
    margin                  REAL,
    severity                TEXT,
    severity_reason_code    TEXT,
    severity_config_version TEXT NOT NULL,
    lesion_area_percentage  REAL,
    lesion_reliable         INTEGER NOT NULL,
    model_name              TEXT NOT NULL,
    model_version           TEXT NOT NULL,
    feature_set_version     TEXT NOT NULL,
    segmentation_config_version TEXT NOT NULL,
    quality_config_version  TEXT NOT NULL,
    warnings                TEXT NOT NULL,
    rejections              TEXT NOT NULL,
    missing_features        TEXT NOT NULL,
    stage_ms                TEXT NOT NULL,
    has_original            INTEGER NOT NULL,
    has_leaf_mask           INTEGER NOT NULL,
    has_lesion_mask         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_expires_at ON predictions (expires_at);
"""


@dataclass(frozen=True)
class HistoryRecord:
    """One prediction as stored in the temporary runtime database."""

    prediction_id: str
    created_at: str
    expires_at: str
    status: str
    disease: str | None
    decision_scores: dict[str, float]
    margin: float | None
    severity: str | None
    severity_reason_code: str | None
    severity_config_version: str
    lesion_area_percentage: float | None
    lesion_reliable: bool
    model_name: str
    model_version: str
    feature_set_version: str
    segmentation_config_version: str
    quality_config_version: str
    warnings: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    missing_features: list[str] = field(default_factory=list)
    stage_ms: dict[str, float] = field(default_factory=dict)
    has_original: bool = False
    has_leaf_mask: bool = False
    has_lesion_mask: bool = False

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe view (lists, not tuples; no numpy)."""
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        payload["rejections"] = list(self.rejections)
        payload["missing_features"] = list(self.missing_features)
        payload["decision_scores"] = dict(self.decision_scores)
        payload["stage_ms"] = dict(self.stage_ms)
        return payload


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    """Fixed-width UTC ISO-8601, so string comparison equals time comparison."""
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


class HistoryRepository:
    """Minimal, thread-safe-enough SQLite repository for temporary history."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # -- connection helpers ------------------------------------------------- #

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the schema; safe to call on every startup."""
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def wipe(self) -> None:
        """Delete the database file entirely (startup / shutdown cleanup)."""
        for candidate in (
            self.path,
            self.path.with_suffix(self.path.suffix + "-wal"),
            self.path.with_suffix(self.path.suffix + "-shm"),
        ):
            if candidate.exists():
                candidate.unlink()

    # -- writes ------------------------------------------------------------- #

    def upsert(self, record: HistoryRecord) -> None:
        payload = record.as_dict()
        values = {
            **payload,
            "decision_scores": json.dumps(payload["decision_scores"]),
            "warnings": json.dumps(payload["warnings"]),
            "rejections": json.dumps(payload["rejections"]),
            "missing_features": json.dumps(payload["missing_features"]),
            "stage_ms": json.dumps(payload["stage_ms"]),
            "lesion_reliable": int(record.lesion_reliable),
            "has_original": int(record.has_original),
            "has_leaf_mask": int(record.has_leaf_mask),
            "has_lesion_mask": int(record.has_lesion_mask),
        }
        columns = ", ".join(values)
        placeholders = ", ".join(f":{name}" for name in values)
        updates = ", ".join(
            f"{name} = excluded.{name}" for name in values if name != "prediction_id"
        )
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO predictions ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT(prediction_id) DO UPDATE SET {updates}",
                values,
            )

    def delete(self, prediction_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM predictions WHERE prediction_id = ?", (prediction_id,)
            )
            return cursor.rowcount > 0

    def delete_all(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM predictions")
            return int(cursor.rowcount)

    def purge_expired(self, *, now: datetime | None = None) -> list[str]:
        """Delete rows whose expiry has passed and return their ids."""
        moment = iso(now or utc_now())
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT prediction_id FROM predictions WHERE expires_at <= ?", (moment,)
            ).fetchall()
            ids = [str(row["prediction_id"]) for row in rows]
            if ids:
                connection.executemany(
                    "DELETE FROM predictions WHERE prediction_id = ?",
                    [(value,) for value in ids],
                )
            return ids

    # -- reads -------------------------------------------------------------- #

    def get(self, prediction_id: str) -> HistoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,)
            ).fetchone()
        return None if row is None else _to_record(row)

    def list_recent(self, limit: int = 50) -> list[HistoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM predictions ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_to_record(row) for row in rows]

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM predictions").fetchone()
        return int(row["total"])


def _to_record(row: sqlite3.Row) -> HistoryRecord:
    def _list(value: str) -> list[str]:
        decoded = json.loads(value or "[]")
        return [str(item) for item in decoded]

    return HistoryRecord(
        prediction_id=str(row["prediction_id"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        status=str(row["status"]),
        disease=row["disease"],
        decision_scores={
            str(key): float(value)
            for key, value in json.loads(row["decision_scores"] or "{}").items()
        },
        margin=None if row["margin"] is None else float(row["margin"]),
        severity=row["severity"],
        severity_reason_code=row["severity_reason_code"],
        severity_config_version=str(row["severity_config_version"]),
        lesion_area_percentage=(
            None
            if row["lesion_area_percentage"] is None
            else float(row["lesion_area_percentage"])
        ),
        lesion_reliable=bool(row["lesion_reliable"]),
        model_name=str(row["model_name"]),
        model_version=str(row["model_version"]),
        feature_set_version=str(row["feature_set_version"]),
        segmentation_config_version=str(row["segmentation_config_version"]),
        quality_config_version=str(row["quality_config_version"]),
        warnings=_list(row["warnings"]),
        rejections=_list(row["rejections"]),
        missing_features=_list(row["missing_features"]),
        stage_ms={
            str(key): float(value)
            for key, value in json.loads(row["stage_ms"] or "{}").items()
        },
        has_original=bool(row["has_original"]),
        has_leaf_mask=bool(row["has_leaf_mask"]),
        has_lesion_mask=bool(row["has_lesion_mask"]),
    )
