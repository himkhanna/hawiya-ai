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

    @property
    def is_prod(self) -> bool:
        return self.env is Environment.PROD


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
