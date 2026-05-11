# Hawiya AI — Postman collection (WizSM)

Two files for WizSM's engineering team to drop straight into Postman or
Bruno and start integrating against `/v1/documents/extract`:

| File | Purpose |
|---|---|
| `hawiya-ai-wizsm.postman_collection.json` | The collection — three folders (Health, Document extraction) with example requests, sample responses, and inline tests |
| `hawiya-ai-dev.postman_environment.json` | Variables: `base_url`, `tenant_id`, `bearer_token` |

## Import

**Postman:**
1. File → Import → drop both files in.
2. Top-right environment selector → "Hawiya AI — Dev".
3. Click the eye icon next to the selector → set `tenant_id` to the UUID Hawiya provides → save.

**Bruno / Insomnia / Hoppscotch:** all support Postman v2.1.0 import. Drop
the collection file in.

## What's included

- `Health → GET /v1/health` — liveness probe (no auth)
- `Health → GET /v1/ready` — readiness with DB ping (no auth)
- `Document extraction → POST /v1/documents/extract — happy path` — pick a
  passport image and submit. Inline tests assert 200 + extraction shape.
- `Document extraction → POST /v1/documents/extract — non-image (415 example)` —
  trigger the unsupported-document error envelope without crafting a bad image
- `Document extraction → POST /v1/documents/extract — without tenant (401 example)` —
  trigger the auth gate; useful for testing your client's error surfaces

Sample 200/415/422/429 responses are saved on each request — browseable
without making a network call.

## Auth model

Phase 1 ships a bearer-token stub (`Bearer dev`) plus a required
`X-Tenant-ID` header. Production swaps the bearer for mTLS or OAuth2 —
the Hawiya team will tell WizSM which before pilot go-live; the request
shape doesn't change.

## What's deliberately NOT in the collection

- `/v1/identity/resolve` and `/v1/persons/*` — these are Hawiya's
  Person Registry endpoints, used by consumers without their own
  registry. WizSM does its own dedup against the Diwan registry, so
  these endpoints are out of scope for the WizSM integration.

If WizSM's plans change later and they want to delegate dedup to
Hawiya, the registry endpoints become relevant — happy to ship a
second collection at that point.

## Quick smoke test once you've imported

1. Run `Health / GET /v1/health` — expect 200 and `{"status":"ok"}`.
2. Run `Document extraction / POST /v1/documents/extract — without tenant` —
   expect 401 and `error.code: TENANT_REQUIRED`. Proves your bearer is
   working but tenant is missing.
3. Set `tenant_id` in the environment.
4. Run `Document extraction / POST /v1/documents/extract — happy path` —
   pick any passport JPEG (or one of the synthetic samples in
   `apps/demo-ui/public/scenarios/`). Expect 200 with the structured
   `fields`, `confidence_per_field`, `checksum_status: all_pass`.
5. Run `Document extraction / POST /v1/documents/extract — non-image` —
   expect 415 and `error.code: UNSUPPORTED_DOCUMENT`. Proves your error
   envelope handling.

That's the whole integration surface for WizSM.

## Updating the collection

Edits land in `hawiya-ai-wizsm.postman_collection.json` directly — it's
plain JSON. Re-export from Postman if you change the collection there
and want the repo version to match.
