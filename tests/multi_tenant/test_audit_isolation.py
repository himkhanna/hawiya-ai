"""Tenant-isolation test — the CI gate.

Spins up a real Postgres via testcontainers, applies migrations, inserts
audit rows for two tenants, then verifies that selecting under tenant A
returns only A's rows. RLS is the last line of defence: even if app code
forgets a WHERE clause, this test fails when isolation breaks.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from hawiya.config import get_settings

try:
    from testcontainers.postgres import PostgresContainer
except ImportError:  # pragma: no cover
    PostgresContainer = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

pytestmark = [pytest.mark.tenancy, pytest.mark.integration]


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    """Provision a throwaway Postgres 16 container and apply migrations."""
    if PostgresContainer is None:
        pytest.skip("testcontainers not installed")

    with PostgresContainer("postgres:16-alpine") as pg:
        sync_url = pg.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        async_url = sync_url  # psycopg3 dialect handles both

        # Migrations import settings → ensure they target the container DB.
        os.environ["HAWIYA_DATABASE_URL_SYNC"] = sync_url
        os.environ["HAWIYA_DATABASE_URL"] = async_url
        get_settings.cache_clear()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", sync_url)
        command.upgrade(cfg, "head")

        yield async_url


@pytest.fixture
async def session(pg_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(pg_url, future=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s
    finally:
        await engine.dispose()


async def _set_tenant(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id) if tenant_id else ""},
    )


async def test_rls_blocks_cross_tenant_reads(session: AsyncSession) -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # Bypass RLS to seed both tenants. We use the table owner privilege via
    # an explicit role-less insert under SET LOCAL row_security = off, which
    # the test role (created by testcontainers as DB owner) is allowed to do.
    async with session.begin():
        await session.execute(text("SET LOCAL row_security = off"))
        await session.execute(
            text(
                "INSERT INTO tenants (tenant_id, tenant_name, status, config) "
                "VALUES (:a, 'Tenant A', 'active', '{}'::jsonb), "
                "       (:b, 'Tenant B', 'active', '{}'::jsonb)"
            ),
            {"a": str(tenant_a), "b": str(tenant_b)},
        )
        await session.execute(
            text(
                "INSERT INTO audit_log (audit_id, tenant_id, request_id, endpoint) "
                "VALUES (:id1, :a, 'r-a', '/v1/identity/resolve'), "
                "       (:id2, :b, 'r-b', '/v1/identity/resolve')"
            ),
            {
                "id1": str(uuid.uuid4()),
                "id2": str(uuid.uuid4()),
                "a": str(tenant_a),
                "b": str(tenant_b),
            },
        )

    # Acting as tenant A — must only see A's audit row.
    async with session.begin():
        await _set_tenant(session, tenant_a)
        rows_a = (await session.execute(text("SELECT tenant_id FROM audit_log"))).scalars().all()
    assert len(rows_a) == 1
    assert uuid.UUID(str(rows_a[0])) == tenant_a

    # Acting as tenant B — must only see B's audit row.
    async with session.begin():
        await _set_tenant(session, tenant_b)
        rows_b = (await session.execute(text("SELECT tenant_id FROM audit_log"))).scalars().all()
    assert len(rows_b) == 1
    assert uuid.UUID(str(rows_b[0])) == tenant_b


async def test_rls_blocks_cross_tenant_writes(session: AsyncSession) -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    async with session.begin():
        await session.execute(text("SET LOCAL row_security = off"))
        await session.execute(
            text(
                "INSERT INTO tenants (tenant_id, tenant_name, status, config) "
                "VALUES (:a, :na, 'active', '{}'::jsonb), "
                "       (:b, :nb, 'active', '{}'::jsonb)"
            ),
            {
                "a": str(tenant_a),
                "b": str(tenant_b),
                "na": f"A-{tenant_a}",
                "nb": f"B-{tenant_b}",
            },
        )

    # Acting as tenant A, attempt to insert an audit row for tenant B.
    # The WITH CHECK clause must reject this.
    with pytest.raises(Exception):  # noqa: B017 — psycopg raises a driver-level error
        async with session.begin():
            await _set_tenant(session, tenant_a)
            await session.execute(
                text(
                    "INSERT INTO audit_log (audit_id, tenant_id, request_id, endpoint) "
                    "VALUES (:id, :b, 'evil', '/v1/identity/resolve')"
                ),
                {"id": str(uuid.uuid4()), "b": str(tenant_b)},
            )


async def test_no_tenant_set_returns_zero_rows(session: AsyncSession) -> None:
    """When the GUC is unset/empty, RLS denies all rows — never exposes them."""
    tenant_a = uuid.uuid4()
    async with session.begin():
        await session.execute(text("SET LOCAL row_security = off"))
        await session.execute(
            text(
                "INSERT INTO tenants (tenant_id, tenant_name, status, config) "
                "VALUES (:a, :na, 'active', '{}'::jsonb)"
            ),
            {"a": str(tenant_a), "na": f"A-{tenant_a}"},
        )
        await session.execute(
            text(
                "INSERT INTO audit_log (audit_id, tenant_id, request_id, endpoint) "
                "VALUES (:id, :a, 'r', '/v1/identity/resolve')"
            ),
            {"id": str(uuid.uuid4()), "a": str(tenant_a)},
        )

    async with session.begin():
        # Do NOT set app.current_tenant.
        rows = (await session.execute(text("SELECT tenant_id FROM audit_log"))).scalars().all()
    assert rows == []
