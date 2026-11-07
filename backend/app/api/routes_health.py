"""Health endpoint — verifies the API and model availability (PRD §15)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Backend and model health")
async def health(request: Request) -> HealthResponse:
    """Return backend health.

    ``model_loaded`` becomes true only after the production artifacts are
    loaded at startup (Phase 4). Until then the app honestly reports false
    and ``model_version`` is null — it never fakes a model version.
    """
    return HealthResponse(
        status="ok",
        model_loaded=bool(getattr(request.app.state, "model_loaded", False)),
        model_version=getattr(request.app.state, "model_version", None),
        runtime_storage="temporary",
    )
