"""Multi-tenancy enforcement.

Every API call carries a tenant identifier. Every service method takes
``tenant_id`` as its first parameter. Every DB query is scoped by tenant.
See ``docs/multi-tenancy.md``.
"""

from hawiya.tenancy.context import (
    TenantContext,
    current_request_id,
    current_tenant_id,
    require_tenant_id,
)

__all__ = [
    "TenantContext",
    "current_request_id",
    "current_tenant_id",
    "require_tenant_id",
]
