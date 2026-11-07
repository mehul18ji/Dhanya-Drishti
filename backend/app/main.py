"""FastAPI application entry point.

Phase 4 M2: the verified production bundle is loaded **once** during the application
lifespan and reported truthfully by ``/api/v1/health`` and ``/api/v1/model-info``.
No prediction route exists yet; nothing is trained, and no request loads artifacts.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes_health import router as health_router
from app.api.routes_model_info import router as model_info_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.services import inference_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown.

    The production bundle is loaded here, exactly once per process. A bundle that
    fails verification does **not** stop the API from starting: the app then reports
    ``model_loaded: false`` and every model-dependent endpoint returns 503, which is
    more honest than crashing or pretending a model exists.
    """
    settings = get_settings()
    runtime_dir = settings.resolve_path(settings.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    app.state.inference = None
    app.state.model_loaded = False
    app.state.model_version = None

    try:
        service = inference_service.get_inference_service()
    except (inference_service.InferenceError, OSError) as exc:
        logger.error("model bundle could not be loaded: %s", exc)
    else:
        app.state.inference = service
        app.state.model_loaded = True
        app.state.model_version = service.model_version
        logger.info(
            "model loaded | version=%s | feature_set=%s | classes=%s",
            service.model_version,
            service.bundle.feature_set_version,
            ",".join(service.classes),
        )

    logger.info(
        "%s v%s starting | env=%s | runtime=%s | model_loaded=%s",
        settings.app_name,
        __version__,
        settings.environment,
        runtime_dir,
        app.state.model_loaded,
    )

    yield

    app.state.inference = None
    app.state.model_loaded = False
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
    app.include_router(model_info_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "project": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
            "model_info": f"{settings.api_v1_prefix}/model-info",
        }

    return app


app = create_app()
