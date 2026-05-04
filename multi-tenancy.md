# Multi-Tenancy Architecture

> Required reading before touching the data layer, services, or auth.

Hawiya AI is multi-tenant by architecture, not by configuration. This means every line of code that touches data assumes a tenant context. Getting this wrong leaks data between customers, and that is the single highest-severity bug we can ship.

This document is the contract for how tenancy works.

---

## 1. What "tenant" means here

A **tenant** is an isolated data partition. One customer environment may host one or many tenants. Examples:

- WizSM Production (PDD visa workflow) — one tenant
- WizSM Staging — separate tenant
- Banking KYC consumer (future) — separate tenant
- Civil Affairs consumer (future) — separate tenant

Tenants share infrastructure (database, service instance, model weights) but never share data. There is no "shared Person Registry" across tenants. A person who is in two tenants exists as two independent Golden Records.

This is intentional. Cross-tenant identity resolution is a regulatory and trust nightmare, and customers explicitly do not want it. If a customer wants federated identity across consumers, they configure all consumers to use the same tenant.

---

## 2. Isolation strategy: shared schema, tenant-scoped rows

We use **row-level tenancy** (every row has `tenant_id`), not schema-per-tenant or database-per-tenant. Reasons:

- Operationally simpler at small-to-medium tenant counts (<100)
- Migrations are atomic across tenants
- Backup, monitoring, and ops tooling stay simple
- Tenant onboarding is instant (insert row in `tenants` table)

Trade-off: we depend on application-layer enforcement for isolation. We mitigate this with:

1. **Database-level row-level security (RLS)** — defence in depth
2. **Repository pattern** — every query goes through a tenant-aware repository
3. **CI gate** — automated tenant-isolation tests run on every PR
4. **Code review** — security reviewer required for any change to data access

If we ever exceed ~100 tenants on one installation, we revisit and consider schema-per-tenant.

---

## 3. The contract

### Every API request carries a tenant identifier

One of the following, in priority order:

1. `tenant_id` claim in the JWT (preferred for OAuth2 client credentials)
2. `X-Tenant-ID` header (for mTLS deployments)

Middleware extracts the tenant identifier and binds it to a `TenantContext` for the duration of the request. Code never reads the tenant from headers or JWT directly — it reads from the context.

### Every database row has a `tenant_id`

```sql
CREATE TABLE persons (
    person_uuid UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    -- ...other columns...
);

CREATE INDEX persons_tenant_lookup ON persons (tenant_id, status, date_of_birth);
```

`tenant_id` is the **first column of every index** that supports lookup. This is non-negotiable for performance — without it, the database can't prune to one tenant's rows.

### Every repository method takes `tenant_id`

```python
class PersonRepository:
    def get(self, tenant_id: UUID, person_uuid: UUID) -> Person | None: ...
    def search(self, tenant_id: UUID, query: SearchQuery) -> list[Person]: ...
    def create(self, tenant_id: UUID, person: NewPerson) -> Person: ...
```

There is no `get_by_uuid(person_uuid)` without `tenant_id`. There is no "admin" path that bypasses tenant scope. Even maintenance scripts run within a tenant context.

### Every service method takes `tenant_id`

```python
class IdentityService:
    def resolve(
        self,
        tenant_id: UUID,
        extraction: DocumentExtraction,
        context: ResolveContext,
    ) -> ResolveResult: ...
```

`tenant_id` is always the first parameter after `self`. This is enforced by:

- A base class `TenantScopedService` with a class-level decorator that fails fast at startup if any public method's first arg isn't `tenant_id`
- A linter rule (custom `ruff` plugin or pre-commit hook)
- Code review

### Database row-level security

Defence in depth. Even if application code forgets, RLS catches it.

```sql
ALTER TABLE persons ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON persons
    USING (tenant_id = current_setting('hawiya.tenant_id')::uuid);
```

The application sets `SET LOCAL hawiya.tenant_id = '...'` at the start of every transaction. If application code forgets a tenant filter, RLS prevents leakage.

This is a backstop, not the primary mechanism. Application-layer enforcement is still required.

---

## 4. Implementation pieces

### `TenantContext` (in `src/hawiya/tenancy/context.py`)

```python
from contextvars import ContextVar
from uuid import UUID
from dataclasses import dataclass

@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    request_id: str
    user_id: str | None = None
    user_role: str | None = None

_current: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)

def current_tenant() -> TenantContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError("No tenant context — code path missing tenant scope")
    return ctx

def set_tenant(ctx: TenantContext) -> None:
    _current.set(ctx)
```

Use `ContextVar` so async tasks inherit context correctly.

### Middleware (in `src/hawiya/tenancy/middleware.py`)

FastAPI middleware that:

1. Extracts tenant_id from JWT or `X-Tenant-ID`
2. Validates the tenant exists and is active
3. Validates the caller is authorised for this tenant
4. Sets `TenantContext`
5. Sets the Postgres session variable for RLS
6. Logs the tenant_id with every log line via structlog binding

### Decorator for service methods

```python
from functools import wraps

def requires_tenant(method):
    @wraps(method)
    def wrapper(self, tenant_id: UUID, *args, **kwargs):
        if not isinstance(tenant_id, UUID):
            raise TypeError(f"{method.__name__}: first arg must be tenant_id (UUID)")
        # Optionally: assert tenant_id matches current_tenant().tenant_id
        return method(self, tenant_id, *args, **kwargs)
    return wrapper
```

### Repository base class

```python
class TenantScopedRepository:
    def __init__(self, session: Session):
        self._session = session

    def _scoped(self, tenant_id: UUID, query):
        """Add tenant filter to any select. Must be called by every public method."""
        return query.where(self.model.tenant_id == tenant_id)
```

---

## 5. CI gate: tenant isolation tests

Every PR runs `make test-tenancy`. This suite verifies:

### Test 1 — Repository never returns cross-tenant rows
For each repository, set up two tenants with overlapping data (same passport number, same DOB). Query as Tenant A. Assert no Tenant B rows in the result.

### Test 2 — Service methods reject mismatched tenant context
Call a service method with `tenant_id=A` while `TenantContext.tenant_id=B`. Assert it raises `TenantMismatchError`.

### Test 3 — RLS catches missing app filter
Drop the application-layer filter (test-only fixture). Run a query under tenant A. Assert RLS still prevents tenant B rows from being returned.

### Test 4 — Audit log is tenant-scoped
Verify every audit entry has `tenant_id` and that audit queries from one tenant cannot see another's rows.

### Test 5 — Idempotency keys are tenant-scoped
Same `Idempotency-Key` from two different tenants must not collide.

These tests are mandatory. A failing tenancy test blocks merge regardless of approvals.

---

## 6. Tenant lifecycle

### Onboarding a new tenant

```bash
# Admin endpoint, requires platform-admin role
POST /v1/admin/tenants
{
  "tenant_name": "WizSM Production",
  "config": {
    "supported_document_types": ["passport", "emirates_id", "gcc_id"],
    "matching_thresholds": {
      "auto_merge": 0.95,
      "suggest_merge": 0.80,
      "manual_review": 0.55
    },
    "retention": {
      "extractions_days": 365,
      "audit_log_years": 7
    },
    "audit_destination": "internal_loki"
  }
}
```

Returns a `tenant_id`. Consumer credentials are issued separately (OAuth2 client registration).

### Suspending a tenant

`PATCH /v1/admin/tenants/{tenant_id}` with `status: suspended`. All requests under that tenant return 403. Data is preserved; can be re-activated.

### Archiving a tenant

`PATCH /v1/admin/tenants/{tenant_id}` with `status: archived`. Data retained per retention policy, then purged. No new requests accepted.

---

## 7. Operational concerns

### Per-tenant metrics

Prometheus labels every metric with `tenant_id`. Dashboards filter by tenant. Alerts can be tenant-scoped.

### Per-tenant rate limits

Default rate limits apply per tenant, not per consumer. A noisy tenant can't starve other tenants.

### Per-tenant retention

Each tenant configures retention for extractions and audit logs separately. A nightly job purges expired data, scoped per tenant.

### Per-tenant audit destinations

Some customers want audit logs written to their own SIEM. The `audit_destination` config supports this — Loki (default), syslog, S3-compatible storage, or a webhook.

---

## 8. What about cross-tenant features later?

We will likely be asked for:

- **Shared models trained on aggregate data** — opt-in only, with documented data-handling policies, and processed in a separate "training" environment, not production tenants.
- **Federated identity** — only by configuring multiple consumers to use the same tenant.
- **Cross-tenant anomaly detection** — possible at the platform level (operational metrics) but never on identity data.

If a customer asks for cross-tenant identity, we say no. This is a brand promise: tenant isolation is absolute.

---

## 9. Common mistakes to avoid

- **Forgetting `tenant_id` in a new query** — caught by repository pattern + RLS + tests.
- **Caching across tenants** — cache keys must include `tenant_id`. Caught by code review.
- **Leaking through joins** — `JOIN`s must include `tenant_id` in the join condition. Caught by code review.
- **Background jobs without tenant context** — every Celery task takes `tenant_id` as the first argument. Without it, the task fails fast.
- **Idempotency keys without tenant scope** — collision risk. The idempotency table primary key is `(tenant_id, idempotency_key)`.
- **Audit logs without tenant_id** — defeats the purpose. Audit writer fails closed if `tenant_id` is missing.

---

## 10. Reading list before working on this

- Postgres RLS docs: <https://www.postgresql.org/docs/16/ddl-rowsecurity.html>
- The `TenantScopedRepository` base class in the codebase
- The tenant isolation test suite in `tests/multi_tenant/`

If after reading you still aren't sure how to make a change tenant-safe, ask before writing the code. Cleaning up a tenant leak in production is much harder than designing it correctly upfront.
