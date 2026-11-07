"""`GET /api/v1/model-info` — the loaded model's identity and provenance (Phase 4 M2).

The response is built from the verified bundle manifest, so it always describes the
model that is actually in memory. Nothing here predicts, retrains or recomputes
metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.exceptions import ModelNotLoadedError
from app.schemas.model_info import ModelInfoResponse
from app.services.inference_service import SCORE_KIND, SCORE_NOTE, InferenceService

router = APIRouter(tags=["model"])


def build_model_info(service: InferenceService) -> ModelInfoResponse:
    """Translate the loaded bundle manifest into the public response model."""
    manifest = service.bundle.manifest
    training = manifest.get("training") or {}
    cv = training.get("cv") or {}
    evaluation = manifest.get("evaluation") or {}
    held_out = evaluation.get("held_out") or {}
    held_out_metrics = held_out.get("metrics") or {}
    provenance = manifest.get("provenance") or {}

    return ModelInfoResponse(
        model_name=service.bundle.model_name,
        model_version=service.model_version,
        bundle_version=str(manifest.get("bundle_version", "0")),
        bundle_exported_at=str(manifest.get("exported_at", "")),
        feature_set_version=service.bundle.feature_set_version,
        feature_count=len(service.bundle.feature_names),
        classes=list(service.classes),
        segmentation_config_version=service.bundle.segmentation_config_version,
        quality_config_version=service.bundle.quality_config_version,
        dataset_version=str(provenance.get("dataset_version", "")),
        split_protocol=str(provenance.get("split_protocol", "")),
        training_rows=int(training.get("development_rows", 0)),
        cv_macro_f1_mean=float(cv.get("macro_f1_mean", 0.0)),
        cv_macro_f1_std=float(cv.get("macro_f1_std", 0.0)),
        cv_accuracy_mean=float(cv.get("accuracy_mean", 0.0)),
        cv_balanced_accuracy_mean=float(cv.get("balanced_accuracy_mean", 0.0)),
        held_out_rows=int(held_out.get("n", 0)),
        held_out_macro_f1=float(held_out_metrics.get("macro_f1", 0.0)),
        held_out_accuracy=float(held_out_metrics.get("accuracy", 0.0)),
        held_out_status=str(held_out.get("status", "")),
        calibrated_probabilities=service.bundle.produces_probabilities,
        score_kind=SCORE_KIND,
        score_note=SCORE_NOTE,
        severity_disclaimer=str(manifest.get("severity_disclaimer", "")),
        known_failure_cases=[str(item) for item in manifest.get("known_failure_cases") or []],
    )


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    summary="Loaded model, feature schema and honest performance metadata",
)
async def model_info(request: Request) -> ModelInfoResponse:
    """Describe the model loaded at startup; 503 when it is unavailable."""
    service: InferenceService | None = getattr(request.app.state, "inference", None)
    if service is None:
        raise ModelNotLoadedError()
    return build_model_info(service)
