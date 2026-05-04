# CLAUDE.md — Hawiya AI

> **هوية · Identity, verified.**
> Project guidance file for AI coding assistants (Claude Code, Cursor, etc.) working on the Hawiya AI repository.
> **This file is the contract.** If a change conflicts with this file, update this file first, then the code.

---

## 1. Product Context

**Product:** Hawiya AI (هوية) — a sovereign, on-premise identity intelligence platform.

**What it does:** Extracts structured identity data from passports, national IDs, and travel documents; resolves identities into a single Golden Record per person; supports consumer applications with workflow-assist agents. Every decision is logged, scored, and reversible.

**What it is not:**
- Not a workflow platform. Consumers (e.g., WizSM) own workflows; Hawiya provides identity intelligence as a service.
- Not a decision-maker. It prepares, validates, recommends — humans approve sovereign-affecting decisions.
- Not a SaaS. Every deployment is on-prem or sovereign-cloud. Data never leaves the customer environment.

**First customer:** WizSM at the UAE Presidential Diwan, deployed at Moro Hub.
**Target consumers (productised):** Government (visa, civil affairs, tax, licensing), banking (KYC), healthcare, hospitality, real estate.

---

## 2. Non-Negotiable Constraints

These are hard requirements. They define what Hawiya AI is. **No code change may violate them without explicit human approval recorded in a commit message.**

### Sovereignty
- All deployments are on-premise or sovereign-cloud. No SaaS path.
- **No external API calls in the production data path.** Forbidden in production: OpenAI, Anthropic public API, Azure cognitive services, Google Cloud APIs, AWS Bedrock, any third-party identity service.
- All AI components are self-hostable: open-weight models or commercially licensed for on-prem.
- No telemetry to third parties. Logs, metrics, and traces stay inside the customer's environment.
- Container images and model weights must be installable from internal artifact stores. **No assumption of internet access at runtime.**

### Multi-tenancy (THIS IS NON-OPTIONAL)
- Every API call carries a tenant identifier (`X-Tenant-ID` header or JWT claim).
- Every database row includes `tenant_id`. Every index begins with `tenant_id`.
- Every service method takes `tenant_id` as the first parameter.
- **Tenants are fully isolated.** No cross-tenant queries, no cross-tenant matching, no shared Golden Records.
- A tenant-isolation test must exist for every new feature that touches data. CI fails without it.
- Per-tenant configuration: matching thresholds, supported document types, retention, audit destinations.

### Security and audit
- Every AI decision logged with: input hash, output, model + version, confidence, reasoning summary, tenant_id, request_id.
- Every action reversible by an authorised human within the configured retention window.
- PII (passport numbers, names, DOB, nationality, photos) encrypted at rest and in transit.
- **Never logged at INFO level.** Use `redact_pii()`. Sensitive payloads only at DEBUG, and DEBUG is off in production.
- No model training on production data without explicit written customer approval and a documented retention policy.

### Architectural philosophy
- **Deterministic where possible, AI where necessary.** Order of preference: rules + checksums → traditional ML → vision models → LLMs.
- **Human-in-the-loop by default.** Every autonomous action gets a confidence score; below threshold, route to consumer's review queue.
- **Boring tech wins.** PostgreSQL over exotic stores. REST over RPC fashion. Modular monolith over premature microservices.
- **Stable contract.** The public API is the product. Breaking changes are rare, versioned, and announced.

---

## 3. Tech Stack (locked for Phase 1)

Do not introduce alternatives without an architecture review.

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | OCR/ML ecosystem |
| API framework | FastAPI | Type-safe, async-friendly, OpenAPI native |
| Server | Uvicorn / Gunicorn | Standard production combo |
| Validation | Pydantic v2 | Type contracts on the wire |
| Database | PostgreSQL 16 | Reliable, has all the extensions we need |
| DB extensions | `pg_trgm`, `pgvector`, `unaccent` | Fuzzy text, embeddings (Phase 2), diacritic-insensitive |
| MRZ extraction | PassportEye + Tesseract 5 | Deterministic, ICAO-validated, free |
| Visual OCR | PaddleOCR | Strong on Arabic + English, self-hostable |
| Identity matching | Splink | Open-source probabilistic matching |
| LLM (Phase 2+) | Falcon / Jais (UAE), Qwen 2.5 / Llama 3.3 (fallback) | All self-hosted via vLLM |
| Async jobs | Celery + Redis | Standard, well-understood |
| Container | Docker | Standard |
| Orchestration | Kubernetes (on-prem) | Standard |
| Observability | OpenTelemetry + Prometheus + Loki + Grafana | Self-hostable |
| Code style | `ruff` (format + lint), `mypy --strict` | Enforced in CI |

**Phase 2+ additions (do not install in Phase 1):** vLLM, TGI, GPU drivers, LLM weights.

---

## 4. Repository Structure

```
hawiya-ai/
├── CLAUDE.md                     # This file — the contract
├── README.md                     # Engineer onboarding
├── API_SPEC.md                   # REST contract for consumers
├── BUILD_PLAN.md                 # Week-by-week execution plan
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── matching-rules.md
│   ├── multi-tenancy.md          # Required reading before touching data
│   ├── deployment/
│   │   ├── air-gapped.md
│   │   ├── kubernetes.md
│   │   └── single-vm.md
│   ├── integration-guides/
│   │   ├── consumer-onboarding.md
│   │   └── tenant-setup.md
│   └── runbooks/
├── src/
│   └── hawiya/
│       ├── api/                  # FastAPI routers (thin, no business logic)
│       │   ├── documents.py
│       │   ├── persons.py
│       │   ├── identity.py
│       │   ├── admin.py
│       │   └── health.py
│       ├── services/             # Business logic (all take tenant_id)
│       │   ├── extraction_service.py
│       │   ├── identity_service.py
│       │   └── tenant_service.py
│       ├── extractors/           # OCR pipeline
│       │   ├── mrz.py
│       │   ├── visual_zone.py
│       │   ├── document_classifier.py
│       │   └── validators.py
│       ├── matching/             # Identity resolution
│       │   ├── deterministic.py
│       │   ├── probabilistic.py  # Phase 2
│       │   ├── arabic_names.py
│       │   └── llm_tiebreaker.py # Phase 2
│       ├── tenancy/              # Multi-tenant enforcement
│       │   ├── context.py        # Tenant context manager
│       │   ├── decorators.py     # @requires_tenant
│       │   └── middleware.py
│       ├── models/               # Pydantic + SQLAlchemy models
│       ├── db/
│       │   ├── session.py
│       │   ├── migrations/       # Alembic
│       │   └── repositories/     # Per-aggregate repos, all tenant-scoped
│       ├── llm/                  # Self-hosted LLM clients (Phase 2)
│       ├── audit/                # Audit logging — every AI decision
│       ├── security/
│       │   ├── pii.py            # redact_pii() helper
│       │   └── auth.py
│       └── config.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── multi_tenant/             # Tenant isolation tests — CI gate
│   ├── fixtures/                 # Anonymised samples ONLY
│   └── conftest.py
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml        # Local dev only
│   ├── helm/
│   └── air-gap/
├── scripts/
│   ├── benchmark_extraction.py
│   ├── dedupe_existing_data.py
│   └── load_test.py
├── examples/
│   ├── consumer-python/
│   ├── consumer-java/
│   └── consumer-dotnet/
├── apps/
│   └── demo-ui/                  # Reference / sales demo (see docs/demo-ui.md)
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── security.yml
├── pyproject.toml
└── Makefile
```

---

## 5. Coding Conventions

### Style
- Format with `ruff format` (line length 100)
- Lint with `ruff check` (strict)
- Type-check with `mypy --strict` on `src/`
- Imports: absolute only, sorted by `ruff`

### Naming
- Modules: `snake_case`
- Classes: `PascalCase`
- Functions, vars: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: leading underscore

### Patterns
- Service classes are stateless. State lives in DB or cache.
- Dependency injection via FastAPI `Depends`. No global singletons except config.
- **`tenant_id` is always the first parameter** of any service method. Never optional. Enforced by `@requires_tenant` decorator on the service base class.
- No `print()` — use the configured structured logger.
- No silent excepts — catch specific exceptions, log, re-raise or return a typed error.
- Always type-hint function signatures and return types.
- Don't catch `Exception` unless you re-raise.

### API conventions
- All endpoints under `/v1/`
- snake_case in JSON, not camelCase
- Structured errors: `{"error": {"code": "...", "message": "...", "details": {...}, "trace_id": "..."}}`
- `Idempotency-Key` required on POST endpoints that create resources
- `X-Request-ID` propagated end-to-end for tracing
- `X-Tenant-ID` always present (or in JWT claims)

### Database
- Every table has `tenant_id UUID NOT NULL` as the first column after the primary key.
- Every index that touches data starts with `tenant_id`.
- Every `WHERE` clause in a repository method includes `tenant_id`. There are no exceptions.
- Use SQLAlchemy 2.0 style (`select()` not `query()`).
- Migrations via Alembic. No raw schema changes.
- `pg_trgm` for fuzzy name matching. `unaccent` for diacritic handling.

### Logging and PII
- Structured JSON logs.
- **Never log raw passport numbers, full names, or DOB at INFO level.** Use `redact_pii()`.
- Safe to log: tenant_id, request_id, person_uuid, extraction_id, processing_path, confidence scores, model versions.
- DEBUG level may include sensitive payloads but DEBUG is off in production.

---

## 6. Canonical Data Models

These are the source of truth across DB, API, and code. **Every entity is tenant-scoped.**

### `Tenant`
```
tenant_id            UUID PK
tenant_name          VARCHAR
status               ENUM(active, suspended, archived)
config               JSONB    -- thresholds, supported docs, retention
created_at           TIMESTAMP
```

### `Person` (Golden Record per tenant)
```
person_uuid          UUID PK
tenant_id            UUID FK NOT NULL
canonical_name_ar    VARCHAR
canonical_name_en    VARCHAR
date_of_birth        DATE
nationality          CHAR(3)  -- ISO 3166-1 alpha-3
sex                  ENUM(M, F, X)
status               ENUM(active, merged, archived)
merged_into          UUID NULLABLE
created_at           TIMESTAMP
updated_at           TIMESTAMP

-- Index: (tenant_id, status, date_of_birth)
-- Index: (tenant_id, canonical_name_ar) using pg_trgm
```

### `PersonIdentifier`
```
identifier_id        UUID PK
tenant_id            UUID FK NOT NULL
person_uuid          UUID FK
identifier_type      ENUM(passport, emirates_id, gcc_id, prior_passport)
identifier_value     VARCHAR
issuing_country      CHAR(3) NULLABLE
issue_date           DATE NULLABLE
expiry_date          DATE NULLABLE
is_primary           BOOLEAN
source               VARCHAR
confidence           FLOAT
created_at           TIMESTAMP

-- Unique index: (tenant_id, identifier_type, identifier_value) WHERE status=active
```

### `PersonNameVariant`
```
variant_id           UUID PK
tenant_id            UUID FK NOT NULL
person_uuid          UUID FK
name_value           VARCHAR
script               ENUM(arabic, latin, other)
variant_type         ENUM(canonical, transliteration, alias, mrz)
phonetic_key         VARCHAR
```

### `DocumentExtraction`
```
extraction_id        UUID PK
tenant_id            UUID FK NOT NULL
consumer_request_id  VARCHAR        -- Consumer's correlation ID
input_hash           VARCHAR        -- For dedup of identical inputs
document_type        ENUM(passport, emirates_id, gcc_id, residence_permit)
extracted_data       JSONB
confidence_per_field JSONB
checksum_status      ENUM(all_pass, partial, all_fail, n/a)
processing_path      ENUM(mrz_only, mrz_plus_visual, visual_only, vision_fallback)
processing_time_ms   INT
person_uuid          UUID NULLABLE  -- If matched/created
match_action         ENUM(auto_matched, suggested_match, new_record, manual_review, no_match_no_create)
created_at           TIMESTAMP
```

### `MatchDecision`
```
decision_id          UUID PK
tenant_id            UUID FK NOT NULL
candidate_a          UUID
candidate_b          UUID
match_type           ENUM(deterministic, probabilistic, llm_assisted)
confidence           FLOAT
features             JSONB
decision             ENUM(auto_merge, suggest_merge, no_match, manual_review)
reviewed_by          VARCHAR NULLABLE
reviewed_at          TIMESTAMP NULLABLE
review_outcome       ENUM NULLABLE
created_at           TIMESTAMP
```

### `AuditLog`
```
audit_id             UUID PK
tenant_id            UUID FK NOT NULL
request_id           VARCHAR
user_id              VARCHAR NULLABLE  -- consumer's user
endpoint             VARCHAR
input_hash           VARCHAR
output_summary       JSONB
model_versions       JSONB
confidence           FLOAT NULLABLE
processing_path      VARCHAR
decision             VARCHAR NULLABLE
created_at           TIMESTAMP
```

---

## 7. Critical Algorithms

### Document extraction pipeline (deterministic-first)
```
1. Receive image/PDF input
2. Document classifier → passport, Emirates ID, GCC ID, other
3. Pre-process: rotate, deskew, enhance contrast
4. Locate MRZ region (template matching) — passports only
5. Run Tesseract on MRZ with OCR-B model
6. Parse MRZ per ICAO 9303
7. Validate checksums (5 checksums per TD3 passport)
8. If all checksums pass → return structured data, confidence = high
9. If partial → run PaddleOCR on visual zone for cross-check
10. If still unresolved → escalate to vision model (Phase 2+)
11. If all paths fail → return failure with diagnostic, route to manual entry
```

### Identity matching (priority order — stop at first definitive answer)
```
1. Emirates ID exact match → auto_merge (1.00)
2. Passport (number + nationality + DOB) exact → auto_merge (0.99)
3. Passport number exact only → suggest_merge (0.90)
4. Arabic canonical name + DOB + nationality → suggest_merge (0.85)
5. Phonetic name + DOB + nationality → manual_review (0.65)
6. Fuzzy English name + DOB → manual_review (0.55)
7. Below threshold → no_match → create new Person if requested
```

### Arabic name normalisation
- Strip diacritics (tashkeel)
- Normalise alef variants (أ, إ, آ → ا)
- Normalise yaa variants (ى → ي)
- Normalise taa marbuta (ة → ه) for matching only, preserve original
- Handle prefixes: "Al-", "El-", "Bin", "Bint", "Ibn", "Abdul-"
- Generate phonetic key (Soundex-AR or custom)

---

## 8. How Claude (or any AI assistant) Should Work in This Repo

### Always
- Read `API_SPEC.md` before changing any endpoint.
- Read `docs/multi-tenancy.md` before touching data layer or services.
- Tenant-scope every query, every cache key, every audit row.
- Run `make test` before declaring a task done.
- Add a tenant-isolation test for any new data path.
- Update `docs/` when behaviour changes.
- Treat all identity data as PII in every code path.
- Use structured logging via `hawiya.observability.logger`.

### Never
- Add a dependency on an external API (OpenAI, Anthropic public, Azure cognitive, AWS, GCP).
- Commit real documents or real PII to the repo.
- Bypass the audit logger for AI decisions.
- Use `print()` for logging.
- Disable type checking or linting to "make it work".
- Introduce code paths that touch data without tenant scope.
- Rename canonical fields without a migration plan.

### When unsure
- Prefer the deterministic option over the AI option.
- Prefer fewer dependencies.
- Ask before introducing a new core technology (DB, framework, ML library).
- Flag any change to the public API — that needs a contract review.

### Useful commands
```bash
make install          # set up venv + dependencies
make test             # all tests
make test-fast        # unit tests only
make test-tenancy     # multi-tenant isolation tests (CI gate)
make lint             # ruff + mypy
make benchmark        # extraction accuracy benchmark
make dedupe-dry-run   # run identity matcher on existing tenant data, no writes
make run-dev          # local dev server with hot reload
make build-image      # build container image
make build-airgap     # build air-gapped installer bundle
make migrate          # run Alembic migrations
make migrate-create   # create new migration
```

---

## 9. Phased Roadmap

### Phase 1 — Foundation (weeks 1–6) — CURRENT
- REST endpoints: `/documents/extract`, `/identity/resolve`, `/persons/*`, `/health`
- Multi-tenant data model and isolation
- Deterministic OCR via PassportEye + Tesseract
- Person Registry with deterministic matching
- Audit logging
- First consumer integration (WizSM)

**Done when:** 95%+ MRZ extraction accuracy on real samples; <2% duplicate creation rate; tenant isolation verified by automated tests; first consumer in production pilot.

### Phase 2 — Intelligence (weeks 7–14)
- Splink-based probabilistic matching
- PaddleOCR visual zone for non-MRZ fields
- Self-hosted LLM (Falcon/Jais) for ambiguous match decisions
- Bulk dedup tooling for existing tenant data
- Officer review queue API endpoints

### Phase 3 — Workflow Assist (weeks 15+)
- Document validation (supporting documents)
- Case summarisation
- Document classification expansion
- Auto-fill packages for downstream systems
- Second consumer onboarded

---

## 10. Glossary

- **MRZ** — Machine Readable Zone (ICAO 9303)
- **Golden Record** — canonical, deduplicated record for one real person within a tenant
- **Tenant** — an isolated data partition; one customer environment may host many tenants
- **Consumer** — an application that calls Hawiya AI's API (e.g., WizSM)
- **PDD** — Presidential Diwan / Private Department (UAE)
- **ICP / GDRFA** — UAE federal and Dubai immigration authorities
- **Falcon / Jais** — UAE-developed open LLMs (TII / MBZUAI)

---

## 11. Ownership and Approval Gates

- **Product owner:** Hawiya AI core team
- **Consumer integrations:** owned per-consumer (WizSM team owns their integration)
- **Infrastructure:** customer-side ops (Moro Hub for first deployment)

**Security review required (PR cannot merge without approval) for:**
- Any change to PII handling
- Any change to tenancy isolation
- Any change to audit logging
- Any change to authentication or authorisation
- Any new dependency
- Any change to the public API contract

When in doubt, the answer is: **deterministic, sovereign, multi-tenant, audited, reversible.**
