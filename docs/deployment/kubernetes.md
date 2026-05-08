# Hawiya AI — Kubernetes Deployment Guide

> Audience: ops engineers deploying Hawiya AI on a customer's on-premise
> Kubernetes cluster (e.g. Moro Hub for the WizSM pilot). This guide
> assumes nothing about how the cluster was provisioned.

---

## 1. Prerequisites

| Component | Minimum | Recommended | Notes |
|---|---|---|---|
| Kubernetes | 1.28 | 1.30+ | sovereign / on-prem; airgap-friendly |
| PostgreSQL | 16 | 16 + replica | `pg_trgm`, `unaccent`, `pgvector` extensions enabled (the latter for Phase 2) |
| Helm | 3.13 | 3.16+ | |
| `kubectl` | matching cluster minor | | |
| Container registry | reachable from cluster | mirror inside customer's network for air-gap |
| Optional | Prometheus Operator | for `ServiceMonitor` discovery |
| Optional | Tempo / Jaeger | for distributed tracing |
| Optional | Loki | for centralised JSON logs |

**Resource baseline per replica** (Phase 1, single tenant): 200m CPU, 512Mi memory.
Scale horizontally; the API is stateless, all state lives in Postgres.

---

## 2. Decide your deployment shape

| Aspect | Pilot (Phase 1) | Production |
|---|---|---|
| Replicas | 2 | 3+ across nodes |
| Postgres | single instance | primary + warm standby |
| Auth | dev bearer token | mTLS or OAuth2 (Phase 1 stub OK for pilot) |
| TLS | cluster-issued | customer-managed cert + ingress termination |
| Secrets | inline in values | Sealed Secrets / external-secrets / KMS-CSI |
| Observability | console exporter | Tempo + Loki + Prometheus + Grafana |

---

## 3. Build and push the image

The Dockerfile lives at `deploy/Dockerfile`. Build with the version pinned:

```bash
docker build -t <your-registry>/hawiya-ai:0.1.0 -f deploy/Dockerfile .
docker push <your-registry>/hawiya-ai:0.1.0
```

For air-gapped customers: see §8.

---

## 4. Provision Postgres

Hawiya AI does not run a Postgres-in-cluster pattern in production. Use:
- a customer-managed Postgres (preferred at Moro Hub), OR
- a CloudNativePG cluster CR if Kubernetes-native Postgres is mandated.

Required setup once the database is reachable:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS btree_gin;  -- needed by composite GIN indexes
-- pgvector is Phase 2 but no harm enabling now:
CREATE EXTENSION IF NOT EXISTS vector;
```

Create a database role and a database for Hawiya AI. The role needs CREATE,
CONNECT, USAGE on the schema. **Run RLS as the table owner**: Postgres
RLS only applies to non-superuser sessions, and `FORCE ROW LEVEL SECURITY`
is set in our migrations so even the owner is bound. Verify with the
multi-tenant isolation test (see §7).

Build the DSN: `postgresql+psycopg://<user>:<pw>@<host>:5432/<db>`.

---

## 5. Create secrets

The chart supports two patterns. Production should always use the first.

### 5a. Reference existing secrets (recommended)

```bash
# Database DSN. Both async and sync URLs (Alembic uses sync).
kubectl create secret generic hawiya-database \
  --from-literal=dsn='postgresql+psycopg://hawiya:<pw>@hawiya-db:5432/hawiya' \
  --from-literal=dsn-sync='postgresql+psycopg://hawiya:<pw>@hawiya-db:5432/hawiya' \
  -n hawiya

# Bearer token (Phase 1 stub auth — replace with mTLS / OAuth2 before going live).
kubectl create secret generic hawiya-auth \
  --from-literal=bearer-token='<32 random chars>' \
  -n hawiya
```

Then point the chart at them:

```yaml
# production-values.yaml
secrets:
  existingDatabaseSecret: hawiya-database
  existingAuthSecret: hawiya-auth
```

### 5b. Inline (dev / staging only)

The chart will create its own secrets from `secrets.databaseUrl` etc. **Never
commit a real production DSN to a values file.**

---

## 6. Run migrations

Migrations are in `src/hawiya/db/migrations/`. Run them via a one-shot Job
before bringing the API up:

```bash
kubectl run hawiya-migrate \
  --image=<your-registry>/hawiya-ai:0.1.0 \
  --rm -i --restart=Never \
  --env="HAWIYA_DATABASE_URL_SYNC=$(kubectl get secret hawiya-database -o jsonpath='{.data.dsn-sync}' | base64 -d)" \
  -- alembic upgrade head
```

Each migration enables RLS on its tables. The first migration creates the
`tenants` and `audit_log` tables; the second adds `document_extractions`;
the third adds the Person Registry plus `pg_trgm` and `unaccent` extensions.

---

## 7. Install the chart

```bash
helm install hawiya deploy/helm/hawiya-ai \
  -f production-values.yaml \
  --namespace hawiya \
  --create-namespace
```

Smoke test (port-forward first if no Ingress):

```bash
kubectl -n hawiya port-forward svc/hawiya 8000:80

# Liveness — no auth needed
curl http://localhost:8000/v1/health
# {"status":"ok","version":"0.1.0"}

# Readiness — also checks DB
curl http://localhost:8000/v1/ready
# {"status":"ok","checks":{"database":"ok"}}

# Auth gate
curl -i http://localhost:8000/v1/persons/00000000-0000-0000-0000-000000000000
# HTTP/1.1 401 ... UNAUTHENTICATED
```

The multi-tenant RLS isolation test under `tests/multi_tenant/` is the
contractual gate. Run it against a copy of the customer's Postgres
(testcontainers spawns its own, but you can also point it at a sandbox
DB via env vars). It verifies cross-tenant reads/writes are blocked at
the database layer — not just by app code.

---

## 8. Air-gapped deployments

Hawiya AI assumes **no internet at runtime** (CLAUDE.md §2). Bundle the
artifacts you need into an installer tarball:

```bash
make build-airgap
# → dist/hawiya-ai-airgap-0.1.0.tar.gz
```

The bundle contains:
- The container image (saved with `docker save`)
- The Helm chart (`helm package`)
- The Python wheels for offline `pip install` (Phase 2 LLM workers)
- An install script that takes a registry hostname

On the air-gapped side:

```bash
tar -xf hawiya-ai-airgap-0.1.0.tar.gz
./install.sh --registry your-internal.registry.local
```

> **Phase 1 status:** the air-gap installer is scaffolded but not
> production-grade. Treat it as a starting point; week 5 of BUILD_PLAN
> hardens it for Moro Hub.

---

## 9. Observability

### Metrics (Prometheus)

Enable the chart's `ServiceMonitor`:

```yaml
serviceMonitor:
  enabled: true
  namespace: monitoring
  labels:
    release: kube-prometheus-stack   # match your operator's selector
```

Custom domain metrics carry a `tenant_id` label per CLAUDE.md §4:
- `hawiya_extractions_total{tenant_id, checksum_status, processing_path}`
- `hawiya_extraction_failures_total{tenant_id, reason}`
- `hawiya_extraction_duration_seconds{tenant_id}` (histogram)
- `hawiya_match_actions_total{tenant_id, action}`
- `hawiya_rate_limited_total{tenant_id, endpoint_class}`

### Tracing (OTLP/gRPC)

Set `app.otel.exporterEndpoint` to your Tempo or Jaeger collector:

```yaml
app:
  otel:
    serviceName: hawiya-ai
    exporterEndpoint: http://tempo.observability:4317
```

`/v1/health`, `/v1/ready`, and `/metrics` are excluded from traces to
keep the signal clean.

### Logs (Loki)

The application emits **structured JSON logs to stdout**. Configure your
log shipper (Promtail, Fluent Bit, Vector, etc.) to forward stdout from
the `api` container. Every log record carries `tenant_id` and
`request_id` so queries like
`{namespace="hawiya"} | json | tenant_id="<uuid>"` work out of the box.

PII is never logged at INFO. Don't change `HAWIYA_LOG_LEVEL` to `DEBUG`
in production.

### Local dashboards

A reference Grafana dashboard ships at
`deploy/observability/grafana/dashboards/service-health.json`. Import it
into the customer's Grafana, or run the local stack:

```bash
docker compose --profile obs up
# Grafana on http://localhost:3000 (anonymous admin)
```

---

## 10. Rolling upgrade procedure

1. Bump `image.tag` in `production-values.yaml` and merge to main.
2. Run any new migrations as a one-shot Job (§6) **before** rolling pods.
   Migrations are forward-compatible by convention; the previous image
   keeps working until pods are replaced.
3. `helm upgrade hawiya deploy/helm/hawiya-ai -f production-values.yaml`
4. Watch readiness probes: `kubectl rollout status deploy/hawiya`
5. Verify `/v1/health` and a sample `POST /v1/identity/resolve`.
6. Keep the previous image tag pinned in your registry for rollback.

---

## 11. Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Pods CrashLoopBackOff with `cannot connect to database` | DSN secret wrong or Postgres unreachable | `kubectl exec` into a debug pod and `psql` the DSN |
| 401 on every request | Bearer token rotated but secret not redeployed | Recreate `hawiya-auth` and `kubectl rollout restart` |
| 422 `IDEMPOTENCY_KEY_CONFLICT` after a redeploy | In-memory idempotency cache doesn't survive restart | Expected — the cache is process-local in Phase 1. Postgres-backed store lands in a follow-up |
| 5xx burst during migration | Pods rolled before `alembic upgrade head` finished | Always run migrations as a Job to completion first |
| Tracing silent | OTLP endpoint unreachable or wrong port | Check `tempo:4317` is on the same network and accepts gRPC |

---

## 12. What's NOT in this guide

These belong in dedicated runbooks (BUILD_PLAN week 6):

- Backup and restore (`docs/runbooks/backup-restore.md`)
- Incident response (`docs/runbooks/incident-response.md`)
- Tenant onboarding (`docs/runbooks/tenant-onboarding.md`)

---

## Appendix: contractual reminders from CLAUDE.md

- No external API calls in the production data path. No OpenAI / Azure /
  AWS / Anthropic public APIs.
- Every API call carries `X-Tenant-ID`. Every database row carries
  `tenant_id`. RLS at the DB layer is the last line of defence — keep
  the multi-tenant isolation test green in CI.
- PII never appears in INFO logs. `redact_pii()` is the only safe path.
- Every AI decision must land in `audit_log`. Every match writes a
  `match_decisions` row.
