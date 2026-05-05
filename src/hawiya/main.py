"""FastAPI application factory.

Wires logging, the tenancy middleware, and routers. Kept thin: business
logic lives in services, not here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hawiya import __version__
from hawiya.api import documents, health, identity, persons
from hawiya.config import get_settings
from hawiya.observability.logger import configure_logging, get_logger
from hawiya.tenancy.context import current_request_id
from hawiya.tenancy.idempotency import IdempotencyMiddleware
from hawiya.tenancy.middleware import TenancyMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("hawiya.startup")
    settings = get_settings()
    log.info("startup", env=settings.env, version=__version__)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Hawiya AI",
        version=__version__,
        description="Sovereign, on-premise identity intelligence.",
        lifespan=lifespan,
    )

    # Order matters: IdempotencyMiddleware is added FIRST so TenancyMiddleware
    # ends up OUTSIDE it (FastAPI prepends to user_middleware). Tenancy auth
    # runs first; idempotency only sees authenticated requests.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(TenancyMiddleware)

    @app.exception_handler(Exception)
    async def _unhandled_exception(
        request: Request,
        _exc: Exception,
    ) -> JSONResponse:
        log = get_logger("hawiya.error")
        log.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                    "trace_id": current_request_id() or "",
                }
            },
        )

    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(identity.router)
    app.include_router(persons.router)
    return app


app = create_app()
