"""Rate-limiter unit + middleware tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from hawiya.tenancy.rate_limit import (
    RateLimiter,
    RateLimitMiddleware,
    classify_endpoint,
)

# ---------------------------------------------------------------------------
# classify_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/v1/documents/extract", "extract"),
        ("/v1/identity/resolve", "extract"),
        ("/v1/persons", "read"),
        ("/v1/persons/abc-123", "read"),
        ("/v1/persons/search", "read"),
        ("/v1/health", None),
        ("/v1/ready", None),
        ("/metrics", None),
        ("/totally/unknown", None),
    ],
)
def test_classify_endpoint(path: str, expected: str | None) -> None:
    assert classify_endpoint(path) == expected


# ---------------------------------------------------------------------------
# RateLimiter token bucket
# ---------------------------------------------------------------------------


def test_first_n_requests_allowed_then_throttled() -> None:
    limiter = RateLimiter(default_per_minute=3)
    tenant = uuid.uuid4()
    now = 1000.0
    # Bucket starts full at capacity=3 → first 3 succeed.
    assert limiter.check(tenant, "extract", now=now) is None
    assert limiter.check(tenant, "extract", now=now) is None
    assert limiter.check(tenant, "extract", now=now) is None
    # Fourth must be throttled with positive retry-after.
    retry = limiter.check(tenant, "extract", now=now)
    assert retry is not None
    assert retry >= 1


def test_tokens_regenerate_over_time() -> None:
    limiter = RateLimiter(default_per_minute=60)  # 1 per second
    tenant = uuid.uuid4()
    now = 1000.0
    # Drain the bucket.
    for _ in range(60):
        assert limiter.check(tenant, "extract", now=now) is None
    assert limiter.check(tenant, "extract", now=now) is not None  # throttled
    # Wait 1.5s — at least one token regenerates.
    assert limiter.check(tenant, "extract", now=now + 1.5) is None


def test_buckets_isolated_per_tenant() -> None:
    limiter = RateLimiter(default_per_minute=1)
    a = uuid.uuid4()
    b = uuid.uuid4()
    now = 0.0
    assert limiter.check(a, "extract", now=now) is None
    # A is now exhausted.
    assert limiter.check(a, "extract", now=now) is not None
    # B should still have its own full bucket.
    assert limiter.check(b, "extract", now=now) is None


def test_buckets_isolated_per_endpoint_class() -> None:
    limiter = RateLimiter(default_per_minute=1)
    tenant = uuid.uuid4()
    now = 0.0
    assert limiter.check(tenant, "extract", now=now) is None
    assert limiter.check(tenant, "extract", now=now) is not None
    # Different endpoint class → separate bucket.
    assert limiter.check(tenant, "read", now=now) is None


# ---------------------------------------------------------------------------
# Middleware behaviour
# ---------------------------------------------------------------------------


def _make_app(limiter: RateLimiter) -> Starlette:
    async def extract_route(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def health_route(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[
            Route("/v1/documents/extract", extract_route, methods=["POST"]),
            Route("/v1/health", health_route, methods=["GET"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    return app


@pytest.fixture
def tenant() -> str:
    return str(uuid.uuid4())


async def test_middleware_allows_under_limit(tenant: str) -> None:
    limiter = RateLimiter(default_per_minute=3)
    app = _make_app(limiter)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(3):
            r = await ac.post("/v1/documents/extract", headers={"X-Tenant-ID": tenant})
            assert r.status_code == 200


async def test_middleware_429_with_retry_after(tenant: str) -> None:
    limiter = RateLimiter(default_per_minute=1)
    app = _make_app(limiter)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/v1/documents/extract", headers={"X-Tenant-ID": tenant})
        r2 = await ac.post("/v1/documents/extract", headers={"X-Tenant-ID": tenant})
    assert r1.status_code == 200
    assert r2.status_code == 429
    assert r2.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r2.headers["Retry-After"]) >= 1


async def test_middleware_skips_unclassified_paths(tenant: str) -> None:
    limiter = RateLimiter(default_per_minute=1)
    app = _make_app(limiter)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # /v1/health isn't rate-limited even after exhausting the extract bucket.
        for _ in range(5):
            r = await ac.get("/v1/health", headers={"X-Tenant-ID": tenant})
            assert r.status_code == 200


async def test_middleware_passes_through_when_tenant_missing() -> None:
    limiter = RateLimiter(default_per_minute=0)  # would deny everything
    app = _make_app(limiter)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # No X-Tenant-ID → middleware doesn't apply (tenancy will reject downstream).
        r = await ac.post("/v1/documents/extract")
    assert r.status_code == 200  # our stub route succeeds


async def test_middleware_passes_through_on_invalid_tenant_uuid() -> None:
    limiter = RateLimiter(default_per_minute=0)
    app = _make_app(limiter)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/v1/documents/extract", headers={"X-Tenant-ID": "not-a-uuid"})
    assert r.status_code == 200
