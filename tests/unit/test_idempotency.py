"""Idempotency middleware tests.

Builds a minimal Starlette app and exercises the middleware directly so
we test the cache semantics in isolation, then a thin sanity check via
the real FastAPI stack to confirm wiring and ordering.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from hawiya.tenancy.idempotency import (
    IdempotencyMiddleware,
    InMemoryIdempotencyStore,
)

# ---------------------------------------------------------------------------
# Minimal Starlette app: counts how many times the route actually ran.
# ---------------------------------------------------------------------------


class _Counter:
    def __init__(self) -> None:
        self.calls = 0


def _build_app(counter: _Counter, store: InMemoryIdempotencyStore) -> Starlette:
    async def echo(request: Request) -> JSONResponse:
        counter.calls += 1
        body = await request.body()
        return JSONResponse({"received": body.decode("utf-8"), "calls": counter.calls})

    app = Starlette(routes=[Route("/echo", echo, methods=["POST", "GET"])])
    app.add_middleware(IdempotencyMiddleware, store=store)
    return app


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


@pytest.fixture
def counter() -> _Counter:
    return _Counter()


@pytest.fixture
def tenant() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def app(counter: _Counter, store: InMemoryIdempotencyStore) -> Starlette:
    return _build_app(counter, store)


def _headers(tenant: str, key: str | None = None) -> dict[str, str]:
    h = {"X-Tenant-ID": tenant}
    if key:
        h["Idempotency-Key"] = key
    return h


# ---------------------------------------------------------------------------
# Cache semantics
# ---------------------------------------------------------------------------


async def test_no_idempotency_key_passes_through(
    app: Starlette, counter: _Counter, tenant: str
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/echo", headers=_headers(tenant), content=b"hello")
        r2 = await ac.post("/echo", headers=_headers(tenant), content=b"hello")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both reached the route.
    assert counter.calls == 2
    assert r2.json()["calls"] == 2


async def test_get_request_ignored(app: Starlette, counter: _Counter, tenant: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.get("/echo", headers=_headers(tenant, key="abc"))
        r2 = await ac.get("/echo", headers=_headers(tenant, key="abc"))
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert counter.calls == 2


async def test_same_key_same_body_returns_cached(
    app: Starlette, counter: _Counter, tenant: str
) -> None:
    transport = ASGITransport(app=app)
    key = "req-123"
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/echo", headers=_headers(tenant, key), content=b"hello")
        r2 = await ac.post("/echo", headers=_headers(tenant, key), content=b"hello")
    assert r1.status_code == r2.status_code == 200
    assert r1.text == r2.text
    # The route only ran once — second response was served from cache.
    assert counter.calls == 1
    assert r2.json()["calls"] == 1


async def test_same_key_different_body_returns_conflict(
    app: Starlette, counter: _Counter, tenant: str
) -> None:
    transport = ASGITransport(app=app)
    key = "req-456"
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/echo", headers=_headers(tenant, key), content=b"hello")
        r2 = await ac.post("/echo", headers=_headers(tenant, key), content=b"world")
    assert r1.status_code == 200
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert counter.calls == 1  # second never reached the route


async def test_different_keys_both_processed(
    app: Starlette, counter: _Counter, tenant: str
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/echo", headers=_headers(tenant, "k1"), content=b"hello")
        r2 = await ac.post("/echo", headers=_headers(tenant, "k2"), content=b"hello")
    assert counter.calls == 2
    assert r1.json()["calls"] == 1
    assert r2.json()["calls"] == 2


async def test_idempotency_isolated_per_tenant(
    counter: _Counter, store: InMemoryIdempotencyStore
) -> None:
    app = _build_app(counter, store)
    transport = ASGITransport(app=app)
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/echo", headers=_headers(tenant_a, "k"), content=b"x")
        # Same key, different tenant — must not reuse A's cache.
        r2 = await ac.post("/echo", headers=_headers(tenant_b, "k"), content=b"x")
    assert counter.calls == 2
    assert r1.json()["calls"] == 1
    assert r2.json()["calls"] == 2


async def test_invalid_tenant_uuid_passes_through(app: Starlette, counter: _Counter) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/echo",
            headers={"X-Tenant-ID": "not-a-uuid", "Idempotency-Key": "k"},
            content=b"hi",
        )
    assert r.status_code == 200
    assert counter.calls == 1


async def test_expired_entry_is_evicted(
    app: Starlette, counter: _Counter, tenant: str, store: InMemoryIdempotencyStore
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/echo", headers=_headers(tenant, "exp"), content=b"hi")
    # Force-expire the entry.
    for entry in store._entries.values():  # type: ignore[attr-defined]
        entry.expires_at = 0
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r2 = await ac.post("/echo", headers=_headers(tenant, "exp"), content=b"hi")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert counter.calls == 2  # second call wasn't cache-served


# ---------------------------------------------------------------------------
# Sanity check via the real FastAPI app (correct middleware ordering).
# ---------------------------------------------------------------------------


async def test_idempotency_works_through_real_app() -> None:
    """POST /v1/persons returns the same response on a replay with same key."""
    from hawiya.api.dependencies import (
        get_audit_writer,
        get_identifier_repository,
        get_matcher,
        get_person_repository,
        get_session,
    )
    from hawiya.audit.writer import AuditWriter
    from hawiya.main import create_app
    from hawiya.matching.deterministic import DeterministicMatcher

    from .test_identity_service import (
        FakeSession,
        StubIdentifierRepo,
        StubPersonRepo,
    )

    app = create_app()
    session = FakeSession()
    person_repo = StubPersonRepo()
    identifier_repo = StubIdentifierRepo()
    audit = AuditWriter(session)  # type: ignore[arg-type]
    matcher = DeterministicMatcher(
        identifier_repo=identifier_repo,  # type: ignore[arg-type]
        person_repo=person_repo,  # type: ignore[arg-type]
    )

    async def _fake_session():
        yield session

    async def _fake_person_repo():
        yield person_repo

    async def _fake_identifier_repo():
        yield identifier_repo

    async def _fake_matcher():
        yield matcher

    async def _fake_audit():
        yield audit

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_person_repository] = _fake_person_repo
    app.dependency_overrides[get_identifier_repository] = _fake_identifier_repo
    app.dependency_overrides[get_matcher] = _fake_matcher
    app.dependency_overrides[get_audit_writer] = _fake_audit

    tenant = str(uuid.uuid4())
    headers = {
        "Authorization": "Bearer dev",
        "X-Tenant-ID": tenant,
        "Idempotency-Key": "create-mansoori-001",
    }
    body = {"canonical_name_en": "Mohamed Almansoori", "nationality": "ARE"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/v1/persons", headers=headers, json=body)
        r2 = await ac.post("/v1/persons", headers=headers, json=body)

    assert r1.status_code == 201
    assert r2.status_code == 201
    # First call reached the service; second was cache-served. So only one
    # Person object should have been added to person_repo.
    assert len(person_repo.created) == 1
    # Bodies match (same person_uuid in both).
    assert json.loads(r1.text)["person_uuid"] == json.loads(r2.text)["person_uuid"]
