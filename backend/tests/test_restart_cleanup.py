"""Startup/restart cleanup regression (PRD §16).

The local-acceptance run once reported *"backend restart did not clear temporary
history and artifacts"*. The application was not at fault: the harness had reused a
live listener, so no fresh process — and therefore no startup wipe — ever ran. These
tests pin the guarantee itself, using the **same runtime directory** a previous
process used:

* a process killed without graceful shutdown leaves a SQLite row and PNG files;
* the next application lifespan removes both before serving anything;
* a second lifespan over a live session's runtime directory starts empty.

A real-process version of the same check lives in
``scripts/check_restart_cleanup.py`` (two actual uvicorn processes, same
``RUNTIME_DIR``, with an explicit proof that the first process is dead).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.history_repository import HistoryRepository
from app.main import create_app
from app.services import history_service as history_service_module
from app.services.history_service import HistoryService
from app.services.image_artifact_service import ArtifactStore
from app.services.prediction_service import predict_upload
from app.services.upload_validation import validate_upload
from tests.vision_helpers import encode_png, leaf_with_spots


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the real settings at a throwaway runtime directory."""
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    get_settings.cache_clear()
    history_service_module.reset_history_service()
    try:
        yield runtime
    finally:
        history_service_module.reset_history_service()
        get_settings.cache_clear()


def _predict(client: TestClient) -> dict:
    image, _, _ = leaf_with_spots(480, 240)
    response = client.post(
        "/api/v1/predict",
        files={"file": ("leaf.png", encode_png(image), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"predicted", "uncertain"}
    assert body["prediction_id"]
    return body


def _leave_killed_process_state(runtime: Path) -> str:
    """Write a real row + real artifact files, then walk away (no ``close()``).

    This is exactly the disk state a process killed with TerminateProcess leaves
    behind, which is why startup has to do the cleanup rather than shutdown.
    """
    service = HistoryService(
        HistoryRepository(runtime / "history.sqlite3"),
        ArtifactStore(runtime / "artifacts"),
    )
    service.start_fresh()
    image, _, _ = leaf_with_spots(480, 240)
    result = predict_upload(validate_upload("leaf.png", encode_png(image)))
    service.record(result)

    assert service.repository.count() == 1
    assert service.artifacts.prediction_dir(result.prediction_id).is_dir()
    return result.prediction_id


def _artifact_files(runtime: Path) -> list[Path]:
    artifacts = runtime / "artifacts"
    if not artifacts.is_dir():
        return []
    return [path for path in artifacts.rglob("*") if path.is_file()]


def test_startup_wipes_a_killed_process_history_and_artifacts(runtime_env: Path) -> None:
    leftover_id = _leave_killed_process_state(runtime_env)
    assert (runtime_env / "history.sqlite3").is_file()
    assert len(_artifact_files(runtime_env)) == 3

    with TestClient(create_app()) as client:
        history = client.get("/api/v1/history").json()
        assert history["count"] == 0
        assert history["items"] == []

        # The old row and its files are gone, not merely hidden from the list.
        assert client.get(f"/api/v1/history/{leftover_id}").status_code == 404
        assert client.get(f"/api/v1/history/{leftover_id}/original").status_code == 404
        assert not (runtime_env / "artifacts" / leftover_id).exists()
        assert _artifact_files(runtime_env) == []


def test_a_second_start_over_the_same_runtime_dir_starts_empty(runtime_env: Path) -> None:
    first = TestClient(create_app())
    first.__enter__()
    try:
        predicted = _predict(first)
        prediction_id = predicted["prediction_id"]
        assert first.get("/api/v1/history").json()["count"] == 1
        assert (runtime_env / "artifacts" / prediction_id).is_dir()

        # A fresh process over the same runtime directory (the old one is gone).
        second = TestClient(create_app())
        second.__enter__()
        try:
            assert second.get("/api/v1/history").json()["count"] == 0
            assert not (runtime_env / "artifacts" / prediction_id).exists()
            assert (
                second.get(f"/api/v1/history/{prediction_id}/original").status_code
                == 404
            )

            # The new process can still predict and store its own temporary row.
            fresh = _predict(second)
            assert fresh["prediction_id"] != prediction_id
            assert second.get("/api/v1/history").json()["count"] == 1
        finally:
            second.__exit__(None, None, None)
    finally:
        first.__exit__(None, None, None)


def test_startup_recreates_an_empty_schema_when_only_the_database_survives(
    runtime_env: Path,
) -> None:
    leftover_id = _leave_killed_process_state(runtime_env)
    # Someone (or a partial cleanup) removed the artifact files but left history.
    for path in _artifact_files(runtime_env):
        path.unlink()

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/history").json()["count"] == 0
        assert client.get(f"/api/v1/history/{leftover_id}").status_code == 404
        assert client.get("/api/v1/history").status_code == 200
