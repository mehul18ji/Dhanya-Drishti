"""Temporary history and artifact routes (Phase 4 M9, PRD §15/§16).

Everything here is runtime-only:

* `GET /api/v1/history` lists the current session's predictions (newest first),
  sweeping expired rows first;
* `GET /api/v1/history/{prediction_id}` returns one record;
* `GET /api/v1/history/{prediction_id}/{original|leaf-mask|lesion-mask}` serves the
  temporary PNG artifacts;
* `DELETE /api/v1/history` removes every row **and** every artifact file at once.

Unknown, expired or invalid ids answer 404 `PREDICTION_NOT_FOUND`; a missing file
answers 404 `ARTIFACT_NOT_FOUND`. Invalid UUIDs are rejected by FastAPI with 422
before any storage code runs, so a crafted id can never touch the filesystem.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import ArtifactNotFoundError, PredictionNotFoundError
from app.schemas.history import (
    HistoryDeleteResponse,
    HistoryItem,
    HistoryListResponse,
)
from app.schemas.prediction import ArtifactLinks
from app.services.history_service import (
    DEFAULT_HISTORY_LIMIT,
    HistoryEntry,
    HistoryService,
    get_history_service,
)

router = APIRouter(tags=["history"], prefix="/history")

PNG_MEDIA_TYPE = "image/png"


def _history_for(request: Request) -> HistoryService:
    return getattr(request.app.state, "history", None) or get_history_service()


def _item(entry: HistoryEntry) -> HistoryItem:
    record = entry.record
    urls = entry.artifact_urls
    return HistoryItem(
        prediction_id=record.prediction_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        status=record.status,  # type: ignore[arg-type]
        disease=record.disease,
        decision_scores=dict(record.decision_scores),
        margin=record.margin,
        severity=record.severity,  # type: ignore[arg-type]
        severity_reason_code=record.severity_reason_code,
        severity_config_version=record.severity_config_version,
        lesion_area_percentage=record.lesion_area_percentage,
        lesion_reliable=record.lesion_reliable,
        model_name=record.model_name,
        model_version=record.model_version,
        feature_set_version=record.feature_set_version,
        segmentation_config_version=record.segmentation_config_version,
        quality_config_version=record.quality_config_version,
        warnings=list(record.warnings),
        rejections=list(record.rejections),
        missing_features=list(record.missing_features),
        stage_ms=dict(record.stage_ms),
        artifacts=ArtifactLinks(
            original_url=urls.get("original_url"),
            leaf_mask_url=urls.get("leaf_mask_url"),
            lesion_mask_url=urls.get("lesion_mask_url"),
        ),
    )


@router.get(
    "",
    response_model=HistoryListResponse,
    summary="Temporary prediction history (current backend runtime only)",
)
async def list_history(
    request: Request,
    limit: int = Query(DEFAULT_HISTORY_LIMIT, ge=1, le=200),
) -> HistoryListResponse:
    entries = await run_in_threadpool(_history_for(request).list_recent, limit)
    return HistoryListResponse(
        count=len(entries), items=[_item(entry) for entry in entries]
    )


@router.delete(
    "",
    response_model=HistoryDeleteResponse,
    summary="Delete every temporary prediction record and artifact",
)
async def clear_history(request: Request) -> HistoryDeleteResponse:
    deleted = await run_in_threadpool(_history_for(request).delete_all)
    return HistoryDeleteResponse(deleted=int(deleted))


@router.get(
    "/{prediction_id}",
    response_model=HistoryItem,
    summary="One temporary prediction record",
    responses={404: {"description": "Unknown or expired prediction id."}},
)
async def get_history_item(prediction_id: uuid.UUID, request: Request) -> HistoryItem:
    entry = await run_in_threadpool(
        _history_for(request).get, str(prediction_id)
    )
    return _item(entry)


async def _artifact(request: Request, prediction_id: uuid.UUID, kind: str) -> FileResponse:
    history = _history_for(request)
    # An expired record is gone even if the periodic sweep has not deleted its
    # files yet: never serve a PNG past the 60-minute TTL.
    try:
        await run_in_threadpool(history.get, str(prediction_id))
    except PredictionNotFoundError:
        raise ArtifactNotFoundError() from None
    try:
        path = await run_in_threadpool(
            history.artifacts.resolve, str(prediction_id), kind
        )
    except ArtifactNotFoundError:
        raise
    return FileResponse(path, media_type=PNG_MEDIA_TYPE, filename=path.name)


@router.get(
    "/{prediction_id}/original",
    response_class=FileResponse,
    summary="Temporary uploaded image for one prediction",
    responses={404: {"description": "Missing or expired artifact."}},
)
async def get_original_artifact(
    prediction_id: uuid.UUID, request: Request
) -> FileResponse:
    return await _artifact(request, prediction_id, "original")


@router.get(
    "/{prediction_id}/leaf-mask",
    response_class=FileResponse,
    summary="Temporary leaf mask for one prediction",
    responses={404: {"description": "Missing or expired artifact."}},
)
async def get_leaf_mask_artifact(
    prediction_id: uuid.UUID, request: Request
) -> FileResponse:
    return await _artifact(request, prediction_id, "leaf_mask")


@router.get(
    "/{prediction_id}/lesion-mask",
    response_class=FileResponse,
    summary="Temporary lesion mask for one prediction",
    responses={404: {"description": "Missing or expired artifact."}},
)
async def get_lesion_mask_artifact(
    prediction_id: uuid.UUID, request: Request
) -> FileResponse:
    return await _artifact(request, prediction_id, "lesion_mask")
