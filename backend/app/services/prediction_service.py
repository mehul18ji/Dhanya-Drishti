"""Prediction composition (Phase 4 M6).

One call turns a validated upload into the single typed result a future
``POST /api/v1/predict`` route will serialise. It composes the three verified
pieces and adds no modelling logic of its own:

1. :func:`app.services.preprocessing_service.preprocess_upload` — validated upload
   -> decode -> segmentation -> 50-feature vector, with the explicit
   ``predicted`` / ``uncertain`` / ``rejected`` mapping;
2. :meth:`app.services.inference_service.InferenceService.predict` — the loaded
   bundle's label plus ``decision_function`` scores;
3. :func:`app.vision.severity.severity_for` — the experimental severity bucket, or
   an explicit "cannot say" with its reason.

Rules this module exists to enforce:

* **No confidence percentage.** The bundle is uncalibrated (decision P-15), so the
  scores are reported as ``decision_margin`` values with the same plain-language
  note as ``/model-info``. Nothing here is called confidence or probability.
* **No invented uncertainty policy.** The status comes from the M4 mapping; the
  only extra rule is a one-way honesty downgrade — if a ``predicted`` outcome
  somehow cannot produce a severity, the result becomes ``uncertain`` rather than
  presenting a label with no measurement behind it. Nothing is ever upgraded, and
  score magnitude is *not* used as a threshold (decision P-05 stays open).
* **A rejected image is never classified.** No label, no scores, no severity; the
  rejection codes carry the explanation.
* **No persistence.** This service writes no files, creates no history rows and
  stores no artifacts. It only returns data; a ``prediction_id`` is generated so a
  later route/history layer can key the response, and is not recorded anywhere.
* **No training or tuning.** The model is only ever used for inference, and the
  held-out rows are never read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from app.services.inference_service import (
    SCORE_KIND,
    SCORE_NOTE,
    InferenceService,
)
from app.services.preprocessing_service import (
    STATUS_PREDICTED,
    STATUS_REJECTED,
    STATUS_UNCERTAIN,
    PreprocessingOutcome,
    PublicStatus,
    preprocess_upload,
    require_inference_service,
)
from app.services.upload_validation import UploadValidationResult
from app.vision.config import QualityConfig, SegmentationConfig, SeverityConfig
from app.vision.severity import SeverityResult, severity_for

#: Statuses a composed prediction may carry (``rejected`` has no label).
NO_LABEL_STATUSES: Final[tuple[str, ...]] = (STATUS_REJECTED,)


@dataclass(frozen=True)
class PredictionResult:
    """One upload's disease label, scores, severity and provenance."""

    prediction_id: str
    status: PublicStatus
    disease: str | None
    decision_scores: dict[str, float]
    margin: float | None
    ranking: tuple[str, ...]
    lesion_area_percentage: float | None
    lesion_reliable: bool
    severity: SeverityResult
    warnings: tuple[str, ...]
    rejections: tuple[str, ...]
    missing_features: tuple[str, ...]
    model_name: str
    model_version: str
    feature_set_version: str
    segmentation_config_version: str
    quality_config_version: str
    stage_ms: dict[str, float]
    outcome: PreprocessingOutcome
    score_kind: str = SCORE_KIND
    score_note: str = SCORE_NOTE

    @property
    def has_label(self) -> bool:
        """True only when a disease label was actually produced."""
        return self.disease is not None

    @property
    def is_rejected(self) -> bool:
        return self.status == STATUS_REJECTED

    def as_dict(self) -> dict[str, object]:
        """Flat, JSON-safe view for the later response model.

        Deliberately contains no ``confidence`` or ``probability`` key: these are
        decision-function margins, and the severity is an experimental bucket.
        """
        return {
            "prediction_id": self.prediction_id,
            "status": self.status,
            "disease": self.disease,
            "decision_scores": dict(self.decision_scores),
            "margin": self.margin,
            "ranking": list(self.ranking),
            "score_kind": self.score_kind,
            "score_note": self.score_note,
            "lesion_area_percentage": self.lesion_area_percentage,
            "lesion_reliable": self.lesion_reliable,
            "severity": self.severity.severity,
            "severity_note": self.severity.short_note,
            "severity_disclaimer": self.severity.disclaimer,
            "severity_reason_code": self.severity.reason_code,
            "severity_method": self.severity.method,
            "severity_config_version": self.severity.config_version,
            "severity_config_sha256": self.severity.config_sha256,
            "warnings": list(self.warnings),
            "rejections": list(self.rejections),
            "missing_features": list(self.missing_features),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "feature_set_version": self.feature_set_version,
            "segmentation_config_version": self.segmentation_config_version,
            "quality_config_version": self.quality_config_version,
            "stage_ms": dict(self.stage_ms),
        }


def predict_upload(
    upload: UploadValidationResult,
    *,
    inference_service: InferenceService | None = None,
    segmentation_config: SegmentationConfig | None = None,
    quality_config: QualityConfig | None = None,
    severity_config: SeverityConfig | None = None,
    prediction_id: str | None = None,
) -> PredictionResult:
    """Compose preprocessing, inference and severity for one validated upload.

    Raises the typed errors of the composed services unchanged: a missing or
    unverified bundle is ``503 MODEL_NOT_LOADED`` *before* any decoding, an
    unreadable/unusable upload is a ``422``, and bundle/schema faults stay
    server-side errors.
    """
    service = require_inference_service(inference_service)

    outcome = preprocess_upload(
        upload,
        inference_service=service,
        segmentation_config=segmentation_config,
        quality_config=quality_config,
    )
    severity = severity_for(
        outcome.lesion_area_percentage,
        lesion_reliable=outcome.lesion_reliable,
        warnings=outcome.warnings,
        config=severity_config,
    )

    status: PublicStatus = outcome.status
    disease: str | None = None
    decision_scores: dict[str, float] = {}
    margin: float | None = None
    ranking: tuple[str, ...] = ()

    if status not in NO_LABEL_STATUSES:
        prediction = service.predict(outcome.feature_result)
        disease = prediction.label
        decision_scores = dict(prediction.decision_scores)
        margin = float(prediction.margin)
        ranking = tuple(prediction.ranking)

        # Honesty downgrade only: a label with no measurable severity is shown as
        # uncertain. Never the reverse, and never from a score threshold.
        if severity.severity is None:
            status = STATUS_UNCERTAIN

    return PredictionResult(
        prediction_id=prediction_id or str(uuid.uuid4()),
        status=status,
        disease=disease,
        decision_scores=decision_scores,
        margin=margin,
        ranking=ranking,
        lesion_area_percentage=outcome.lesion_area_percentage,
        lesion_reliable=outcome.lesion_reliable,
        severity=severity,
        warnings=outcome.warnings,
        rejections=outcome.rejections,
        missing_features=outcome.missing_features,
        model_name=service.bundle.model_name,
        model_version=service.model_version,
        feature_set_version=outcome.feature_set_version,
        segmentation_config_version=outcome.segmentation_config_version,
        quality_config_version=outcome.quality_config_version,
        stage_ms=outcome.stage_ms,
        outcome=outcome,
    )
