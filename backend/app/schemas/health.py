"""Response schemas for the health endpoint (PRD §15)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Backend and model availability."""

    status: Literal["ok"] = "ok"
    model_loaded: bool = Field(
        description="True once production model artifacts are loaded at startup."
    )
    model_version: str | None = Field(
        default=None,
        description="Version of the loaded model, or null when no model is available.",
    )
    runtime_storage: Literal["temporary"] = Field(
        default="temporary",
        description="History and images live only in temporary runtime storage.",
    )
