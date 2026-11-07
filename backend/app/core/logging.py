"""Logging setup for the backend."""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, with a consistent format."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers when uvicorn reloads the app.
    for handler in list(root.handlers):
        if getattr(handler, "_dhanyadrishti", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler._dhanyadrishti = True  # type: ignore[attr-defined]
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
