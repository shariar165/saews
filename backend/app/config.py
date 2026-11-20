"""Application settings, loaded from environment variables (prefix ``EWS_``) or ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EWS_", env_file=PROJECT_ROOT / ".env", extra="ignore")

    app_name: str = "SAEWS — Socio-Academic Early Warning System"
    environment: str = "development"
    demo_mode: bool = True

    # Database: SQLite for the local prototype; set to a postgresql+psycopg:// URL for multi-user deployment.
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'saews.db').as_posix()}"

    # Auth
    jwt_secret: str = "dev-only-change-me-0f6b1c2d9e8a7f3b"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    cookie_name: str = "saews_session"
    cookie_secure: bool = False  # set True behind HTTPS
    rate_limit_enabled: bool = True
    login_rate_limit: str = "10/minute"

    # Risk model / data-quality thresholds (configurable per institution)
    model_dir: str = str(PROJECT_ROOT / "backend" / "app" / "ml" / "artifacts")
    risk_threshold_moderate: float = 0.20
    risk_threshold_high: float = 0.40
    risk_threshold_critical: float = 0.65
    min_data_completeness: float = 0.6
    stale_after_days: int = 21

    # Privacy
    min_group_size: int = 5  # small-cell suppression for de-identified reports
    retention_days: int = 730  # historical risk assessments / closed import batches
    audit_retention_days: int = 365
    max_upload_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
