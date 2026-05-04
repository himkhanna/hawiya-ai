"""Per-request tenant context, propagated via ``contextvars``.

The middleware sets the context at the start of each request; services and
repositories read it via ``current_tenant_id()`` / ``require_tenant_id()``.
A context manager (``TenantContext``) is provided for scripts and tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from uuid import UUID

_tenant_id_var: ContextVar[UUID | None] = ContextVar("hawiya_tenant_id", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("hawiya_request_id", default=None)


class MissingTenantError(RuntimeError):
    """Raised when a code path requires a tenant but none is set."""


def current_tenant_id() -> UUID | None:
    return _tenant_id_var.get()


def require_tenant_id() -> UUID:
    tid = _tenant_id_var.get()
    if tid is None:
        raise MissingTenantError(
            "No tenant in context. Service methods must run inside a "
            "TenantContext or behind the tenancy middleware."
        )
    return tid


def current_request_id() -> str | None:
    return _request_id_var.get()


def _set_tenant(tenant_id: UUID | None) -> Token[UUID | None]:
    return _tenant_id_var.set(tenant_id)


def _reset_tenant(token: Token[UUID | None]) -> None:
    _tenant_id_var.reset(token)


def _set_request_id(request_id: str | None) -> Token[str | None]:
    return _request_id_var.set(request_id)


def _reset_request_id(token: Token[str | None]) -> None:
    _request_id_var.reset(token)


@contextmanager
def TenantContext(  # noqa: N802 — class-style name for ergonomic `with TenantContext(...)`
    tenant_id: UUID,
    request_id: str | None = None,
) -> Iterator[None]:
    """Bind a tenant (and optional request id) for the duration of a block.

    Use in scripts, background jobs, or tests. The HTTP middleware uses the
    underlying ContextVars directly so it can release them per-request.
    """
    t_token = _set_tenant(tenant_id)
    r_token = _set_request_id(request_id) if request_id is not None else None
    try:
        yield
    finally:
        _tenant_id_var.reset(t_token)
        if r_token is not None:
            _request_id_var.reset(r_token)
