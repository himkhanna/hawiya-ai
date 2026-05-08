"""Per-tenant rate limiting (token bucket).

Phase 1 ships an in-memory bucket per ``(tenant_id, endpoint_class)``.
Replaceable with a Redis-backed implementation behind ``RateLimiter``
for multi-instance deploys (BUILD_PLAN week 4 hardening).

Configuration:
- Default rate from ``settings.rate_limit_default_per_minute`` (Phase 1: 100).
- Per-tenant overrides live in ``Tenant.config['rate_limit'][endpoint_class]``;
  the middleware doesn't know about ``Tenant`` directly — services pass the
  resolved limit in via a callable. Until the lookup is wired, every tenant
  gets the default.

Endpoint classes:
- ``extract`` — covers ``/v1/documents/extract`` and ``/v1/identity/resolve``
  (the OCR-heavy paths CLAUDE.md cares about).
- ``read`` — covers GET ``/v1/persons/{uuid}`` and search.
- ``other`` — everything else (currently no limit).

429 response carries a ``Retry-After`` header in seconds.
"""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from hawiya.config import get_settings
from hawiya.observability.logger import get_logger
from hawiya.observability.metrics import RATE_LIMITED_TOTAL

log = get_logger("hawiya.rate_limit")

# Path-prefix → endpoint-class mapping.
_ENDPOINT_CLASSES: tuple[tuple[str, str], ...] = (
    ("/v1/documents/extract", "extract"),
    ("/v1/identity/resolve", "extract"),
    ("/v1/persons/search", "read"),
    ("/v1/persons", "read"),
)


def classify_endpoint(path: str) -> str | None:
    """Return the endpoint-class for ``path`` or None if not rate-limited."""
    for prefix, klass in _ENDPOINT_CLASSES:
        if path == prefix or path.startswith(prefix + "/"):
            return klass
    return None


@dataclass
class _Bucket:
    """A token bucket. Tokens regenerate continuously at ``rate_per_sec``."""

    capacity: float
    tokens: float
    rate_per_sec: float
    last_refill: float

    def take(self, now: float) -> float | None:
        """Consume one token. Returns None on success, or seconds-until-retry."""
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return None
        deficit = 1.0 - self.tokens
        return deficit / self.rate_per_sec if self.rate_per_sec > 0 else math.inf


class RateLimiter:
    """In-memory limiter. Buckets are keyed by ``(tenant, endpoint_class)``."""

    def __init__(self, *, default_per_minute: int) -> None:
        self.default_per_minute = default_per_minute
        self._buckets: dict[tuple[uuid.UUID, str], _Bucket] = {}

    def _bucket_for(self, tenant_id: uuid.UUID, endpoint_class: str, now: float) -> _Bucket:
        key = (tenant_id, endpoint_class)
        bucket = self._buckets.get(key)
        if bucket is not None:
            return bucket
        capacity = float(self.default_per_minute)
        bucket = _Bucket(
            capacity=capacity,
            tokens=capacity,
            rate_per_sec=capacity / 60.0,
            last_refill=now,
        )
        self._buckets[key] = bucket
        return bucket

    def check(
        self, tenant_id: uuid.UUID, endpoint_class: str, *, now: float | None = None
    ) -> float | None:
        """Returns None if allowed, else seconds-until-retry (>= 1)."""
        t = now if now is not None else time.monotonic()
        retry = self._bucket_for(tenant_id, endpoint_class, t).take(t)
        if retry is None:
            return None
        return max(1.0, math.ceil(retry))

    def clear(self) -> None:
        self._buckets.clear()


def _rate_limited_response(retry_after: int, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Per-tenant rate limit exceeded.",
                "details": {"retry_after_seconds": retry_after},
                "trace_id": request_id,
            }
        },
        headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply ``RateLimiter`` to classified endpoints. Skips unauth'd paths."""

    def __init__(self, app: ASGIApp, *, limiter: RateLimiter | None = None) -> None:
        super().__init__(app)
        self.limiter = limiter or RateLimiter(
            default_per_minute=get_settings().rate_limit_default_per_minute
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        endpoint_class = classify_endpoint(request.url.path)
        if endpoint_class is None:
            return await call_next(request)

        raw_tenant = request.headers.get("X-Tenant-ID")
        if not raw_tenant:
            # Tenancy middleware will reject; nothing to rate-limit.
            return await call_next(request)
        try:
            tenant_id = uuid.UUID(raw_tenant)
        except ValueError:
            return await call_next(request)

        retry = self.limiter.check(tenant_id, endpoint_class)
        if retry is not None:
            RATE_LIMITED_TOTAL.labels(tenant_id=str(tenant_id), endpoint_class=endpoint_class).inc()
            request_id = request.headers.get("X-Request-ID") or ""
            log.info(
                "rate_limited",
                tenant_id=str(tenant_id),
                endpoint_class=endpoint_class,
                retry_after=int(retry),
            )
            return _rate_limited_response(int(retry), request_id)

        return await call_next(request)
