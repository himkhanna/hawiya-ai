# Demo UI Specification

> A standalone React demo application that doubles as the officer-experience preview and the sales demo. Lives in a separate workspace from the main service.

This document specifies what to build, how it should look and feel, and when it gets built. It is not a wireframe set — it is a brief detailed enough that an engineer can build it without further questions, and a stakeholder can sign off without seeing code.

---

## 1. Purpose

A single demo application that serves three audiences simultaneously:

1. **Sales conversations** — buyers see the platform's capability in 90 seconds, no slideware
2. **Officer experience preview** — visa team and stakeholders preview what their staff will use, before WizSM integration is live
3. **Engineering reference** — frontend developers see the canonical integration pattern with Hawiya AI's API

The demo is **not** the WizSM UI. WizSM owns its own UI. The demo lives in the Hawiya AI repository as a reference application.

---

## 2. Scope

### In scope
- Three-panel single-page application: capture → extraction → identity resolution
- Three pre-built demo scenarios (new, returning, ambiguous match)
- Live confidence scoring and checksum visualisation
- Officer-style review and confirm actions
- Audit trail panel
- Toggle between mock mode (no backend) and live mode (real Hawiya API)
- Both real anonymised samples and stylised SVG mock passport

### Out of scope
- Multi-document workflows (only single passport per session in v1)
- Authentication flows (demo runs in dev mode with a fixed dev tenant)
- Mobile-responsive design (desktop demo only — sales meetings are on laptops)
- Localisation (English only in v1; Arabic display values are shown but UI chrome is English)
- Persistence between sessions (each demo run is fresh)

---

## 3. Audience and use cases

| Audience | Use case | Time available |
|---|---|---|
| Government CIO / minister | Boardroom demo, projected on screen | 2–5 min |
| Bank chief risk officer | Laptop-to-laptop demo over coffee | 5–10 min |
| Visa officer (PDD) | "What will I actually use?" preview | 10–20 min |
| Frontend engineer | Reference for their own integration | Self-paced |

The same UI must work for all four. The way it works for them differs: a CIO watches the operator; an officer drives.

---

## 4. Aesthetic direction

The demo inherits the Hawiya AI brand from the corporate deck and architecture artifacts:

- **Palette:** midnight ink (`#0A0E1A`), warm paper (`#F5F1EA`), crimson accent (`#8B1E2D`), warm gold (`#B8954A`), deep teal for data signals (`#2D5F5D`)
- **Typography:** Fraunces (display, serif) for headings, Inter Tight (sans) for body, JetBrains Mono for technical data, Amiri for Arabic
- **Tone:** refined editorial, government-appropriate, premium without being flashy
- **Motion:** purposeful — animations communicate process (extraction happening, checksums passing), never decorative
- **Density:** generous whitespace; this is not a dashboard

What the demo must *not* be: another generic AI-tool UI with purple gradients and Inter everywhere. It should feel like a sovereign government product.

---

## 5. Layout

### Master layout
A three-column composition on a paper-coloured background, occupying ~1280 × 800 viewport (sales laptops are typically 1440-wide MacBooks).

```
┌────────────────────────────────────────────────────────────────────────┐
│  [HEADER]  Hawiya AI · هوية         [scenario selector]   [mode toggle]│
├──────────────────┬─────────────────────────┬───────────────────────────┤
│                  │                         │                           │
│    CAPTURE       │      EXTRACTION         │   IDENTITY RESOLUTION     │
│    (left col)    │      (centre col)       │   (right col)             │
│                  │                         │                           │
│  - Drop zone     │  - Document preview     │  - Match action banner    │
│  - Sample tabs   │  - MRZ animation        │  - Person card            │
│  - Mockup tab    │  - Field-by-field       │  - History summary        │
│  - Scan button   │    confidence dots      │  - Officer actions        │
│                  │  - Checksum row         │  - Audit trail (expand)   │
│                  │                         │                           │
├──────────────────┴─────────────────────────┴───────────────────────────┤
│  [FOOTER]  Demo · v0.1 · /v1/identity/resolve · 287ms · tenant_id      │
└────────────────────────────────────────────────────────────────────────┘
```

### Header bar
- Left: brand mark (Fraunces "Hawiya AI" + Amiri "هوية" in crimson)
- Centre: scenario selector — three pill buttons ("New traveller" / "Returning" / "Ambiguous match")
- Right: mode toggle — "Mock" / "Live" with a tiny green dot when live API is reachable

### Footer
A monospace strip showing technical truth: API endpoint hit, response time, tenant_id, request_id. This is what engineers and CIOs both like to see — it proves it's real.

---

## 6. Capture panel (left column)

### Layout
- Header: "01 · CAPTURE" in mono accent
- Tab strip: "Real sample" / "Mock passport"
- Content area depending on tab
- Primary CTA: "Scan passport"

### Real sample tab
A grid of three thumbnails of anonymised passport samples (different nationalities, different conditions). Click to select. Selected one gets an accent border. Shows a small caption beneath: "ARE · machine-readable · clean scan."

### Mock passport tab
An SVG-rendered fake UAE passport with editable fields (name, passport number, DOB, nationality). Default values match Scenario A. Editing a field is allowed but shows a subtle "demo data" watermark. This lets a sales operator say "let me put your name in" — a small but powerful moment.

### Drop zone (always visible at the bottom)
A dashed rectangle that accepts file drops for the future case where a real image is uploaded. In v1 this is decorative — actual processing comes from the selected sample. Show a subtle hint: "Or drop a passport image here."

### Scan button
Large crimson button. Click triggers the extraction animation (centre column) and the resolution flow (right column).

---

## 7. Extraction panel (centre column)

This is the "wow" panel. Here's what it shows in sequence after Scan is pressed:

### Stage 1 — Document preview (immediate)
The selected passport image fades in. Subtle scan lines animate across it (CSS only, ~1.5 sec). This is theatre but earned theatre — it communicates "we're reading the document."

### Stage 2 — MRZ extraction (after 800ms)
A box overlays the bottom of the passport image, simulating MRZ region detection. Inside the box, the raw MRZ text types in monospace, character by character (~30ms per char). This sells "we're reading the ICAO standard, not guessing."

```
P<AREALMANSOORI<<AHMED<MOHAMMED<<<<<<<<<<<<<
A12345678 4ARE8504128M3009304784198512345678 8
```

### Stage 3 — Field extraction (after MRZ completes)
Below the document, a structured field display fades in field by field. Each field has:

- Label (small caps, mono)
- Value (large, serif if Arabic)
- Confidence dot (filled circle, colour from red → amber → green based on confidence)

Fields appear with staggered reveals (60ms between each):
- Document type
- Issuing country
- Passport number
- Surname
- Given names
- Nationality
- Date of birth
- Sex
- Expiry date
- Personal number
- Place of birth (lower confidence — visual zone only)
- Issuing authority (lower confidence)
- Name (Arabic) — in Amiri, larger

### Stage 4 — Checksum row (after fields complete)
A horizontal strip at the bottom. Five small checksum boxes (Passport Number / DOB / Expiry / Personal Number / Composite). Each starts grey. They flip green one at a time (200ms apart) with a small check icon. If a scenario has a checksum failure (none in v1), it flips amber/red.

### Stage 5 — "Extraction complete" badge
Small banner: "Extraction complete · 287ms · all checksums passed." This is the prompt for the right column to populate.

---

## 8. Identity resolution panel (right column)

Activates as Stage 5 fires.

### Layout depending on `match_action`

**`auto_matched` (Scenario B — Returning traveller)**

```
┌─────────────────────────────────────┐
│ ✓ MATCHED                           │
│   Auto-matched · confidence 0.99    │
│   on passport_number + DOB          │
├─────────────────────────────────────┤
│  Ahmed Al Mansoori                  │  ← Fraunces, large
│  أحمد محمد المنصوري                  │  ← Amiri
│                                     │
│  ARE · 1985-04-12 · M               │
│                                     │
│  3 prior interactions               │
│  Last seen: 12 Apr 2026             │
│                                     │
│  [View full profile] [Confirm]      │
└─────────────────────────────────────┘

▾ AUDIT TRAIL
  Decision: auto_match
  Match type: deterministic
  Matched on: passport_number, date_of_birth
  Model versions: mrz/passporteye-v0.1, match/det-v0.1
  Reversible until: 30 May 2026
```

**`new_record` (Scenario A — New traveller)**

```
┌─────────────────────────────────────┐
│ + NEW PERSON                        │
│   No existing record found          │
├─────────────────────────────────────┤
│  Ahmed Al Mansoori                  │
│  أحمد محمد المنصوري                  │
│                                     │
│  ARE · 1985-04-12 · M               │
│                                     │
│  Will create new Golden Record      │
│  in tenant: WizSM Production        │
│                                     │
│  [Cancel] [Create person]           │
└─────────────────────────────────────┘
```

**`suggested_match` (Scenario C — Ambiguous)**

```
┌─────────────────────────────────────┐
│ ⚠ REVIEW REQUIRED                   │
│   1 candidate · confidence 0.86     │
│   matched on: name_arabic + DOB     │
├─────────────────────────────────────┤
│  Extracted             Existing     │
│  ────────────         ──────────    │
│  Ahmad Almansouri  ≈  Ahmed Al      │
│  أحمد المنصوري        Mansoori      │
│  A12345678            Z98765432  ⚠  │
│  1985-04-12           1985-04-12 ✓  │
│  ARE                  ARE        ✓  │
│                                     │
│  [Reject — different person]        │
│  [Confirm — same person]            │
│  [Escalate to supervisor]           │
└─────────────────────────────────────┘
```

The differences row is the heart of Scenario C — it shows exactly what the algorithm sees and lets the officer make the call. This is the "human-in-the-loop" promise made visible.

### Audit trail
Always present beneath the result card, collapsed by default. Expanded shows:
- Decision and confidence
- Match type (deterministic / probabilistic / llm_assisted)
- Fields matched
- Model versions used
- Reversibility window
- Officer who took the action (in mock: "demo_officer")
- A "View raw API response" link that reveals the JSON Hawiya returned

---

## 9. Demo scenarios (canonical set)

Three scenarios are baked in, accessible via the header pills. Each has a fixed sample passport and fixed expected output, so the demo is reproducible.

### Scenario A — New traveller
- Passport: synthetic UAE passport, "Ahmed Al Mansoori," Emirates ID 784-1985-1234567-8
- Expected: clean MRZ, all checksums pass, no existing match → `new_record`
- Demo beat: "First time this person is seen. Hawiya creates a Golden Record."

### Scenario B — Returning traveller
- Passport: same person, Emirates ID matches an existing record
- Pre-seeded mock data: Ahmed Al Mansoori with 3 prior visa requests, last seen Apr 2026
- Expected: clean MRZ, deterministic match on Emirates ID + DOB → `auto_matched`
- Demo beat: "Three months later, same traveller. We recognise them instantly. No retyping. No duplicate."

### Scenario C — Ambiguous match (the showpiece)
- Passport: "Ahmad Almansouri" (different transliteration), different passport number from Scenario B's person, same DOB and nationality
- Expected: probabilistic match on Arabic name + DOB → `suggested_match`, confidence 0.86
- Demo beat: "Same person, different passport, different spelling. Algorithm flags it. Officer decides. Decision is logged."

This is the scenario that wins deals. It demonstrates: Arabic name handling, fuzzy matching, human-in-the-loop, and audit — all in one interaction.

---

## 10. Mock mode vs live mode

### Mock mode (default)
All API calls are stubbed in the frontend. Latencies are simulated (200–500ms with jitter) to feel real. State lives in React state only. Refreshing the page resets everything.

This is what a sales operator uses in 95% of demos. No backend. No network. No surprises.

### Live mode
Toggling on attempts to reach a configured Hawiya AI endpoint. The frontend calls the real `/v1/documents/extract` and `/v1/identity/resolve`. The mode toggle's status dot turns green if the service responds to `/v1/health` within 2 seconds, amber if reachable but slow, red if unreachable.

In live mode, scenarios A/B/C still drive what's submitted (so the demo remains predictable), but the response comes from the real service. This is what an engineer uses to validate their integration, and what an officer uses during pilot.

### Configuration
A small `.env`-style config file:
```
HAWIYA_API_URL=http://localhost:8000
HAWIYA_TENANT_ID=<dev-tenant-uuid>
HAWIYA_AUTH_TOKEN=<dev-bearer>
DEMO_MODE=mock | live
```

In a deployed demo, these are baked in at build time; in dev, they come from the environment.

---

## 11. Tech stack

Locked, no alternatives without a discussion:

- **React 18** with **Vite**
- **TypeScript** strict mode
- **Tailwind CSS** with a custom config that pulls from the Hawiya palette
- **Framer Motion** for the staged extraction animation (the one place complex motion is justified)
- **Zustand** for state (lightweight, sufficient for this scope — Redux is overkill)
- **Lucide React** for icons (consistent with the deck)
- **Fonts via Google Fonts:** Fraunces, Inter Tight, JetBrains Mono, Amiri

No UI component libraries (shadcn/ui, MUI, Chakra). The aesthetic is too specific. Build the few components needed by hand.

The demo lives in `apps/demo-ui/` in a monorepo structure, or in a separate `hawiya-demo` repo. Either is acceptable; monorepo is preferred so the demo and the OpenAPI client stay in sync.

### Folder structure
```
apps/demo-ui/
├── public/
│   └── samples/                  # Anonymised passport sample images
├── src/
│   ├── components/
│   │   ├── CapturePanel.tsx
│   │   ├── ExtractionPanel.tsx
│   │   ├── IdentityPanel.tsx
│   │   ├── AuditTrail.tsx
│   │   ├── MockPassport.tsx      # SVG passport renderer
│   │   ├── ConfidenceDot.tsx
│   │   ├── ChecksumRow.tsx
│   │   └── ScenarioSelector.tsx
│   ├── scenarios/
│   │   ├── scenarioA.ts          # New traveller
│   │   ├── scenarioB.ts          # Returning traveller
│   │   └── scenarioC.ts          # Ambiguous match
│   ├── api/
│   │   ├── client.ts             # Real Hawiya API client (live mode)
│   │   └── mock.ts               # Mock responses (mock mode)
│   ├── store/
│   │   └── demo.ts               # Zustand store
│   ├── styles/
│   │   └── globals.css
│   ├── App.tsx
│   └── main.tsx
├── tailwind.config.ts
├── vite.config.ts
└── package.json
```

---

## 12. Animation timing reference

The extraction sequence is the most visible part. Get this right and the demo sells itself.

| Stage | Trigger | Duration | Notes |
|---|---|---|---|
| Document fade-in | Scan pressed | 300ms ease-out | Image opacity 0 → 1 |
| Scan-line sweep | At 200ms | 1500ms | Linear, top → bottom |
| MRZ box appear | At 800ms | 200ms | Slight scale-in |
| MRZ text type | At 1000ms | ~1500ms | 30ms per char, two lines |
| Field 1 reveal | At 2400ms | 240ms | y: 6px → 0, opacity 0 → 1 |
| Subsequent fields | +60ms each | 240ms | Staggered |
| Checksum 1 flip | At 3200ms | 200ms | grey → green, check icon scale-in |
| Subsequent checksums | +200ms each | 200ms | |
| "Extraction complete" badge | At 4400ms | 300ms | Slide up from bottom |
| Identity panel populate | At 4500ms | 400ms | Card fade + slight rise |

Total: under 5 seconds. Long enough to be impressive. Short enough not to bore.

A "skip animation" button (subtle, top-right of the centre column) lets repeat demos go faster — sales people who do this five times a day will need it.

---

## 13. Accessibility

The demo is for live presentations on a projector and laptops. Some considerations:

- **Contrast:** all text passes WCAG AA against the warm paper background
- **Font size:** body text 16px minimum; technical mono text 13px minimum
- **No motion-only signals:** confidence is shown by both colour and number, not just colour
- **Keyboard navigable:** scenario selector, scan button, officer actions all reachable via Tab
- **Pause/skip animation:** for users with vestibular sensitivities or rushed demos
- **Screen reader announcements:** stage transitions ("MRZ extracted, all checksums passed") spoken via `aria-live="polite"`

---

## 14. What the demo intentionally hides

Things that exist in the real product but aren't worth showing in a 5-minute demo:

- **Tenant selection** (the demo runs in a fixed tenant)
- **Auth flows** (assumed, not shown)
- **Multi-document submission** (single passport per session)
- **Bulk processing** (one at a time)
- **Officer login screens, role assignment** (assumed)
- **Configuration UI** (back-office concern)
- **Detailed performance metrics** (the footer hint is enough)

A buyer who asks for any of these gets a follow-up meeting, not a demo expansion.

---

## 15. When this gets built (timeline)

The demo is **not** Phase 1 critical-path work. The Phase 1 plan (`BUILD_PLAN.md`) ships a working backend and a real consumer integration; the demo is a sales/presentation asset that runs in parallel.

Suggested timing:

- **Week 1–3:** Backend team executes Phase 1 build plan
- **Week 3–4:** Frontend engineer (separate from backend team) builds the demo against the OpenAPI spec — mock mode only at first
- **Week 4–5:** Demo wired to the real Hawiya AI service in dev, live mode tested
- **Week 5–6:** Demo rehearsed with sales/product team, refined based on actual demo feedback

Total effort: roughly 2–3 weeks of one frontend engineer, working in parallel with the backend build.

If you don't have a dedicated frontend engineer, the demo can wait until after Phase 1 ships. **Do not pull a backend engineer onto the demo during Phase 1.** The backend timeline is already tight.

---

## 16. Acceptance criteria

The demo is "done" when:

- All three scenarios work end-to-end in mock mode
- Live mode successfully calls a running Hawiya AI service
- A non-technical sales person can run the full demo without coaching after a 30-min walkthrough
- An officer (not a sales person) can run Scenario C and articulate what's happening without prompting
- The demo runs offline (mock mode) — no network required
- A frontend engineer can read this doc + the codebase and add a fourth scenario in under a day

---

## 17. Future enhancements (post-Phase-1)

Things to add later but not on day one:

- **Drag-and-drop a real image** and process it through live mode
- **Multi-document scenario** showing a passport + supporting letter validated together
- **Bulk dedup demo** showing a CSV of records being deduplicated
- **Audit timeline** showing the full history of a person across all interactions
- **Configurable thresholds** so a buyer can dial confidence and see the match action change live
- **Arabic-first UI mode** for Arabic-speaking buyers
- **Export to PDF** of the audit trail for a given decision

---

## 18. Open questions for the team

To answer before building:

1. **Where does the demo live?** Same repo (`apps/demo-ui/`) or separate (`hawiya-demo`)? Recommendation: same monorepo.
2. **Who maintains it?** Frontend lead on the consumer team, or a dedicated DX engineer? Recommendation: dedicated DX so it doesn't compete with WizSM integration work.
3. **Is the mock passport SVG OK to ship?** Trademark/legal review needed if it looks too much like a real UAE passport. Recommendation: stylise it clearly as "demo" — distinct logo, watermark.
4. **What's the URL for the deployed demo?** `demo.hawiya.<domain>`? Internal only or shareable with prospects? Recommendation: internal-only at first, a shareable link with PIN for prospects later.
5. **Anonymised samples — where do they come from?** Either generated synthetically or from a public-domain source. Never real customer documents, even anonymised.
