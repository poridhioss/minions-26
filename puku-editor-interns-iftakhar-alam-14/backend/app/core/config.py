"""
Central application settings.

Reads all environment variables from the .env file (or OS environment)
and exposes them as a typed, validated Settings object.

Usage anywhere in the codebase:
    from backend.app.core.config import settings
    print(settings.DATABASE_URL)
"""
from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve the project root (two levels up from this file: core/ → app/ → backend/ → root)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """
    Holds all configuration values for the ML Tracker backend.

    Why BaseSettings?
      • Auto-loads variables from .env (no need for os.getenv everywhere)
      • Type-checks values (e.g. PORT must be int)
      • Raises clear errors at startup if something is missing or wrong type
    """

    # ─── Database ────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        ...,
        description="SQLAlchemy connection string, e.g. postgresql://user:pass@host:5432/db"
    )

    # ─── Security ────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        ...,
        min_length=8,
        description="Secret used to sign tokens. Must be long & random in production."
    )
    # Comma-separated list of valid API keys in .env
    # Example: API_KEYS=key-one,key-two,key-three
    API_KEYS: str = Field(
        default="dev-key-12345",
        description="Comma-separated list of valid API keys for authentication."
    )
    # Token settings (kept here for future JWT support)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=1)

    # ─── MLflow ──────────────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: str = Field(
        default="http://localhost:5000",
        description="URL of the MLflow tracking server."
    )
    MLFLOW_ARTIFACT_ROOT: str = Field(
        default="./mlruns",
        description="Where MLflow stores artifacts locally if no remote store is set."
    )

    # ─── MinIO (S3-compatible object storage) ───────────────────────────
    MINIO_ENDPOINT: str = Field(default="localhost:9000")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin")
    MINIO_SECRET_KEY: str = Field(default="minioadmin")
    MINIO_BUCKET: str = Field(default="artifacts")
    MINIO_SECURE: bool = Field(default=False, description="Use HTTPS for MinIO?")

    # ─── App ─────────────────────────────────────────────────────────────
    APP_NAME: str = Field(default="ML Experiment Tracker")
    APP_VERSION: str = Field(default="0.1.0")
    DEBUG: bool = Field(default=True)
    # Comma-separated list of allowed CORS origins for the frontend
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost",
        description="Comma-separated list of allowed frontend origins."
    )

    # ─── Pydantic config ─────────────────────────────────────────────────
    model_config = SettingsConfigDict(
        # Absolute path to the .env file at the project root
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Helper properties ───────────────────────────────────────────────
    @property
    def api_keys_list(self) -> List[str]:
        """Parse the comma-separated API_KEYS string into a clean list."""
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS string into a clean list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# ─── Singleton pattern ───────────────────────────────────────────────
# @lru_cache makes this function run only ONCE.
# Every place that imports `settings` gets the same object.
@lru_cache
def get_settings() -> Settings:
    """Factory that returns a cached Settings instance."""
    return Settings()


# Module-level singleton — import this everywhere:
#     from backend.app.core.config import settings
settings = get_settings()
