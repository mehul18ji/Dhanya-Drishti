"""`POST /api/v1/predict` — one upload to one honest result (Phase 4 M8).

Flow: multipart upload -> typed upload validation (413/415/422) -> the CPU-bound
composition (decode, segmentation, features, inference, severity) **in a worker
thread** -> a JSON-safe response.

Two response shapes (PRD §15):

* ``predicted`` / ``uncertain`` with a disease label, decision-margin scores,
  severity + disclaimer, artifacts and temporary-history metadata;
* ``rejected`` with a ``reason_code`` and a human-readable message, **without**
  ``prediction_id``, artifacts or a stored history row.

The route never serialises ``PredictionResult.outcome``; it builds
:class:`PredictionResponse` from the documented projection.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, File, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import ModelNotLoadedError
from app.schemas.prediction import ArtifactLinks, PredictionResponse, RejectedResponse
from app.services.history_service import HistoryEntry, HistoryService, get_history_service
from app.services.prediction_service import PredictionResult, predict_upload
from app.services.upload_validation import read_and_validate
from app.vision.messages import WARNING_MESSAGES

router = APIRouter(tags=["prediction"])
logger = logging.getLogger(__name__)

DEFAULT_REJECTION_CODE = "NO_CLEAR_LEAF_FOUND"


def _rejection_code(result: PredictionResult) -> str:
    """The most informative rejection code ("no leaf" beats a side-effect warning)."""
    if DEFAULT_REJECTION_CODE in result.rejections:
        return DEFAULT_REJECTION_CODE
    return result.rejections[0] if result.rejections else DEFAULT_REJECTION_CODE


def _history_for(request: Request) -> HistoryService:
    return getattr(request.app.state, "history", None) or get_history_service()


def _artifacts(entry: HistoryEntry) -> ArtifactLinks:
    urls = entry.artifact_urls
    return ArtifactLinks(
        original_url=urls.get("original_url"),
        leaf_mask_url=urls.get("leaf_mask_url"),
        lesion_mask_url=urls.get("lesion_mask_url"),
    )


def _prediction_response(
    result: PredictionResult, entry: HistoryEntry
) -> PredictionResponse:
    """Project the composed result onto the public schema (never the raw object)."""
    margin = 0.0 if result.margin is None else float(result.margin)
    return PredictionResponse(
        prediction_id=result.prediction_id,
        status="uncertain" if result.status == "uncertain" else "predicted",
        disease=str(result.disease),
        decision_scores=dict(result.decision_scores),
        margin=margin,
        ranking=list(result.ranking),
        score_kind="decision_margin",
        score_note=result.score_note,
        lesion_area_percentage=result.lesion_area_percentage,
        lesion_reliable=result.lesion_reliable,
        severity=result.severity.severity,
        severity_note=result.severity.short_note,
        severity_disclaimer=result.severity.disclaimer,
        severity_reason_code=result.severity.reason_code,
        severity_method=result.severity.method,
        severity_config_version=result.severity.config_version,
        severity_config_sha256=result.severity.config_sha256,
        warnings=list(result.warnings),
        rejections=list(result.rejections),
        missing_features=list(result.missing_features),
        artifacts=_artifacts(entry),
        model_name=result.model_name,
        model_version=result.model_version,
        feature_set_version=result.feature_set_version,
        segmentation_config_version=result.segmentation_config_version,
        quality_config_version=result.quality_config_version,
        stage_ms=dict(result.stage_ms),
        created_at=entry.record.created_at,
    )


@router.post(
    "/predict",
    response_model=PredictionResponse | RejectedResponse,
    summary="Analyse one rice-leaf photograph",
    responses={
        413: {"description": "Upload exceeds the configured size limit."},
        415: {"description": "Unsupported or spoofed file type."},
        422: {"description": "Corrupt, unreadable or too-small upload."},
        503: {"description": "Production model not loaded."},
    },
)
async def predict(
    request: Request,
    file: UploadFile = File(..., description="One JPG/JPEG/PNG/WEBP rice-leaf photo."),
) -> PredictionResponse | RejectedResponse:
    """Validate the upload, then compose the prediction off the event loop."""
    if getattr(request.app.state, "inference", None) is None:
        raise ModelNotLoadedError()

    settings = get_settings()
    started = time.perf_counter()
    validated = await read_and_validate(file, settings=settings)

    # Segmentation, feature extraction, inference and severity mapping are CPU
    # bound: never run them on the event loop.
    result = await run_in_threadpool(
        predict_upload, validated, prediction_id=str(uuid.uuid4())
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    pipeline_ms = float(result.stage_ms.get("total", 0.0))

    if not result.has_label:
        code = _rejection_code(result)
        logger.info(
            "predict rejected | reason=%s | pipeline=%.0f ms | request=%.0f ms",
            code,
            pipeline_ms,
            elapsed_ms,
        )
        return RejectedResponse(
            reason_code=code, message=WARNING_MESSAGES.get(code, code)
        )

    history = _history_for(request)
    entry = await run_in_threadpool(history.record, result)
    logger.info(
        "predict %s | status=%s | disease=%s | severity=%s | pipeline=%.0f ms | request=%.0f ms",
        result.prediction_id,
        result.status,
        result.disease,
        result.severity.severity or f"none({result.severity.reason_code})",
        pipeline_ms,
        elapsed_ms,
    )
    return _prediction_response(result, entry)
