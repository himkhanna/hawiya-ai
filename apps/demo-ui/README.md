# Hawiya AI — Demo UI

A standalone React app that walks a customer through the production
identity-resolve flow: capture → extraction → resolution. Lives in this
repo as a sales / officer-experience preview per `demo-ui.md`. Not the
WizSM officer UI; that's WizSM's responsibility.

This is **Tier 1**: real API calls, three baked-in scenarios, no
animations beyond simple transitions, system fonts. Tiers 2 and 3 add
animations and brand polish.

## Run it

The Hawiya AI backend stack must be up first. From the repo root:

```bash
docker compose -f deploy/docker-compose.yml \
    -f deploy/docker-compose.override.yml \
    --profile obs up -d
```

Wait until `deploy-api-1` is healthy, then seed:

```bash
# Tenant
docker compose -f deploy/docker-compose.yml \
    -f deploy/docker-compose.override.yml exec api \
    python -m scripts.seed_dev_tenant
# Note the tenant_id printed.

# Personas (the demo UI's Scenario B matches Ahmed Almansoori from this seed)
.venv/Scripts/python.exe -m scripts.seed_demo_persons \
    --base-url http://localhost:8010 \
    --tenant-id <tenant_id>
```

Then in this directory:

```bash
cp .env.example .env.local
# Edit .env.local and paste the tenant_id into VITE_HAWIYA_TENANT_ID
npm install   # only the first time
npm run dev
```

Open http://localhost:5173.

## Before each customer demo

Scenario A creates a `Mohamed Almansoori` record on its first scan. If
you demo the same tenant twice without cleanup, the second run's
Scenario A will return `auto_matched` instead of `new_record` and the
narrative breaks. Reset between sessions:

```bash
python -m scripts.reset_demo_session --tenant-id <tenant_id>
```

This deletes only the ad-hoc records the UI creates (P1234567 and
X9876543). The seeded Ahmed Almansoori — which Scenario B matches
against — is kept.

## What you should see

Three pill buttons in the header. Click one to select a scenario. The
left column shows the passport image, the center column shows the
extracted fields once you press Scan, the right column shows the
identity decision.

| Scenario | Result | What it demonstrates |
|---|---|---|
| **A — New traveller** | `new_record` | Real OCR + Golden Record creation. Click Scan again to see `auto_matched` (dedup). |
| **B — Returning traveller** | `auto_matched` | Recognised against the seeded Ahmed Almansoori. No duplicate. |
| **C — Possible duplicate** | `suggested_match` | Same passport number as B, tampered DOB. System refuses to auto-link; routes to officer review. |

If the API is unreachable the header pill goes red and Scan returns a
network error in the centre column.

## Files

- `src/App.tsx` — top-level layout + state machine
- `src/scenarios.ts` — three scenarios + image loaders
- `src/api.ts` — client for `/v1/identity/resolve`
- `src/components/` — Header, CapturePanel, ExtractionPanel, ResolutionPanel, Footer
- `public/scenarios/scenario-{a,b,c}.jpg` — pre-generated passport images
  (regenerate via `python -m scripts.generate_passport_image`)
- `tailwind.config.js` — brand palette per `demo-ui.md` §4

## Not in Tier 1

Custom fonts (Fraunces / Inter Tight / Amiri), MRZ extraction animation,
checksum-row animation, SVG mock-passport editor, real anonymised
samples, mock-mode toggle. All flagged for Tier 2/3.
