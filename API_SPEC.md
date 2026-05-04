# API_SPEC.md — Hawiya AI REST Contract

> **The consumer contract.** This is the public API of Hawiya AI. Every consumer (WizSM today; banking, civil affairs, healthcare tomorrow) integrates through these endpoints.
>
> **Stability rules:** breaking changes are rare, versioned, and announced. Additive changes (new optional fields, new endpoints, new enum values explicitly marked extensible) are non-breaking and ship on `main`. Anything else needs an architecture review and a migration window for consumers.
>
> If a code change conflicts with this spec, update this spec first, then the code. If a customer asks for a behaviour not in this spec, the answer is "yes, in vN+1" or "let's discuss" — never silently divergent.

---

## 1. Authentication and tenancy

### 1.1 Auth model — DECISION PENDING (BUILD_PLAN §"Before you start" Q1)

Two candidate models. The middleware will be built to accept both during Week 1; the pilot picks one and that becomes the supported model for v1.

**Option A — OAuth2 client credentials (preferred for productised consumers)**
- Consumer holds a `client_id` + `client_secret`, issued at tenant onboarding
- Exchanges credentials for a short-lived JWT at `POST /v1/auth/token`
- JWT carries `tenant_id`, `client_id`, `scope`, `exp` (≤1h)
- Sent as `Authorization: Bearer <jwt>` on every request
- Tenant identifier is read from the JWT `tenant_id` claim — `X-Tenant-ID` is **ignored** if the JWT carries the claim

**Option B — mTLS + service JWT (preferred for sovereign on-prem)**
- Consumer presents a client certificate issued by the customer's PKI
- Inside the mTLS tunnel, requests carry `X-Tenant-ID: <uuid>` + `Authorization: Bearer <service-jwt>`
- The service JWT is short-lived (≤1h), signed by an internal issuer

**Decision required by end of Week 1.** Record the choice in §1 of this file and remove the unchosen option.

### 1.2 Tenant identification

Regardless of auth model, every request resolves to exactly one `tenant_id` (UUIDv4). Resolution priority:

1. JWT `tenant_id` claim (Option A)
2. `X-Tenant-ID` header (Option B)

A request that resolves to no tenant returns `401 UNAUTHENTICATED`. A request whose caller is not authorised for the resolved tenant returns `403 FORBIDDEN`.

### 1.3 Roles and scopes

| Scope | Grants |
|---|---|
| `documents:extract` | `POST /v1/documents/extract` |
| `identity:resolve` | `POST /v1/identity/resolve` |
| `persons:read` | `GET /v1/persons/*`, `POST /v1/persons/search` |
| `persons:write` | `POST /v1/persons`, `POST /v1/persons/{uuid}/merge`, `PATCH /v1/persons/{uuid}` |
| `admin:tenants` | `/v1/admin/tenants/*` (platform-admin only — never granted to a consumer) |
| `audit:read` | `GET /v1/audit/*` (consumer read of their own tenant's audit log) |

A consumer is typically issued `documents:extract identity:resolve persons:read persons:write` for a single tenant. Admin scopes are platform-internal.

---

## 2. Conventions

### 2.1 Versioning
- All endpoints under `/v1/`
- v1 is stable. v2 will be introduced side-by-side; v1 is deprecated only with ≥6 months notice.

### 2.2 Encoding
- All JSON request and response bodies use **snake_case** field names
- Dates: ISO 8601 `YYYY-MM-DD`
- Timestamps: ISO 8601 with timezone, e.g. `2026-05-01T14:23:11.482Z`
- Country codes: ISO 3166-1 **alpha-3** (e.g. `ARE`, `SAU`, `EGY`)
- Sex: `M` / `F` / `X`
- UUIDs: canonical string form (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
- All text is UTF-8. Arabic content is preserved as-is; no transliteration on the wire unless the consumer asks for it.

### 2.3 Required headers (every request)

| Header | Required | Purpose |
|---|---|---|
| `Authorization` | yes | Bearer token (JWT) |
| `X-Tenant-ID` | conditional | Required if JWT lacks `tenant_id` claim |
| `X-Request-ID` | recommended | Consumer-supplied trace ID; echoed in responses and logs. If missing, the service generates one. |
| `Idempotency-Key` | conditional | Required on POSTs that create resources (see §2.5) |
| `Content-Type` | yes on bodies | `application/json` or `multipart/form-data` |

### 2.4 Error responses

All errors share one envelope:

```json
{
  "error": {
    "code": "DOCUMENT_UNREADABLE",
    "message": "MRZ region could not be located in the supplied image.",
    "details": {
      "supported_formats": ["image/jpeg", "image/png", "application/pdf"],
      "received": "image/heic"
    },
    "trace_id": "01J5W9Q3K2M4P7N8X0YQRZHTBW"
  }
}
```

- `code` — stable machine-readable identifier. See §7 for the full list.
- `message` — human-readable. May change between releases; do **not** parse it.
- `details` — endpoint-specific structured context. Stable per code.
- `trace_id` — equal to `X-Request-ID` for the request. Use it when filing tickets.

HTTP status codes follow standard semantics:

| Status | Meaning |
|---|---|
| `400 BAD_REQUEST` | Validation failure, malformed payload |
| `401 UNAUTHENTICATED` | Missing or invalid credentials |
| `403 FORBIDDEN` | Authenticated, but not authorised for the resource/tenant |
| `404 NOT_FOUND` | Resource does not exist within this tenant |
| `409 CONFLICT` | Resource conflict (e.g. duplicate person) |
| `413 PAYLOAD_TOO_LARGE` | Document exceeds size limits (§3.2) |
| `415 UNSUPPORTED_MEDIA_TYPE` | Body content type not accepted |
| `422 UNPROCESSABLE_ENTITY` | Well-formed but semantically invalid |
| `429 TOO_MANY_REQUESTS` | Rate limit exceeded; honour `Retry-After` |
| `500 INTERNAL_ERROR` | Unexpected server failure |
| `503 SERVICE_UNAVAILABLE` | Component degraded; honour `Retry-After` |

### 2.5 Idempotency

Required on every POST that creates a resource (`/documents/extract`, `/identity/resolve`, `/persons`, `/persons/{uuid}/merge`).

- Header: `Idempotency-Key: <opaque string, ≤128 chars, recommend ULID or UUID>`
- Window: **24 hours** from first observation
- Scope: `(tenant_id, idempotency_key)` — keys never collide across tenants
- Behaviour: a replay returns the original response (status, body, headers) byte-for-byte
- Conflict: a key reused with a *different* request body returns `409 IDEMPOTENCY_CONFLICT`

A consumer SHOULD generate one fresh key per logical operation. A consumer MUST NOT reuse a key for a different operation.

### 2.6 Pagination

List endpoints use cursor pagination:

```
GET /v1/persons/search?limit=50&cursor=eyJvZmZzZXQiOjUwfQ
```

Response:
```json
{
  "items": [ ... ],
  "next_cursor": "eyJvZmZzZXQiOjEwMH0",
  "has_more": true
}
```

`limit` defaults to 25, max 200. `cursor` is opaque — consumers MUST NOT parse it. `next_cursor` is `null` on the last page.

### 2.7 Rate limits

Default per-tenant limits (configurable in tenant config):

| Endpoint group | Limit |
|---|---|
| `/documents/extract` | 100 req/min |
| `/identity/resolve` | 100 req/min |
| `/persons/*` (read) | 600 req/min |
| `/persons/*` (write) | 60 req/min |
| `/health`, `/ready` | unlimited |

On limit: `429` with `Retry-After: <seconds>` and `X-RateLimit-Remaining: 0`.

### 2.8 Audit-trail headers (responses)

Every response that represents an AI decision (`/documents/extract`, `/identity/resolve`, `/persons` create) carries:

| Header | Meaning |
|---|---|
| `X-Audit-ID` | UUID of the audit row written for this call |
| `X-Model-Versions` | Comma-separated `component/version` list, e.g. `mrz/passporteye-v0.1,match/det-v0.1` |
| `X-Reversible-Until` | ISO 8601 timestamp; the decision can be reversed via the audit endpoint up to this time |

---

## 3. Endpoints — Health and metadata

### 3.1 `GET /v1/health` (liveness)

No auth. Used by load balancers and Kubernetes liveness probes.

**Response 200**
```json
{ "status": "ok" }
```

### 3.2 `GET /v1/ready` (readiness)

No auth. Used by Kubernetes readiness probes.

**Response 200** — service can accept traffic
```json
{
  "status": "ready",
  "components": {
    "database": "ok",
    "ocr_engine": "ok",
    "audit_sink": "ok"
  }
}
```

**Response 503** — at least one critical component is degraded
```json
{
  "status": "degraded",
  "components": {
    "database": "ok",
    "ocr_engine": "ok",
    "audit_sink": "unreachable"
  }
}
```

### 3.3 `GET /v1/version`

Auth required (any scope). Returns build and model metadata.

```json
{
  "service_version": "0.1.0",
  "build_sha": "a1b2c3d",
  "built_at": "2026-04-29T08:14:00Z",
  "model_versions": {
    "mrz_extractor": "passporteye-v0.1+tesseract-5.3",
    "deterministic_matcher": "det-v0.1",
    "arabic_normaliser": "arabic-norm-v0.1"
  },
  "supported_document_types": ["passport"],
  "phase": 1
}
```

---

## 4. Endpoints — Documents

### 4.1 `POST /v1/documents/extract`

Extract structured fields from a single passport or ID image. Returns extraction + confidence per field. **Does not** match against the Person Registry — use `/identity/resolve` for that.

**Auth:** scope `documents:extract`.
**Idempotency:** required.

#### Request — multipart (preferred)
```
POST /v1/documents/extract
Authorization: Bearer ...
Idempotency-Key: 01J5W9Q3K2M4P7N8X0YQRZHTBW
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="document"; filename="passport.jpg"
Content-Type: image/jpeg

<binary>
--boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "document_type_hint": "passport",
  "consumer_request_id": "wizsm-req-2026-0501-0042",
  "capture_source": "regula_70x8"
}
--boundary--
```

#### Request — JSON (base64)
For consumers that cannot send multipart (legacy systems). Discouraged; prefer multipart.
```json
{
  "document": {
    "content_type": "image/jpeg",
    "data_base64": "..."
  },
  "document_type_hint": "passport",
  "consumer_request_id": "wizsm-req-2026-0501-0042",
  "capture_source": "browser_upload"
}
```

#### Constraints
- Max image size: **10 MB**
- Accepted content types: `image/jpeg`, `image/png`, `application/pdf` (single-page only in v1)
- `document_type_hint` (optional): one of `passport`, `emirates_id`, `gcc_id`, `residence_permit`. Speeds classification but does not override it; a hint that conflicts with the classifier returns `422 DOCUMENT_TYPE_MISMATCH`.
- `consumer_request_id` (optional): consumer's correlation ID, max 128 chars, stored on the extraction row for traceability.
- `capture_source` (optional): free-form, stored for analytics.

#### Response 200
```json
{
  "extraction_id": "8c42f3a1-...",
  "tenant_id": "f1a8...",
  "document_type": "passport",
  "processing_path": "mrz_only",
  "processing_time_ms": 287,
  "checksum_status": "all_pass",
  "extracted_data": {
    "passport_number": "A12345678",
    "issuing_country": "ARE",
    "surname": "AL MANSOORI",
    "given_names": "AHMED MOHAMMED",
    "nationality": "ARE",
    "date_of_birth": "1985-04-12",
    "sex": "M",
    "expiry_date": "2030-09-30",
    "personal_number": "78419851234567",
    "name_arabic": "أحمد محمد المنصوري",
    "place_of_birth": null,
    "issuing_authority": null
  },
  "confidence_per_field": {
    "passport_number": 0.99,
    "issuing_country": 1.00,
    "surname": 0.97,
    "given_names": 0.95,
    "nationality": 1.00,
    "date_of_birth": 1.00,
    "sex": 1.00,
    "expiry_date": 1.00,
    "personal_number": 0.95,
    "name_arabic": 0.88
  },
  "checksums": {
    "passport_number": "pass",
    "date_of_birth": "pass",
    "expiry_date": "pass",
    "personal_number": "pass",
    "composite": "pass"
  },
  "raw_mrz": "P<AREALMANSOORI<<AHMED<MOHAMMED<<<<<<<<<<<<<\nA12345678 4ARE8504128M3009304784198512345678 8",
  "audit": {
    "audit_id": "...",
    "request_id": "...",
    "model_versions": {
      "mrz_extractor": "passporteye-v0.1+tesseract-5.3",
      "classifier": "doc-cls-v0.1"
    },
    "reversible_until": "2026-05-31T14:23:11Z"
  }
}
```

`processing_path` enum: `mrz_only` | `mrz_plus_visual` | `visual_only` | `vision_fallback`. v1 (Phase 1) returns `mrz_only` for clean MRZ, `visual_only` for non-MRZ documents (Emirates ID), and never `vision_fallback` (Phase 2+).

`checksum_status` enum: `all_pass` | `partial` | `all_fail` | `n/a` (for documents without MRZ).

#### Response errors
- `400 BAD_REQUEST` — malformed multipart, invalid metadata
- `413 PAYLOAD_TOO_LARGE` — image > 10 MB
- `415 UNSUPPORTED_MEDIA_TYPE` — content type not accepted
- `422 DOCUMENT_UNREADABLE` — image received, but extraction failed; `details` contains stage of failure (`classification`, `mrz_locate`, `mrz_ocr`, `checksum`)
- `422 UNSUPPORTED_DOCUMENT` — classifier identified a document type not in `tenant.config.supported_document_types`
- `422 DOCUMENT_TYPE_MISMATCH` — `document_type_hint` conflicts with classifier output

---

## 5. Endpoints — Identity resolution

### 5.1 `POST /v1/identity/resolve`

The primary endpoint. Extracts a document **and** resolves it against the Person Registry in a single call. Most consumers will use only this endpoint.

**Auth:** scopes `documents:extract` + `identity:resolve`.
**Idempotency:** required.

#### Request — multipart
Same multipart shape as `/documents/extract`, plus a `resolve_options` part:

```
--boundary
Content-Disposition: form-data; name="resolve_options"
Content-Type: application/json

{
  "create_if_no_match": true,
  "auto_merge_threshold": null,
  "suggest_merge_threshold": null,
  "consumer_request_id": "wizsm-req-2026-0501-0042"
}
--boundary--
```

#### Request — JSON
```json
{
  "document": {
    "content_type": "image/jpeg",
    "data_base64": "..."
  },
  "resolve_options": {
    "create_if_no_match": true,
    "auto_merge_threshold": null,
    "suggest_merge_threshold": null,
    "consumer_request_id": "wizsm-req-2026-0501-0042"
  }
}
```

#### Request — extract-then-resolve
A consumer that already called `/documents/extract` and wants to resolve the result without re-uploading:
```json
{
  "extraction_id": "8c42f3a1-...",
  "resolve_options": { "create_if_no_match": true }
}
```
The extraction must belong to the same tenant and be ≤24h old.

#### Resolve options
| Field | Type | Default | Meaning |
|---|---|---|---|
| `create_if_no_match` | bool | `true` | If matching returns `no_match`, create a new Golden Record. If `false`, return `no_match_no_create`. |
| `auto_merge_threshold` | float \| null | tenant config | Override per-call (rarely used; mostly for testing) |
| `suggest_merge_threshold` | float \| null | tenant config | Override per-call |
| `consumer_request_id` | string \| null | — | Consumer correlation ID |

#### Response 200
```json
{
  "extraction": { /* same shape as §4.1 response, minus the audit envelope */ },
  "match": {
    "action": "auto_matched",
    "confidence": 0.99,
    "match_type": "deterministic",
    "matched_on": ["passport_number", "date_of_birth", "nationality"],
    "person_uuid": "b07c1e64-...",
    "person": {
      "person_uuid": "b07c1e64-...",
      "canonical_name_ar": "أحمد محمد المنصوري",
      "canonical_name_en": "Ahmed Mohammed Al Mansoori",
      "date_of_birth": "1985-04-12",
      "nationality": "ARE",
      "sex": "M",
      "status": "active",
      "interaction_count": 3,
      "last_seen_at": "2026-04-12T10:08:00Z"
    },
    "candidates": [],
    "decision_id": "..."
  },
  "audit": {
    "audit_id": "...",
    "request_id": "...",
    "model_versions": {
      "mrz_extractor": "passporteye-v0.1+tesseract-5.3",
      "matcher": "det-v0.1",
      "arabic_normaliser": "arabic-norm-v0.1"
    },
    "reversible_until": "2026-05-31T14:23:11Z"
  }
}
```

#### `match.action` enum (full v1 contract)

| Value | Meaning | Phase 1 live? |
|---|---|---|
| `auto_matched` | Confidence ≥ tenant `auto_merge` threshold; `person_uuid` is set | yes |
| `suggested_match` | Confidence ≥ `suggest_merge` but < `auto_merge`; `candidates` populated, `person_uuid` is null | yes (deterministic paths only) |
| `manual_review` | Confidence ≥ `manual_review` but < `suggest_merge`; `candidates` populated | partial — Phase 1 returns this only on near-miss deterministic matches; phonetic/fuzzy paths arrive Phase 2 |
| `new_record` | No match; `create_if_no_match=true`; new Golden Record created, `person_uuid` set | yes |
| `no_match_no_create` | No match; `create_if_no_match=false`; `person_uuid` is null | yes |

#### `match.match_type` enum

| Value | Phase 1 live? |
|---|---|
| `deterministic` | yes |
| `probabilistic` | no — Phase 2 |
| `llm_assisted` | no — Phase 2+ |

A consumer SHOULD treat unknown enum values as `manual_review` (forward compatibility).

#### `candidates` shape (only for `suggested_match` and `manual_review`)
```json
"candidates": [
  {
    "person_uuid": "...",
    "confidence": 0.86,
    "matched_on": ["name_arabic", "date_of_birth", "nationality"],
    "differences": [
      { "field": "passport_number", "extracted": "A12345678", "existing": "Z98765432" }
    ],
    "person_summary": {
      "canonical_name_ar": "أحمد المنصوري",
      "canonical_name_en": "Ahmed Al Mansoori",
      "date_of_birth": "1985-04-12",
      "nationality": "ARE"
    }
  }
]
```

Up to **5 candidates** returned, ranked by confidence descending.

#### Response errors
- All errors from `/documents/extract` apply
- `422 EXTRACTION_NOT_FOUND` — `extraction_id` unknown or expired
- `422 EXTRACTION_TENANT_MISMATCH` — `extraction_id` belongs to another tenant (returned as `404` to avoid information leak — see §7)

---

## 6. Endpoints — Persons

### 6.1 `POST /v1/persons/search`

Find candidate Golden Records by structured criteria. Read-only; does not write to the audit log (it's not a decision).

**Auth:** scope `persons:read`.

#### Request
```json
{
  "name_arabic": "أحمد المنصوري",
  "name_english": null,
  "date_of_birth": "1985-04-12",
  "nationality": "ARE",
  "identifiers": [
    { "type": "passport", "value": "A12345678" }
  ],
  "limit": 25
}
```

At least one of `identifiers`, `name_arabic`, `name_english`, or `date_of_birth + nationality` must be supplied.

#### Response 200
```json
{
  "items": [
    {
      "person_uuid": "...",
      "match_score": 0.92,
      "matched_on": ["passport_number"],
      "person": { /* full Person record */ }
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

`match_score` is a search relevance score, **not** a matching confidence. It is comparable across results in the same response only.

### 6.2 `GET /v1/persons/{person_uuid}`

Retrieve one Golden Record.

**Auth:** scope `persons:read`.

#### Response 200
```json
{
  "person_uuid": "b07c1e64-...",
  "tenant_id": "...",
  "canonical_name_ar": "أحمد محمد المنصوري",
  "canonical_name_en": "Ahmed Mohammed Al Mansoori",
  "date_of_birth": "1985-04-12",
  "nationality": "ARE",
  "sex": "M",
  "status": "active",
  "merged_into": null,
  "identifiers": [
    {
      "identifier_id": "...",
      "identifier_type": "passport",
      "identifier_value": "A12345678",
      "issuing_country": "ARE",
      "issue_date": "2020-09-30",
      "expiry_date": "2030-09-30",
      "is_primary": true,
      "source": "extraction:8c42f3a1-...",
      "confidence": 0.99
    },
    {
      "identifier_id": "...",
      "identifier_type": "emirates_id",
      "identifier_value": "784-1985-1234567-8",
      "is_primary": true,
      "source": "manual_entry",
      "confidence": 1.00
    }
  ],
  "name_variants": [
    { "name_value": "أحمد محمد المنصوري", "script": "arabic", "variant_type": "canonical" },
    { "name_value": "Ahmed Mohammed Al Mansoori", "script": "latin", "variant_type": "transliteration" },
    { "name_value": "Ahmad Almansouri", "script": "latin", "variant_type": "alias" }
  ],
  "interaction_count": 3,
  "first_seen_at": "2026-01-20T09:14:00Z",
  "last_seen_at": "2026-04-12T10:08:00Z",
  "created_at": "2026-01-20T09:14:00Z",
  "updated_at": "2026-04-12T10:08:00Z"
}
```

If the person has been merged into another (`status = merged`), `merged_into` is the surviving `person_uuid`. Consumers SHOULD follow the redirect.

#### Response errors
- `404 NOT_FOUND` — person does not exist in this tenant (also returned for cross-tenant reads — see §7)

### 6.3 `POST /v1/persons` (manual create)

Create a Golden Record without going through document extraction. Used for back-office tooling and migrations. Most consumers should use `/identity/resolve` instead.

**Auth:** scope `persons:write`.
**Idempotency:** required.

#### Request
```json
{
  "canonical_name_ar": "أحمد محمد المنصوري",
  "canonical_name_en": "Ahmed Mohammed Al Mansoori",
  "date_of_birth": "1985-04-12",
  "nationality": "ARE",
  "sex": "M",
  "identifiers": [
    { "identifier_type": "emirates_id", "identifier_value": "784-1985-1234567-8" }
  ]
}
```

#### Response 201
The full Person record (same shape as §6.2).

#### Response 409 — duplicate suspected
```json
{
  "error": {
    "code": "POSSIBLE_DUPLICATE",
    "message": "An existing person matches the provided identifiers.",
    "details": {
      "candidates": [
        { "person_uuid": "...", "confidence": 0.99, "matched_on": ["emirates_id"] }
      ]
    },
    "trace_id": "..."
  }
}
```

To force creation despite the duplicate, the caller must instead `POST /v1/persons/{uuid}/merge` against the existing record, or call with `?force=true` (requires scope `persons:write` AND `admin:override` — typically platform-admin only).

### 6.4 `PATCH /v1/persons/{person_uuid}`

Update mutable fields on a Golden Record. Identifiers and name variants are managed via dedicated endpoints (Phase 2). v1 supports updates to `canonical_name_ar`, `canonical_name_en`, `status`.

**Auth:** scope `persons:write`.

```json
{ "canonical_name_en": "Ahmed Mohammed Almansoori" }
```

Returns the updated Person.

### 6.5 `POST /v1/persons/{surviving_uuid}/merge`

Merge a duplicate record into a surviving record. Both must be active and in the same tenant.

**Auth:** scope `persons:write`.
**Idempotency:** required.

```json
{
  "duplicate_uuid": "f4c01e22-...",
  "reason": "Same person, different transliteration",
  "reviewed_by": "officer:wizsm:user42"
}
```

Effect:
- `duplicate.status = merged`, `duplicate.merged_into = surviving_uuid`
- All `person_identifiers` and `person_name_variants` are re-pointed to `surviving_uuid`
- A `match_decision` row is written
- An audit entry is written
- Reversible until `reversible_until` (typically 30 days)

#### Response 200
The surviving Person record, with merged identifiers visible.

### 6.6 `GET /v1/persons/{person_uuid}/extractions`

Retrieve the extraction history for a person. Paginated.

**Auth:** scope `persons:read`.

```json
{
  "items": [
    {
      "extraction_id": "...",
      "document_type": "passport",
      "match_action": "auto_matched",
      "created_at": "2026-04-12T10:08:00Z"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

---

## 7. Endpoints — Audit (consumer read access)

### 7.1 `GET /v1/audit/{audit_id}`

Retrieve a single audit entry. Tenant-scoped — returns `404` if the entry belongs to another tenant (we deliberately do **not** distinguish "not found" from "not yours" to avoid existence leaks across tenants).

**Auth:** scope `audit:read`.

```json
{
  "audit_id": "...",
  "tenant_id": "...",
  "request_id": "...",
  "user_id": "officer:wizsm:user42",
  "endpoint": "POST /v1/identity/resolve",
  "input_hash": "sha256:...",
  "output_summary": { "match_action": "auto_matched", "person_uuid": "..." },
  "model_versions": { ... },
  "confidence": 0.99,
  "processing_path": "mrz_only",
  "decision": "auto_match",
  "reversible_until": "2026-05-31T14:23:11Z",
  "reversed_at": null,
  "reversed_by": null,
  "created_at": "2026-05-01T14:23:11Z"
}
```

### 7.2 `POST /v1/audit/{audit_id}/reverse`

Reverse a decision (e.g. an auto-merge that the officer disagrees with). Only allowed before `reversible_until`.

**Auth:** scope `persons:write` (since reversal mutates person state).
**Idempotency:** required.

```json
{
  "reason": "Officer determined these are different people.",
  "reviewed_by": "officer:wizsm:user42"
}
```

Effect depends on the original decision:
- `auto_match` reversal → unlinks the extraction from the person, re-creates the person if needed
- `merge` reversal → splits the record (surviving and duplicate become separate again)
- `auto_create` reversal → archives the newly created person

All reversals write a new audit entry. **Reversals themselves are not reversible.**

---

## 8. Endpoints — Admin (platform-internal only)

> These endpoints are **not** exposed to consumers. They are for platform operators (Hawiya AI ops) only. A consumer-facing tenant management portal is Phase 3.

### 8.1 `POST /v1/admin/tenants`

Onboard a new tenant. Requires scope `admin:tenants`.

```json
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

#### Response 201
```json
{
  "tenant_id": "f1a8...",
  "tenant_name": "WizSM Production",
  "status": "active",
  "config": { /* echoed */ },
  "created_at": "2026-05-01T14:23:11Z"
}
```

Consumer credentials (OAuth2 client_id/secret or mTLS cert CSR flow) are issued via a separate endpoint (Phase 2 — out of scope for this spec).

### 8.2 `GET /v1/admin/tenants`

List tenants. Paginated.

### 8.3 `GET /v1/admin/tenants/{tenant_id}`

Get one tenant's config and status.

### 8.4 `PATCH /v1/admin/tenants/{tenant_id}`

Update tenant status (`active`, `suspended`, `archived`) or config. Config changes apply to subsequent requests only — in-flight requests use the snapshot taken at request start.

```json
{ "status": "suspended" }
```

A `suspended` tenant returns `403 TENANT_SUSPENDED` on every non-admin endpoint.

---

## 9. Error code catalogue

Stable error codes. New codes are additive (non-breaking); codes are never repurposed.

### 9.1 Authentication and tenancy
| Code | HTTP | Meaning |
|---|---|---|
| `UNAUTHENTICATED` | 401 | No or invalid credentials |
| `TOKEN_EXPIRED` | 401 | JWT expired; refresh required |
| `FORBIDDEN` | 403 | Authenticated but lacks scope or tenant access |
| `TENANT_NOT_FOUND` | 401 | Tenant identifier does not resolve to a tenant |
| `TENANT_SUSPENDED` | 403 | Tenant exists but is suspended |
| `TENANT_ARCHIVED` | 403 | Tenant exists but is archived |

### 9.2 Validation
| Code | HTTP | Meaning |
|---|---|---|
| `INVALID_REQUEST` | 400 | Generic malformed request |
| `MISSING_FIELD` | 400 | A required field is missing; `details.field` names it |
| `INVALID_FIELD_VALUE` | 400 | A field value is malformed; `details.field` and `details.reason` |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Body content type not accepted |
| `PAYLOAD_TOO_LARGE` | 413 | Body exceeds size limit |

### 9.3 Documents
| Code | HTTP | Meaning |
|---|---|---|
| `DOCUMENT_UNREADABLE` | 422 | Image received but extraction failed; `details.stage` |
| `UNSUPPORTED_DOCUMENT` | 422 | Document type not in tenant config |
| `DOCUMENT_TYPE_MISMATCH` | 422 | Hint conflicts with classifier |
| `CHECKSUM_FAILED` | 422 | All checksums failed; data unreliable |

### 9.4 Identity
| Code | HTTP | Meaning |
|---|---|---|
| `EXTRACTION_NOT_FOUND` | 404 | `extraction_id` unknown or expired |
| `PERSON_NOT_FOUND` | 404 | Person does not exist in this tenant |
| `POSSIBLE_DUPLICATE` | 409 | A matching person already exists; see `details.candidates` |
| `PERSON_MERGED` | 409 | Operation invalid because person is in `merged` state; `details.merged_into` is the surviving uuid |
| `MERGE_TENANT_MISMATCH` | 422 | Surviving and duplicate are in different tenants (returned as `404` in practice) |

### 9.5 Audit
| Code | HTTP | Meaning |
|---|---|---|
| `AUDIT_NOT_FOUND` | 404 | Audit entry does not exist in this tenant |
| `REVERSAL_WINDOW_EXPIRED` | 422 | Decision is past `reversible_until` |
| `ALREADY_REVERSED` | 409 | Decision has already been reversed |

### 9.6 Idempotency and rate
| Code | HTTP | Meaning |
|---|---|---|
| `IDEMPOTENCY_CONFLICT` | 409 | Key reused with a different request body |
| `RATE_LIMITED` | 429 | Per-tenant rate limit exceeded |

### 9.7 System
| Code | HTTP | Meaning |
|---|---|---|
| `INTERNAL_ERROR` | 500 | Unexpected server failure |
| `SERVICE_UNAVAILABLE` | 503 | A required component is unavailable |
| `TIMEOUT` | 504 | Upstream component (OCR, DB) timed out |

---

## 10. Cross-tenant information leakage rules

Hawiya AI's tenant isolation is absolute (per `docs/multi-tenancy.md`). To prevent existence-leak attacks across tenants:

- A `GET /v1/persons/{uuid}` for a uuid that exists in another tenant returns `404 PERSON_NOT_FOUND`, **not** `403`. There is no observable difference between "doesn't exist anywhere" and "exists in another tenant".
- Same rule for extractions, audit entries, and any other tenant-scoped resource.
- Idempotency keys are scoped per-tenant (§2.5); a key used by Tenant A does not affect Tenant B.
- Error messages never include data from another tenant, even on internal errors.

This is a hard requirement and a tested invariant (`tests/multi_tenant/`).

---

## 11. PII handling on the wire

- All requests and responses go over TLS (≥1.2; 1.3 preferred). HTTP/2 supported. Plaintext HTTP rejected at the load balancer.
- PII fields (names, DOB, identifiers, raw MRZ, document images) are never logged at INFO level by the service. They appear in DEBUG logs only when DEBUG is explicitly enabled — DEBUG is **off** in production.
- Document images are stored encrypted at rest. Retention is tenant-configurable (default 365 days, then purged).
- The `input_hash` field in audit entries is `sha256(<canonical-form-of-input>)` — computed deterministically so the same input produces the same hash, but the input itself cannot be reconstructed.
- Consumer-side: do not log `Authorization` headers, request bodies of `/documents/extract` or `/identity/resolve`, or response bodies that contain `extracted_data`. Log `request_id` and `extraction_id` instead.

---

## 12. What's not in v1 (deferred contracts)

Listed here so consumers know not to build against them yet:

- **Webhooks / async callbacks** — under review for Phase 2. v1 is fully synchronous.
- **Batch endpoints** — `POST /v1/documents/extract:batch` for bulk processing — Phase 2.
- **Probabilistic match details** — `match.match_type = "probabilistic"` will appear in Phase 2 with the same response shape; consumers should already treat unknown `match_type` values gracefully.
- **LLM-assisted match reasoning** — `match.match_type = "llm_assisted"` will appear in Phase 2+ with an additional `reasoning_summary` field.
- **Officer review queue** — `GET /v1/review-queue` — Phase 2 APIs.
- **Document validation** — `POST /v1/documents/validate` for supporting documents — Phase 3.
- **Consumer-managed encryption keys** — Phase 3 review.
- **Multi-document submission** — Phase 3.

---

## 13. Backward compatibility commitments

In v1, the following are **frozen contracts**; changing any of these requires v2:

- Endpoint paths and HTTP methods
- Required request fields (you can add optional fields; you cannot rename or remove required ones)
- Response field names and types for non-experimental fields
- Error code identifiers (new codes can be added)
- Authentication mechanism (once chosen)
- Idempotency window and scope rules

The following can change additively without notice:
- New optional request fields
- New response fields
- New enum values (consumers must treat unknown enum values gracefully — see `match.action`)
- New error codes
- New endpoints
- Improvements to confidence scores, model versions, processing paths

---

## 14. Open questions to resolve before Week 2 ships

1. **Auth model** (§1.1) — pick A or B. Affects middleware design and consumer onboarding flow.
2. **`POST /v1/auth/token`** — is this part of v1, or is token issuance fully out-of-band? If Option A, we need this endpoint specified.
3. **Reversibility window default** — 30 days assumed throughout. Is this per-tenant configurable in v1, or v1 fixes it at 30 and v2 makes it configurable?
4. **`?force=true` on `POST /v1/persons`** — required for v1 (for back-office tooling) or deferred to admin tooling?
5. **Audit destination webhook** — `audit_destination: "webhook"` mentioned in `multi-tenancy.md`. What's the webhook contract? Defer to Phase 2 unless WizSM needs it on day one.
6. **Error message localisation** — single-language (English) for v1, Arabic in v2? Confirm with WizSM.

Send these as a written list to product + WizSM. Pin the answers here in §1 and §14.

---

## 15. Changelog

| Version | Date | Change |
|---|---|---|
| 0.1 (draft) | 2026-05-01 | Initial spec drafted from CLAUDE.md, BUILD_PLAN.md, multi-tenancy.md, demo-ui.md. |
