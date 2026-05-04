"""ASGI middleware that establishes per-request tenant + request context.

Rules:
- Paths in ``UNAUTHENTICATED_PATHS`` are exempt (health, openapi, docs).
- Every other request must carry an ``X-Tenant-ID`` header that parses as a
  UUID. Phase 1 also requires a bearer token equal to ``settings.dev_bearer_token``;
  this is replaced by mTLS / OAuth2 before production (see API_SPEC.md §1).
- Missing tenant → 401 with the structured error envelope.
- A request id is generated if not provided in ``X-Request-ID`` and is
  echoed in the response headers.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from hawiya.config import get_settings
from hawiya.tenancy.context import (
    _reset_request_id,
    _reset_tenant,
    _set_request_id,
    _set_tenant,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

UNAUTHENTICATED_PATHS: frozenset[str] = frozenset(
    {
        "/v1/health",
        "/v1/ready",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


def _error(code: str, message: str, *, status_code: int, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": {},
                "trace_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


class TenancyMiddleware(BaseHTTPMiddleware):
    """Validate tenant + bearer, then bind tenant/request context for the call."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        if request.url.path in UNAUTHENTICATED_PATHS:
            r_token = _set_request_id(request_id)
            try:
                response = await call_next(request)
            finally:
                _reset_request_id(r_token)
            response.headers["X-Request-ID"] = request_id
            return response

        settings = get_settings()

        auth = request.headers.get("Authorization", "")
        bearer = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
        if bearer != settings.dev_bearer_token:
            return _error(
                "UNAUTHENTICATED",
                "Missing or invalid bearer token.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                request_id=request_id,
            )

        raw_tenant = request.headers.get("X-Tenant-ID")
        if not raw_tenant:
            return _error(
                "TENANT_REQUIRED",
                "X-Tenant-ID header is required.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                request_id=request_id,
            )
        try:
            tenant_id = uuid.UUID(raw_tenant)
        except ValueError:
            return _error(
                "TENANT_INVALID",
                "X-Tenant-ID must be a valid UUID.",
                status_code=status.HTTP_400_BAD_REQUEST,
                request_id=request_id,
            )

        t_token = _set_tenant(tenant_id)
        r_token = _set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            _reset_tenant(t_token)
            _reset_request_id(r_token)

        response.headers["X-Request-ID"] = request_id
        return response
