"""Async SQLAlchemy session + tenant-aware DB binding.

Pattern:
- A single async engine is created at startup.
- Each request acquires a session via ``get_session`` (FastAPI dependency).
- Before yielding, the session sets ``SET LOCAL app.current_tenant = ...``
  using the tenant from context. Postgres RLS policies key off this GUC.
- ``SET LOCAL`` is scoped to the surrounding transaction; SQLAlchemy's
  AsyncSession runs in an implicit transaction, so the value is released
  automatically at commit/rollback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hawiya.config import get_settings
from hawiya.tenancy.context import current_tenant_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine  # noqa: PLW0603 — process-wide engine singleton
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def _get_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory  # noqa: PLW0603 — process-wide factory singleton
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def set_session_tenant(session: AsyncSession) -> None:
    """Bind the current tenant to the session for RLS enforcement.

    Uses ``set_config(..., is_local := true)`` so the value lives only for
    the current transaction. No tenant in context → raises rather than
    silently exposing all rows.
    """
    tenant_id = current_tenant_id()
    if tenant_id is None:
        raise RuntimeError(
            "set_session_tenant called without a tenant in context. "
            "Repository code must run inside the tenancy middleware or a TenantContext."
        )
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id)},
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a tenant-bound async session."""
    factory = _get_factory()
    async with factory() as session, session.begin():
        await set_session_tenant(session)
        yield session
