"""Application configuration.

Settings load from environment variables prefixed with ``HAWIYA_`` and from
a local ``.env`` file in development. There are no global mutable singletons
beyond ``get_settings()``, which is cached.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HAWIYA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.DEV
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://hawiya:hawiya@localhost:5432/hawiya",
        description="Async SQLAlchemy URL (psycopg3 driver).",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://hawiya:hawiya@localhost:5432/hawiya",
        description="Sync SQLAlchemy URL used by Alembic.",
    )

    dev_bearer_token: str = Field(
        default="dev",
        description="Dev-only bearer token accepted alongside X-Tenant-ID. "
        "Phase 1 stub; replaced by mTLS or OAuth2 before production.",
    )

    # ------------------------------------------------------------------ Telemetry
    otel_service_name: str = "hawiya-ai"
    otel_exporter_otlp_endpoint: str = Field(
        default="",
        description="OTLP/gRPC endpoint (e.g. http://tempo:4317). Empty disables export.",
    )
    otel_console_exporter: bool = Field(
        default=False,
        description="If true, also export spans to stdout — useful in dev.",
    )

    # ------------------------------------------------------------------ Limits
    rate_limit_default_per_minute: int = Field(
        default=100,
        description="Default requests/min per tenant on extract/resolve. "
        "Per-tenant overrides live in Tenant.config.",
    )

    @property
    def is_prod(self) -> bool:
        return self.env is Environment.PROD


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
