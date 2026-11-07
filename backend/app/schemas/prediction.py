"""Response schemas for `POST /api/v1/predict` (PRD §15, Phase 4 M8).

These are deliberately a **projection** of
:meth:`app.services.prediction_service.PredictionResult.as_dict`, never the internal
object: no numpy arrays, no pipeline masks, no artifact bytes.

Two shapes are returned:

* :class:`PredictionResponse` — ``status`` is ``predicted`` or ``uncertain`` and a
  disease label exists. ``uncertain`` means the label must be presented as
  unconfirmed (a quality warning, a missing severity or an unreliable lesion);
* :class:`RejectedResponse` — the upload reached the vision pipeline but is not
  analysable. No ``prediction_id``, no artifacts, and nothing is stored in history.

Scores are always ``decision_function`` margins. No field is a probability or a
confidence percentage (decision P-15), and there is no score-based uncertainty
threshold while P-05 remains open.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SeverityName = Literal["Mild", "Moderate", "Severe"]


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactLinks(_StrictResponse):
    """Temporary artifact URLs for this prediction (null when not produced)."""

    original_url: str | None = None
    leaf_mask_url: str | None = None
    lesion_mask_url: str | None = None


class PredictionResponse(_StrictResponse):
    """A predicted or uncertain result that carries a disease label."""

    prediction_id: str = Field(description="UUID of this temporary prediction.")
    status: Literal["predicted", "uncertain"]
    disease: str = Field(description="One of the three supported disease labels.")
    decision_scores: dict[str, float] = Field(
        description="One-vs-rest decision_function values per class. Not probabilities."
    )
    margin: float = Field(
        description="Best minus second-best decision score. Not a confidence value."
    )
    ranking: list[str] = Field(description="Class names, best decision score first.")
    score_kind: Literal["decision_margin"] = "decision_margin"
    score_note: str
    lesion_area_percentage: float | None = Field(
        default=None,
        description="Measured lesion area of the leaf, or null when uncalibrated.",
    )
    lesion_reliable: bool
    severity: SeverityName | None = Field(
        default=None, description="Experimental bucket, or null when it cannot be stated."
    )
    severity_note: str
    severity_disclaimer: str
    severity_reason_code: str | None = None
    severity_method: str
    severity_config_version: str
    severity_config_sha256: str
    warnings: list[str] = Field(default_factory=list)
    rejections: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    artifacts: ArtifactLinks = Field(default_factory=ArtifactLinks)
    model_name: str
    model_version: str
    feature_set_version: str
    segmentation_config_version: str
    quality_config_version: str
    stage_ms: dict[str, float] = Field(default_factory=dict)
    created_at: str = Field(description="ISO-8601 UTC timestamp of the stored record.")
    runtime_storage: Literal["temporary"] = "temporary"


class RejectedResponse(_StrictResponse):
    """An unsuitable image: no prediction, no id, no stored history (PRD §15)."""

    status: Literal["rejected"] = "rejected"
    reason_code: str
    message: str
    runtime_storage: Literal["temporary"] = "temporary"
