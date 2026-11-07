"""FastAPI application entry point.

Phase 0: application factory, configuration, logging, CORS and a health
endpoint. No model, no prediction route — those arrive in Phases 3-4.
Run locally with:

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes_health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown.

    Phase 0 only prepares the runtime directory. Model artifacts are loaded
    here in Phase 4; they are never trained or loaded during a request.
    """
    settings = get_settings()
    runtime_dir = settings.resolve_path(settings.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Honest initial state: no production model exists yet.
    app.state.model_loaded = False
    app.state.model_version = None

    logger.info(
        "%s v%s starting | env=%s | runtime=%s",
        settings.app_name,
        __version__,
        settings.environment,
        runtime_dir,
    )

    yield

    logger.info("%s shutting down", settings.app_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=(
            "Academic prototype for rice-leaf disease analysis. "
            "Supports Bacterial Leaf Blight, Brown Spot and Leaf Smut only. "
            "Not professional agricultural advice."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "project": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    return app


app = create_app()
