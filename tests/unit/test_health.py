"""Health endpoint and tenancy-middleware behaviour."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from hawiya.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_is_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    # Every response carries a request id, even unauthenticated ones.
    assert resp.headers.get("X-Request-ID")


async def test_protected_endpoint_requires_bearer(client: AsyncClient) -> None:
    # /openapi.json is unauthenticated; any non-exempt path proves the gate.
    resp = await client.get("/v1/persons/00000000-0000-0000-0000-000000000000")
    # No bearer → 401, not 404. Auth happens before routing.
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_protected_endpoint_requires_tenant_header(client: AsyncClient) -> None:
    resp = await client.get(
        "/v1/persons/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TENANT_REQUIRED"


async def test_invalid_tenant_uuid_returns_400(client: AsyncClient) -> None:
    resp = await client.get(
        "/v1/persons/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer dev", "X-Tenant-ID": "not-a-uuid"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TENANT_INVALID"


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    resp = await client.get(
        "/v1/health",
        headers={"X-Request-ID": "req-abc-123"},
    )
    assert resp.headers["X-Request-ID"] == "req-abc-123"
