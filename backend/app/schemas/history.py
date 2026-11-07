"""Response schemas for the temporary history endpoints (PRD §15/§16, Phase 4 M9).

History is session-scoped: rows and artifact files are wiped at startup, expire
after `HISTORY_EXPIRY_MINUTES`, and disappear on `DELETE /api/v1/history` or on
graceful shutdown.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.prediction import ArtifactLinks, SeverityName

StatusName = Literal["predicted", "uncertain", "rejected"]


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoryItem(_StrictResponse):
    """One stored prediction, exactly as the history page needs it."""

    prediction_id: str
    created_at: str
    expires_at: str
    status: StatusName
    disease: str | None = None
    decision_scores: dict[str, float] = Field(default_factory=dict)
    margin: float | None = None
    severity: SeverityName | None = None
    severity_reason_code: str | None = None
    severity_config_version: str
    lesion_area_percentage: float | None = None
    lesion_reliable: bool
    model_name: str
    model_version: str
    feature_set_version: str
    segmentation_config_version: str
    quality_config_version: str
    warnings: list[str] = Field(default_factory=list)
    rejections: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    stage_ms: dict[str, float] = Field(default_factory=dict)
    artifacts: ArtifactLinks = Field(default_factory=ArtifactLinks)


class HistoryListResponse(_StrictResponse):
    count: int
    items: list[HistoryItem] = Field(default_factory=list)
    runtime_storage: Literal["temporary"] = "temporary"


class HistoryDeleteResponse(_StrictResponse):
    deleted: int = Field(description="Number of history rows removed.")
    runtime_storage: Literal["temporary"] = "temporary"
