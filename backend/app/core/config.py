"""Typed application configuration.

All runtime settings come from environment variables / the root `.env` file.
Nothing that must be calibrated (segmentation thresholds, severity cut-offs,
quality limits) is hard-coded here: those belong in `backend/configs/*.yaml`
from Phase 2 onward (PRD §9, §12).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[3] is the repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # `model_dir` is a legitimate setting name, not the Pydantic model namespace.
        protected_namespaces=(),
    )

    app_name: str = "DhanyaDrishti"
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Comma-separated string in the environment; use `cors_origins` for the list.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    max_upload_mb: int = 10
    #: Temporary history TTL (PRD §16). ``history_expiry_minutes`` is the age at
    #: which a record becomes invalid; the sweep interval is how often the
    #: running process actually deletes expired rows and their PNG files.
    history_expiry_minutes: int = 60
    history_sweep_interval_seconds: int = 60

    runtime_dir: Path = BACKEND_DIR / ".runtime"
    model_dir: Path = BACKEND_DIR / "app" / "artifacts" / "production"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated origin allowlist."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in {"development", "dev", "local"}

    def resolve_path(self, value: Path) -> Path:
        """Resolve a configured path relative to the repository root."""
        return value if value.is_absolute() else (REPO_ROOT / value)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one per process)."""
    return Settings()
