"""Upload-to-features orchestration (Phase 4 M4).

One call turns an already-validated upload into everything the prediction response
will need: the Phase 2 segmentation result, the versioned Phase 3 feature vector,
the measurement artifacts and an explicit public status.

Nothing here re-implements vision logic. The sequence is exactly the one the
Phase 2 audit and the Phase 3 matrix builder used::

    upload bytes
      -> app.vision.preprocessing (decode + EXIF orientation, aspect-safe working image)
      -> app.vision.pipeline.run_segmentation (quality, leaf, lesion)
      -> app.vision.feature_extraction.extract_features_from_pipeline (50 ordered features)

Status mapping (PRD §11) has three values and only three values:

``rejected``
    The pipeline refused the image (no clear leaf, too dark, ...) or produced no
    feature vector. Nothing is classified and nothing is measured.
``uncertain``
    A vector exists, but quality warnings, missing features or an uncalibrated
    lesion estimate mean the result must not be shown as confident.
``predicted``
    A complete, warning-free vector exists.

There is deliberately **no** ``healthy`` status: the approved dataset has no
healthy class, so the system can never claim a leaf is healthy — an unsupported or
out-of-distribution image comes back ``uncertain`` or ``rejected``.

Lesion honesty is inherited from the extractor and enforced again on the way out:
when the lesion estimate is uncalibrated, ``lesion_area_percentage`` stays
``None`` and the lesion/spatial features stay ``NaN``. An unmeasurable lesion is
never reported as ``0 %``.

The service also refuses to produce features when the production model is not
available (``503 MODEL_NOT_LOADED``) or when the vector was produced by a
different schema / Phase 2 configuration than the loaded bundle pins, because such
a vector is not comparable to what the model was fitted on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np

from app.core.exceptions import ModelNotLoadedError, UploadValidationError
from app.services.inference_service import (
    ConfigMismatchError,
    InferenceError,
    InferenceService,
    SchemaMismatchError,
    get_inference_service,
)
from app.services.upload_validation import UploadValidationResult
from app.vision.config import (
    QualityConfig,
    SegmentationConfig,
    load_quality_config,
    load_segmentation_config,
)
from app.vision.feature_extraction import (
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    FeatureExtractionResult,
    extract_features_from_pipeline,
)
from app.vision.pipeline import SegmentationPipelineResult, run_segmentation
from app.vision.preprocessing import ImageDecodeError

PublicStatus = Literal["predicted", "uncertain", "rejected"]

STATUS_PREDICTED: Final[str] = "predicted"
STATUS_UNCERTAIN: Final[str] = "uncertain"
STATUS_REJECTED: Final[str] = "rejected"

#: Every status this service can return. ``healthy`` is intentionally absent.
PUBLIC_STATUSES: Final[tuple[str, ...]] = (
    STATUS_PREDICTED,
    STATUS_UNCERTAIN,
    STATUS_REJECTED,
)


@dataclass(frozen=True)
class MeasurementArtifacts:
    """Images and masks kept for the response/diagnostic views (never persisted here)."""

    original: np.ndarray
    working: np.ndarray
    leaf_mask: np.ndarray | None
    canvas: np.ndarray | None
    canvas_leaf_mask: np.ndarray | None
    lesion_mask: np.ndarray | None

    @property
    def available(self) -> bool:
        """True when the leaf/lesion stages actually ran (not a rejected image)."""
        return self.canvas is not None and self.leaf_mask is not None


@dataclass(frozen=True)
class PreprocessingOutcome:
    """One validated upload, fully analysed and honestly labelled."""

    status: PublicStatus
    feature_result: FeatureExtractionResult
    pipeline: SegmentationPipelineResult
    artifacts: MeasurementArtifacts
    upload: UploadValidationResult
    model_version: str
    feature_set_version: str = FEATURE_SET_VERSION

    @property
    def values(self) -> np.ndarray | None:
        """The 50 schema-ordered features, or ``None`` for a rejected image."""
        return self.feature_result.values

    @property
    def feature_names(self) -> tuple[str, ...]:
        return FEATURE_NAMES

    @property
    def lesion_reliable(self) -> bool:
        return bool(self.feature_result.lesion_reliable)

    @property
    def lesion_area_percentage(self) -> float | None:
        """Measured lesion area, or ``None`` when the estimate is uncalibrated."""
        if not self.feature_result.lesion_reliable:
            return None
        return self.feature_result.lesion_area_percentage

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.feature_result.warnings

    @property
    def rejections(self) -> tuple[str, ...]:
        return self.feature_result.rejections

    @property
    def missing_features(self) -> tuple[str, ...]:
        return self.feature_result.missing_features

    @property
    def stage_ms(self) -> dict[str, float]:
        return dict(self.pipeline.stage_ms)

    @property
    def segmentation_config_version(self) -> str:
        return self.feature_result.segmentation_config_version

    @property
    def quality_config_version(self) -> str:
        return self.feature_result.quality_config_version

    @property
    def is_rejected(self) -> bool:
        return self.status == STATUS_REJECTED


def _require_service(inference_service: InferenceService | None) -> InferenceService:
    """Refuse to analyse before the production bundle is verified and loaded."""
    if inference_service is not None:
        return inference_service
    try:
        return get_inference_service()
    except InferenceError as exc:
        raise ModelNotLoadedError(
            "The prediction model is not available, so this upload cannot be analysed yet."
        ) from exc


def _check_provenance(
    service: InferenceService, extraction: FeatureExtractionResult
) -> None:
    """A vector from another schema or configuration is not comparable to the model."""
    bundle = service.bundle
    if extraction.schema_version != bundle.feature_set_version:
        raise SchemaMismatchError(
            f"features were extracted with schema {extraction.schema_version!r}, "
            f"the loaded bundle expects {bundle.feature_set_version!r}"
        )
    for label, value, expected in (
        (
            "segmentation_config_sha256",
            extraction.segmentation_config_sha256,
            bundle.segmentation_config_sha256,
        ),
        (
            "quality_config_sha256",
            extraction.quality_config_sha256,
            bundle.quality_config_sha256,
        ),
    ):
        if value and value != expected:
            raise ConfigMismatchError(
                f"features were extracted with {label} {value[:12]}... but the bundle "
                f"pins {expected[:12]}...; this vector is not comparable to the model"
            )


def _public_status(
    pipeline: SegmentationPipelineResult, extraction: FeatureExtractionResult
) -> PublicStatus:
    """Map the pipeline/extractor state onto the three public statuses."""
    if extraction.values is None or extraction.status == STATUS_REJECTED or pipeline.rejected:
        return STATUS_REJECTED
    if (
        extraction.status == STATUS_UNCERTAIN
        or pipeline.uncertain
        or not extraction.lesion_reliable
        or extraction.missing_features
        or extraction.warnings
    ):
        return STATUS_UNCERTAIN
    return STATUS_PREDICTED


def preprocess_upload(
    upload: UploadValidationResult,
    *,
    inference_service: InferenceService | None = None,
    segmentation_config: SegmentationConfig | None = None,
    quality_config: QualityConfig | None = None,
) -> PreprocessingOutcome:
    """Analyse one validated upload with the shared Phase 2 + Phase 3 code path.

    The model is checked **first**, so an unavailable model fails fast with
    ``503 MODEL_NOT_LOADED`` instead of spending CPU on an image that cannot be
    classified. Unreadable bytes (normally caught during upload validation) become
    a typed 422 rather than a crash.
    """
    service = _require_service(inference_service)

    try:
        pipeline = run_segmentation(
            upload.content,
            segmentation_config=segmentation_config or load_segmentation_config(),
            quality_config=quality_config or load_quality_config(),
        )
    except ImageDecodeError as exc:
        # Upload validation normally catches this earlier; keep the failure typed.
        raise UploadValidationError("The uploaded image could not be decoded.") from exc

    extraction = extract_features_from_pipeline(pipeline)
    _check_provenance(service, extraction)

    artifacts = MeasurementArtifacts(
        original=pipeline.oriented.bgr,
        working=pipeline.working.bgr,
        leaf_mask=pipeline.leaf.mask,
        canvas=pipeline.canvas_bgr,
        canvas_leaf_mask=pipeline.canvas_leaf_mask,
        lesion_mask=None if pipeline.lesion is None else pipeline.lesion.mask,
    )

    return PreprocessingOutcome(
        status=_public_status(pipeline, extraction),
        feature_result=extraction,
        pipeline=pipeline,
        artifacts=artifacts,
        upload=upload,
        model_version=service.model_version,
    )
