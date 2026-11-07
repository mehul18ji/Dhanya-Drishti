"""Domain exceptions and their HTTP mapping.

Every expected failure (invalid upload, no leaf found, unusable model artifacts)
is expressed as an ``AppError`` with a stable ``reason_code`` so the frontend can
react without parsing human-readable text (PRD §15).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for expected application failures."""

    status_code: int = 500
    reason_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, reason_code: str | None = None) -> None:
        if message is not None:
            self.message = message
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.message)


class UploadValidationError(AppError):
    status_code = 422
    reason_code = "INVALID_UPLOAD"
    message = "The uploaded file is not a supported image."


class UnsupportedFileTypeError(UploadValidationError):
    status_code = 415
    reason_code = "UNSUPPORTED_FILE_TYPE"
    message = "Unsupported file type. Allowed types: JPG, JPEG, PNG, WEBP."


class FileTooLargeError(UploadValidationError):
    status_code = 413
    reason_code = "FILE_TOO_LARGE"
    message = "The uploaded file exceeds the maximum allowed size."


class NoLeafFoundError(AppError):
    status_code = 422
    reason_code = "NO_CLEAR_LEAF_FOUND"
    message = "No suitable rice leaf region could be detected. Upload one clear, well-lit leaf."


class ModelNotLoadedError(AppError):
    status_code = 503
    reason_code = "MODEL_NOT_LOADED"
    message = "The prediction model is not available yet."


def register_exception_handlers(app: FastAPI) -> None:
    """Register JSON handlers for ``AppError`` subclasses."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        )
