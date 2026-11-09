"""Temporary history + artifact storage tests (Phase 4 M7).

Every test uses a throwaway runtime directory and synthetic images: no dataset, no
network, no permanent state.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from app.core.exceptions import (
    ArtifactNotFoundError,
    PredictionNotFoundError,
)
from app.db.history_repository import HistoryRepository, iso, utc_now
from app.services.history_service import HistoryService, sweep_expired_periodically
from app.services.image_artifact_service import (
    ARTIFACT_KINDS,
    ArtifactStore,
    canonical_prediction_id,
)
from app.services.prediction_service import predict_upload
from app.services.upload_validation import validate_upload
from tests.vision_helpers import encode_png, leaf_with_spots


def _service(tmp_path: Path, *, expiry_minutes: int = 60) -> HistoryService:
    runtime = tmp_path / "runtime"
    service = HistoryService(
        HistoryRepository(runtime / "history.sqlite3"),
        ArtifactStore(runtime / "artifacts"),
        expiry_minutes=expiry_minutes,
        api_prefix="/api/v1",
    )
    service.start_fresh()
    return service


def _prediction(prediction_id: str | None = None):
    image, _, _ = leaf_with_spots(480, 240)
    upload = validate_upload("leaf.png", encode_png(image))
    return predict_upload(upload, prediction_id=prediction_id or str(uuid.uuid4()))


# --------------------------------------------------------------------------- #
# Identity / path safety
# --------------------------------------------------------------------------- #


def test_ids_are_canonical_uuids_and_paths_cannot_traverse(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    identifier = str(uuid.uuid4())

    assert canonical_prediction_id(identifier) == identifier
    assert store.prediction_dir(identifier).parent == tmp_path

    for bad in ("../../etc/passwd", "not-a-uuid", "", ".."):
        with pytest.raises(ValueError):
            canonical_prediction_id(bad)


def test_unknown_identifier_is_a_404_not_a_crash(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)

    with pytest.raises(ArtifactNotFoundError):
        store.resolve(str(uuid.uuid4()), "original")
    with pytest.raises(ArtifactNotFoundError):
        store.resolve(str(uuid.uuid4()), "nonexistent-kind")


# --------------------------------------------------------------------------- #
# Round trip
# --------------------------------------------------------------------------- #


def test_record_persists_row_and_artifacts_together(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = _prediction()

    entry = service.record(result)

    assert entry.record.prediction_id == result.prediction_id
    assert entry.record.status == result.status
    assert entry.record.disease == result.disease
    assert entry.record.severity == result.severity.severity
    assert entry.record.severity_reason_code == result.severity.reason_code
    assert entry.record.model_version == "svm-v1.0.0"
    if result.lesion_area_percentage is None:
        assert entry.record.lesion_area_percentage is None
    else:
        assert entry.record.lesion_area_percentage == pytest.approx(
            result.lesion_area_percentage
        )

    for kind in ARTIFACT_KINDS:
        path = service.artifacts.resolve(result.prediction_id, kind)
        assert path.is_file()
        assert path.stat().st_size > 0
        assert f"{kind}_url" in entry.artifact_urls
        assert entry.artifact_urls[f"{kind}_url"].endswith(
            {"original": "/original", "leaf_mask": "/leaf-mask", "lesion_mask": "/lesion-mask"}[
                kind
            ]
        )

    fetched = service.get(result.prediction_id)
    assert fetched.record.as_dict()["prediction_id"] == result.prediction_id
    assert fetched.record.warnings == list(result.warnings)
    assert fetched.record.decision_scores == pytest.approx(result.decision_scores)


def test_list_is_newest_first_and_limited(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _prediction()
    second = _prediction()
    now = utc_now()

    service.record(first, now=now - timedelta(minutes=5))
    service.record(second, now=now)

    listed = service.list_recent(limit=10)
    assert [entry.record.prediction_id for entry in listed] == [
        second.prediction_id,
        first.prediction_id,
    ]
    assert len(service.list_recent(limit=1)) == 1


def test_recorded_row_is_json_safe(tmp_path: Path) -> None:
    service = _service(tmp_path)
    entry = service.record(_prediction())

    payload = entry.as_dict()

    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["artifacts"], dict)
    assert isinstance(payload["decision_scores"], dict)
    assert "confidence" not in payload
    assert "probability" not in payload


# --------------------------------------------------------------------------- #
# Delete and expiry
# --------------------------------------------------------------------------- #


def test_delete_removes_row_and_files(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = _prediction()
    service.record(result)

    assert service.delete(result.prediction_id) is True

    with pytest.raises(PredictionNotFoundError):
        service.get(result.prediction_id)
    assert not service.artifacts.prediction_dir(result.prediction_id).exists()
    assert service.repository.count() == 0


def test_delete_unknown_prediction_is_a_404(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(PredictionNotFoundError):
        service.delete(str(uuid.uuid4()))


def test_delete_all_clears_rows_and_files(tmp_path: Path) -> None:
    service = _service(tmp_path)
    for _ in range(3):
        service.record(_prediction())

    assert service.repository.count() == 3
    assert service.delete_all() == 3
    assert service.repository.count() == 0
    assert service.artifacts.delete_all() == 0


def test_expired_rows_and_files_are_swept(tmp_path: Path) -> None:
    service = _service(tmp_path, expiry_minutes=10)
    result = _prediction()
    created = utc_now() - timedelta(minutes=30)
    service.record(result, now=created)

    assert service.repository.count() == 1
    assert service.sweep_expired(now=created + timedelta(minutes=11)) == 1
    assert service.repository.count() == 0
    assert not service.artifacts.prediction_dir(result.prediction_id).exists()

    with pytest.raises(PredictionNotFoundError):
        service.get(result.prediction_id)


def test_get_reports_an_expired_row_as_missing(tmp_path: Path) -> None:
    service = _service(tmp_path, expiry_minutes=5)
    result = _prediction()
    service.record(result, now=utc_now() - timedelta(hours=2))

    with pytest.raises(PredictionNotFoundError):
        service.get(result.prediction_id)
    assert service.repository.count() == 0


def test_periodic_sweep_deletes_expired_records_without_any_request(
    tmp_path: Path,
) -> None:
    """A record must vanish on the timer even if no client ever reads history."""
    service = _service(tmp_path, expiry_minutes=10)
    result = _prediction()
    service.record(result, now=utc_now() - timedelta(minutes=30))

    async def run_briefly() -> None:
        task = asyncio.create_task(sweep_expired_periodically(service, 0.02))
        await asyncio.sleep(0.12)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_briefly())

    assert service.repository.count() == 0
    assert not service.artifacts.prediction_dir(result.prediction_id).exists()


def test_periodic_sweep_keeps_going_after_a_transient_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One failed sweep must not stop the expiry loop for the process lifetime."""
    service = _service(tmp_path, expiry_minutes=10)
    result = _prediction()
    service.record(result, now=utc_now() - timedelta(minutes=30))

    original = service.sweep_expired
    calls = {"count": 0}

    def flaky(*, now=None):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient disk hiccup")
        return original(now=now)

    monkeypatch.setattr(service, "sweep_expired", flaky)

    async def run_briefly() -> None:
        task = asyncio.create_task(sweep_expired_periodically(service, 0.02))
        await asyncio.sleep(0.12)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_briefly())

    assert calls["count"] >= 2
    assert service.repository.count() == 0


def test_start_fresh_wipes_a_previous_run(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = _prediction()
    service.record(result)

    assert (tmp_path / "runtime" / "history.sqlite3").exists()
    assert service.artifacts.prediction_dir(result.prediction_id).exists()

    service.start_fresh()

    assert service.repository.count() == 0
    assert not service.artifacts.prediction_dir(result.prediction_id).exists()


def test_close_removes_everything(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.record(_prediction())
    runtime = tmp_path / "runtime"

    service.close()

    assert not (runtime / "history.sqlite3").exists()
    artifacts_dir = runtime / "artifacts"
    assert not artifacts_dir.exists() or list(artifacts_dir.iterdir()) == []


# --------------------------------------------------------------------------- #
# Prediction hook
# --------------------------------------------------------------------------- #


def test_predict_upload_records_when_a_history_is_supplied(tmp_path: Path) -> None:
    service = _service(tmp_path)
    image, _, _ = leaf_with_spots(480, 240)
    upload = validate_upload("leaf.png", encode_png(image))

    result = predict_upload(upload, history=service)

    stored = service.get(result.prediction_id).record
    assert stored.status == result.status
    assert stored.model_version == result.model_version


def test_predict_upload_writes_nothing_without_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    image, _, _ = leaf_with_spots(480, 240)

    result = predict_upload(validate_upload("leaf.png", encode_png(image)))

    assert isinstance(result.status, str)
    assert list(tmp_path.iterdir()) == []


def test_rejected_prediction_is_never_stored(tmp_path: Path) -> None:
    """A rejected upload has no label, so it must stay out of history (M8 contract)."""
    service = _service(tmp_path)
    blank = np.full((400, 400, 3), 250, dtype=np.uint8)
    result = predict_upload(validate_upload("blank.png", encode_png(blank)), history=service)

    assert result.status == "rejected"
    assert result.has_label is False
    assert service.repository.count() == 0
    assert not service.artifacts.prediction_dir(result.prediction_id).exists()
    with pytest.raises(PredictionNotFoundError):
        service.get(result.prediction_id)
    assert iso(utc_now())  # timestamp helper still exercised
