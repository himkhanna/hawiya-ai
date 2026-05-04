"""Base class and decorator that enforce the tenant-first calling convention.

CLAUDE.md §5: ``tenant_id`` is always the first parameter of any service
method. This module makes that invariant impossible to break by accident.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.tenancy.context import require_tenant_id

P = ParamSpec("P")
R = TypeVar("R")

# requires_tenant expects bound-method args: (self, tenant_id, ...).
_MIN_REQUIRES_TENANT_ARGS = 2


class CrossTenantError(RuntimeError):
    """Service was called with a tenant_id that doesn't match request context."""


class ServiceBase:
    """Stateless service base. State lives in DB or cache."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session


def requires_tenant(
    method: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """Assert that the first arg is the tenant id and matches request context.

    Catches off-by-one bugs in workers / scripts that iterate tenants —
    if the caller passes tenant A but the surrounding context is tenant B,
    we fail loudly rather than silently writing to the wrong partition.
    """

    @functools.wraps(method)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # First positional arg after ``self`` is the tenant id.
        if len(args) < _MIN_REQUIRES_TENANT_ARGS or not isinstance(args[1], UUID):
            raise TypeError(
                f"{method.__qualname__} must take tenant_id: UUID as the first parameter"
            )
        tenant_id: UUID = args[1]
        ctx_tenant = require_tenant_id()
        if tenant_id != ctx_tenant:
            raise CrossTenantError(
                f"explicit tenant {tenant_id} does not match context tenant {ctx_tenant}"
            )
        return await method(*args, **kwargs)

    return wrapper
