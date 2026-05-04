# Hawiya AI

> **هوية · Identity, verified.**
> Sovereign, on-premise identity intelligence platform for governments and regulated enterprises.

---

## What this is

Hawiya AI is a standalone product. Consumer applications call it over REST to:

1. **Extract** structured data from passports, national IDs, and travel documents
2. **Resolve** identities into a single Golden Record per person
3. **Assist** workflows with audit-ready, confidence-scored AI decisions

It runs entirely inside the customer's environment — on-premise or sovereign cloud. No external API calls in production. Data never leaves the customer's data centre.

The first consumer is **WizSM**, a visa workflow platform deployed at Moro Hub for the UAE Presidential Diwan. The architecture is consumer-agnostic by design — banking KYC, civil affairs, healthcare, and hospitality consumers can be onboarded without changes to the core.

---

## Status

| Phase | Scope | Status |
|---|---|---|
| **Phase 1 — Foundation** | Document extraction, Person Registry, multi-tenancy, first consumer | **In progress** |
| Phase 2 — Intelligence | Probabilistic matching, visual OCR, LLM tiebreaker | Planned |
| Phase 3 — Workflow Assist | Document validation, summarisation, second consumer | Planned |

---

## Quick start (local dev)

Prerequisites:
- Python 3.11+
- Docker + Docker Compose
- Make

```bash
# Clone
git clone <internal-repo-url> hawiya-ai
cd hawiya-ai

# Install dependencies
make install

# Bring up Postgres + dev services
docker compose -f deploy/docker-compose.yml up -d

# Run migrations
make migrate

# Seed a test tenant
make seed-dev-tenant

# Start the service
make run-dev

# In another terminal — verify
curl http://localhost:8000/v1/health
```

The dev server runs at `http://localhost:8000`. OpenAPI docs at `http://localhost:8000/docs`.

---

## Project structure (the short version)

```
src/hawiya/
├── api/          # FastAPI routers — thin, no business logic
├── services/     # Business logic — every method takes tenant_id
├── extractors/   # OCR pipeline (MRZ, visual zone, classifier)
├── matching/     # Identity resolution
├── tenancy/      # Multi-tenant enforcement (read this first)
├── audit/        # Decision logging
└── db/           # Repositories, migrations, session
```

Full structure and conventions are in [`CLAUDE.md`](./CLAUDE.md).

---

## Key documents

| Document | Read when |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | Before writing any code. This is the contract. |
| [`API_SPEC.md`](./API_SPEC.md) | Before changing any endpoint. The consumer contract. |
| [`BUILD_PLAN.md`](./BUILD_PLAN.md) | To know what to build this week. |
| [`docs/multi-tenancy.md`](./docs/multi-tenancy.md) | Before touching data layer or services. |
| [`docs/demo-ui.md`](./docs/demo-ui.md) | Before building or modifying the demo UI. |
| [`docs/architecture.md`](./docs/architecture.md) | For the full picture. |
| [`docs/data-model.md`](./docs/data-model.md) | When working with the schema. |
| [`docs/matching-rules.md`](./docs/matching-rules.md) | When working on identity resolution. |

---

## The five rules everyone breaks (don't be that person)

1. **Tenant scope every query.** Every WHERE clause, every cache key, every audit row carries `tenant_id`. CI will fail your PR if a new data path lacks an isolation test.
2. **Never call external APIs in production.** No OpenAI, no Azure cognitive, no AWS, no GCP. If you think you have an exception, you don't — open a discussion first.
3. **Never log raw PII at INFO level.** Use `redact_pii()`. Passport numbers, names, DOB are sensitive.
4. **Deterministic before AI.** Try ICAO checksums and rules before reaching for ML. AI for what AI is good at, not for everything.
5. **Every AI decision is logged.** No AI output should ever leave the service without an entry in `audit_log`.

---

## Running tests

```bash
make test             # full suite
make test-fast        # unit only
make test-tenancy     # multi-tenant isolation suite — CI gate
```

Coverage target: 85% on `services/`, `extractors/`, `matching/`, `tenancy/`.

---

## Contributing

- Branch from `main`, target `main` via PR.
- Keep PRs small. One logical change per PR.
- Tests must pass. `make lint` must be clean. Coverage must not drop.
- Update `CLAUDE.md` if you change a constraint, convention, or canonical model.
- Update `API_SPEC.md` if you change an endpoint contract.
- Tag a security reviewer for any change to PII handling, auth, audit, or tenancy.

---

## Deployment

Hawiya AI deploys three ways:

| Mode | When | Time to live |
|---|---|---|
| On-premise | Customer's data centre | 4–6 weeks |
| Sovereign cloud | Customer uses a national cloud (Moro, Core42) | 2–4 weeks |
| Hybrid | Multi-site with central + edge | 6–8 weeks |

Deployment guides in [`docs/deployment/`](./docs/deployment/).

---

## Licence

Proprietary. Internal use only. Distribution to customers under separate licence agreement.

---

## Contact

- **Product:** Hawiya AI core team
- **Architecture review:** required for new dependencies, schema changes, public API changes
- **Security review:** required for PII, auth, audit, or tenancy changes
