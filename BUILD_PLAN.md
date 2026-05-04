# Build Plan — Phase 1 (Weeks 1–6)

> The plan from "empty repo" to "first consumer in production pilot."

This document is the contract for what gets built in Phase 1. It exists to prevent scope drift, keep the team aligned on sequence, and define what "done" means at each step.

If a stakeholder asks you to do something not in this plan, the answer is: "yes, in Phase 2" or "let's discuss whether to swap it in." Don't silently expand the scope.

---

## Phase 1 outcome (what "done" looks like)

A production-deployed Hawiya AI service, running on-premise at Moro Hub, with WizSM as its first integrated consumer, processing real passport documents in a pilot. Specifically:

- ✅ REST API live with `/documents/extract`, `/identity/resolve`, `/persons/*`, `/health`, `/admin/tenants/*`
- ✅ One tenant (WizSM Production) onboarded and operational
- ✅ MRZ extraction at ≥95% accuracy on real customer passport samples
- ✅ Person Registry with deterministic identity matching live
- ✅ Multi-tenant isolation verified by automated tests
- ✅ Audit logging for every AI decision
- ✅ Deployed via Helm to a Kubernetes cluster at Moro Hub
- ✅ WizSM successfully calling `/identity/resolve` from a pilot environment
- ✅ Officer feedback loop closed: at least one full week of pilot operation with no Sev-1/Sev-2 incidents

---

## Pre-week-1: Setup (assume 3–5 days, can run in parallel with week 1)

These can be done by anyone, in parallel. They unblock everyone else.

| Task | Owner | Done means |
|---|---|---|
| Provision Git repo with `main` branch protection | Eng lead | PRs require review + CI pass to merge |
| Provision dev Postgres (Docker Compose) | Backend eng | `make migrate` succeeds locally |
| Provision CI (GitHub Actions or similar) | Eng lead | Lint + tests run on every PR |
| Provision artifact registry for container images | Ops | Internal-only registry reachable from CI |
| Schedule recurring architecture review (weekly, 30 min) | Eng lead | Calendar invite sent |
| Get 100 anonymised passport samples from WizSM team | Product | Samples in `tests/fixtures/` (anonymised — never real PII) |
| Confirm Moro deployment environment specs (CPU, RAM, storage, network) | Ops + Moro team | Doc in `docs/deployment/moro-hub.md` |
| Confirm WizSM auth model (mTLS or OAuth2) | Eng lead + WizSM team | Decision recorded in `API_SPEC.md` §1 |

---

## Week 1 — Skeleton and tenancy foundation

**Goal:** A runnable service with multi-tenancy enforced at the schema and middleware level. No AI yet, no real endpoints. Just the skeleton that everything else hangs off.

| Task | Acceptance criteria |
|---|---|
| Project scaffolding: `pyproject.toml`, `Makefile`, `pre-commit`, `ruff`, `mypy` | `make install`, `make lint`, `make test` all work on a clean clone |
| Base FastAPI app with `/v1/health` and `/v1/ready` | `curl localhost:8000/v1/health` returns 200 |
| Postgres schema for `tenants`, `audit_log` | Alembic migration applies cleanly |
| `TenantContext` + middleware | Requests without `X-Tenant-ID` (and no JWT) return 401 |
| Postgres RLS enabled on `audit_log` | Test verifies cross-tenant query blocked at DB level |
| Structured logging via `structlog`, JSON format | Logs include tenant_id, request_id by default |
| `redact_pii()` helper | Unit-tested on a set of known PII patterns |
| `make seed-dev-tenant` creates a test tenant | Returns a UUID + dev credentials |
| First multi-tenant isolation test passes | `make test-tenancy` green |
| Dockerfile + docker-compose for local dev | `docker compose up` brings up service + Postgres |

**Definition of done for week 1:** A new engineer can clone the repo, run `make install && make migrate && make seed-dev-tenant && make run-dev`, and successfully call `curl -H "X-Tenant-ID: <uuid>" -H "Authorization: Bearer dev" http://localhost:8000/v1/health`.

---

## Week 2 — Document extraction (deterministic path)

**Goal:** Working passport extraction via MRZ + checksums. No identity matching yet.

| Task | Acceptance criteria |
|---|---|
| `extractors/mrz.py` — PassportEye + Tesseract integration | Unit tests pass on 20 synthetic MRZ strings |
| `extractors/validators.py` — ICAO 9303 checksum validation | All 5 checksums implemented and unit-tested |
| `extractors/document_classifier.py` — passport vs other ID detection | Classifies test fixtures correctly |
| `extraction_service.py` — orchestrates the pipeline | Returns structured `ExtractionResult` with confidence per field |
| Schema: `document_extractions` table | Alembic migration applied |
| `POST /v1/documents/extract` endpoint | Accepts multipart upload + JSON, returns extraction |
| Structured error responses | `DOCUMENT_UNREADABLE`, `UNSUPPORTED_DOCUMENT` codes work |
| Audit log entry for every extraction | One row per call, with tenant_id |
| Benchmark script: `make benchmark` | Runs against `tests/fixtures/passports/` and reports accuracy |

**Definition of done for week 2:** `POST /v1/documents/extract` with a real (anonymised) passport image returns correctly extracted, checksum-validated structured data. Accuracy on the fixture set is ≥95%.

**Likely friction:** Tesseract setup on the dev image. PassportEye occasionally misreads `<` as `(` — handle in post-processing. MRZ region detection on phone-camera photos is harder than scanner output — accept lower accuracy on phone photos for Phase 1, target scanner first.

---

## Week 3 — Person Registry and deterministic matching

**Goal:** A Golden Record store, with deterministic identity matching working end-to-end.

| Task | Acceptance criteria |
|---|---|
| Schema: `persons`, `person_identifiers`, `person_name_variants` | Alembic migration applied, indexes correct |
| Postgres RLS enabled on all person tables | Cross-tenant test blocks at DB level |
| `matching/arabic_names.py` — normalisation, phonetic key | Unit tests on common Arabic name variants |
| `matching/deterministic.py` — Emirates ID + passport+DOB matching | Unit tests on positive and negative matches |
| `identity_service.py` — orchestrates extract → match → return | Returns `auto_matched`, `new_record`, or `no_match_no_create` |
| `POST /v1/identity/resolve` endpoint | Multipart and JSON variants work |
| `POST /v1/persons/search` endpoint | Returns ranked candidates |
| `GET /v1/persons/{uuid}` endpoint | Full Person record |
| `POST /v1/persons` endpoint with `POSSIBLE_DUPLICATE` 409 | Triggers when an existing match exists |
| Idempotency middleware | Same `Idempotency-Key` returns same response within 24h |

**Definition of done for week 3:** Submit the same passport twice via `/identity/resolve`. The second call returns `auto_matched` with the same `person_uuid`. Submit a passport with a typo in the number — returns `suggested_match` (or `new_record` depending on threshold). All decisions are in the audit log.

**Likely friction:** Defining the matching threshold defaults. Start with `auto_merge: 0.95, suggest_merge: 0.80, manual_review: 0.55` and tune from real WizSM data in week 5.

---

## Week 4 — Hardening and observability

**Goal:** Production-ready operability. The service is now feature-complete for Phase 1; this week is about making it reliable, observable, and deployable.

| Task | Acceptance criteria |
|---|---|
| OpenTelemetry tracing on every endpoint | Spans visible in local Tempo/Jaeger |
| Prometheus metrics: latency, error rate, match-action distribution | Per-tenant labels |
| Loki log aggregation in dev | Logs queryable by tenant_id |
| Grafana dashboards: service health, per-tenant volume | Dashboards committed to `deploy/grafana/` |
| Rate limiting middleware | Configurable per tenant; default 100 req/min on extract/resolve |
| Helm chart for Kubernetes deployment | `helm install` works against a kind cluster |
| Air-gap installer bundle | `make build-airgap` produces an offline-installable tarball |
| Load test: `scripts/load_test.py` | Service handles 50 RPS sustained without errors |
| Security scan: `bandit`, `pip-audit` clean | No high-severity findings |
| Documentation: `docs/deployment/kubernetes.md` complete | New ops engineer can deploy from scratch |

**Definition of done for week 4:** Deploy to a staging Kubernetes cluster (can be on-prem or sovereign cloud, not necessarily Moro yet). Run a 30-minute load test at 50 RPS. Observe metrics in Grafana. No memory leaks, no error spikes.

---

## Week 5 — Pilot deployment and tuning

**Goal:** Hawiya AI deployed at Moro Hub. WizSM connected. Real passport processing happening with officer oversight.

| Task | Acceptance criteria |
|---|---|
| Moro Hub deployment | Service running at customer environment, accessible from WizSM |
| Production tenant onboarded (`WizSM Production`) | Returns valid `tenant_id`, credentials issued |
| WizSM REST client integrated | WizSM successfully calls `/identity/resolve` |
| Capture device pilot: 1 Regula scanner connected | Officers can scan passports through WizSM UI |
| Threshold tuning from real data | Match thresholds adjusted based on first 100 extractions |
| Officer feedback collected | Log of officer corrections used to identify edge cases |
| Bug triage daily standup | All Sev-1/Sev-2 issues resolved within 24h |

**Definition of done for week 5:** WizSM officers process at least 50 real passport requests through Hawiya AI. Officer correction rate measured. Top 5 failure modes documented.

**Likely friction:** Moro Hub procurement and access. Network firewall rules. Internal DNS. Start ops engagement in week 1 — don't wait until week 5.

---

## Week 6 — Stabilisation and handoff

**Goal:** Service is stable, the team can support it, Phase 2 can start cleanly.

| Task | Acceptance criteria |
|---|---|
| Address all officer feedback from week 5 | Issues triaged, fixes shipped or scheduled |
| Runbook: incident response | `docs/runbooks/incident-response.md` complete |
| Runbook: tenant onboarding | `docs/runbooks/tenant-onboarding.md` complete |
| Runbook: backup and restore | `docs/runbooks/backup-restore.md` complete |
| On-call rotation defined | First on-call engineer trained |
| Phase 1 retrospective | Document lessons learned, scope changes for Phase 2 |
| Phase 2 kickoff | BUILD_PLAN_PHASE_2.md drafted |

**Definition of done for week 6:** Service has run for one continuous week in production (post-pilot) with no Sev-1/Sev-2 incidents. The team is ready to start Phase 2.

---

## What's explicitly NOT in Phase 1

These are deferred to Phase 2 or later. **Saying yes to any of these in Phase 1 will derail the plan.**

- ❌ Probabilistic / fuzzy matching (Phase 2)
- ❌ Visual zone OCR for non-MRZ fields beyond the basics (Phase 2)
- ❌ LLM tiebreaker (Phase 2)
- ❌ Bulk dedup of existing data (Phase 2)
- ❌ Officer review queue UI (Phase 2 — APIs only in Phase 2)
- ❌ Document validation beyond passports (Phase 3)
- ❌ Case summarisation, draft response (Phase 3)
- ❌ Auto-fill into ICP/GDRFA (Phase 3 — and even then, hand-off pattern, not RPA)
- ❌ Second consumer onboarded (Phase 3)
- ❌ Multi-document submission (Phase 3)
- ❌ Webhook callbacks (Phase 2 review)
- ❌ Customer-managed encryption keys / BYOK (Phase 3 review)

---

## Parallel track: demo UI

A standalone React demo application — the sales / officer-experience preview — runs in parallel with the Phase 1 backend build. **This is parallel work, not Phase 1 critical path.**

- Specification: [`docs/demo-ui.md`](./docs/demo-ui.md)
- Owner: dedicated frontend engineer (not the backend team)
- Timeline: weeks 3–6 of Phase 1, behind the backend
- Mock mode shippable independently of any backend; live mode requires the real service

**Hard rule:** do not pull a backend engineer onto the demo UI during Phase 1. The Phase 1 backend timeline is already tight. If you don't have a dedicated frontend engineer, the demo waits until after Phase 1 ships.

---

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Tesseract MRZ accuracy below target on real samples | Medium | Have Regula SDK as upgrade path; budget for licence if needed |
| Moro Hub deployment delayed | High | Start ops engagement week 1, not week 5 |
| WizSM team requests scope additions | High | This document. Point at it. |
| Real passport sample volume too low to tune thresholds | Medium | Generate synthetic data from the 100 fixture samples |
| Tenant-isolation bug ships to production | Low (with mitigation) | RLS + repository pattern + CI tests + code review |
| Auth model not finalised by week 5 | Medium | Lock decision in week 1 architecture review |

---

## Daily and weekly cadence

- **Daily standup** (15 min): blockers only, no status reports
- **Weekly architecture review** (30 min): one decision per week, recorded
- **Weekly demo** (30 min): show real progress to product + WizSM team
- **Bi-weekly retro** (45 min): what's working, what isn't, one action

---

## Before you start: things to confirm with stakeholders this week

These are decisions the engineering team cannot make alone. Get answers in week 1:

1. **Auth model**: mTLS + service JWT, or OAuth2 client credentials? (Affects middleware design.)
2. **Hosting**: Kubernetes at Moro, or a single VM for Phase 1? (Affects deployment story.)
3. **Capture device**: Are we shipping with Regula 70x8 from day 1, or browser upload only for the pilot?
4. **Tenant for the pilot**: Is the pilot a separate tenant from production, or is the pilot in production with limited users?
5. **Audit destination**: Loki internal, customer SIEM, or both?
6. **Licence terms with WizSM**: per-call, flat-fee, or per-tenant? (Doesn't affect Phase 1 code, but affects metering decisions.)

Send these as a written list. Get written answers. Pin them in the team channel.

---

## A note on how to use this plan

This plan is firm on outcomes and approximate on dates. If week 2 takes 8 days because Tesseract is slower to integrate than expected, that's fine — push everything else back a few days. If you can't finish week 4 in week 4, **don't skip to week 5**. Stabilise first.

The plan is wrong if:
- You're in week 3 and haven't talked to the WizSM team yet — go talk to them.
- You're in week 5 and don't have Moro deployment access — escalate immediately.
- You discover a major architectural issue (tenancy not enforceable in some path, MRZ unrecoverable on customer data) — stop, raise it, replan.

Ship the plan, not the ego. If reality changes, the plan changes.
