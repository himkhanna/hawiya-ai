"""Liveness and readiness probes.

``/v1/health`` is a process liveness check — no auth, no I/O.
``/v1/ready`` verifies the DB is reachable; used by Kubernetes readiness.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text

from hawiya import __version__
from hawiya.db.session import get_engine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/v1/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/v1/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready() -> ReadinessResponse:
    checks: dict[str, str] = {}
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"fail: {type(exc).__name__}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return ReadinessResponse(status=overall, checks=checks)
