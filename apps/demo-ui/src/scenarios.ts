// Two demo modes per consumer-shape:
//
//   - "wizsm"    : extract-only. Hawiya OCRs the passport and returns
//                  structured JSON. Consumer (e.g. WizSM at the Diwan)
//                  runs its own dedup against its own registry. The
//                  matching / Person Registry features of Hawiya AI
//                  are out of scope for this consumer.
//
//   - "registry" : full Hawiya stack. Consumer relies on Hawiya's
//                  Person Registry for dedup and gets back an action
//                  (new_record / auto_matched / suggested_match).
//                  Used by other prospects (banking KYC, healthcare,
//                  smaller gov departments without their own registry).
//
// Each scenario carries the MRZ string for the typing animation and a
// short operator talk-track for the demo.

import { buildTd3Mrz, type PassportFields } from "./mrz";

export type Mode = "wizsm" | "registry";
export type ScenarioId =
  | "uae"
  | "usa"
  | "gbr"
  | "A"
  | "B"
  | "C";

export interface Scenario {
  id: ScenarioId;
  mode: Mode;
  pillLabel: string;
  title: string;
  blurb: string;
  imagePath: string;
  mrzLine1: string;
  mrzLine2: string;
  // Registry mode only.
  expectedAction?: "new_record" | "auto_matched" | "suggested_match";
  talkTrack: string[];
}

const PASSPORTS: Record<ScenarioId, PassportFields> = {
  uae: {
    issuing: "ARE",
    nationality: "ARE",
    surname: "ALMANSOORI",
    given: "MOHAMED",
    passportNumber: "P1234567",
    dob: "900112",
    sex: "M",
    expiry: "300101",
  },
  usa: {
    issuing: "USA",
    nationality: "USA",
    surname: "SMITH",
    given: "JOHN ROBERT",
    passportNumber: "USA123456",
    dob: "780404",
    sex: "M",
    expiry: "320404",
  },
  gbr: {
    issuing: "GBR",
    nationality: "GBR",
    surname: "WINDSOR",
    given: "ELIZABETH ALEXANDRA",
    passportNumber: "GBR987654",
    dob: "850421",
    sex: "F",
    expiry: "350421",
  },
  A: {
    issuing: "ARE",
    nationality: "ARE",
    surname: "ALMANSOORI",
    given: "MOHAMED",
    passportNumber: "P1234567",
    dob: "900112",
    sex: "M",
    expiry: "300101",
  },
  B: {
    issuing: "ARE",
    nationality: "ARE",
    surname: "ALMANSOORI",
    given: "AHMED",
    passportNumber: "S0100100",
    dob: "820904",
    sex: "M",
    expiry: "300101",
  },
  C: {
    issuing: "ARE",
    nationality: "ARE",
    surname: "ALMANSOORI",
    given: "AHMED",
    passportNumber: "S0100100",
    dob: "850606",
    sex: "M",
    expiry: "300101",
  },
};

function withMrz(s: Omit<Scenario, "mrzLine1" | "mrzLine2">): Scenario {
  const [line1, line2] = buildTd3Mrz(PASSPORTS[s.id]);
  return { ...s, mrzLine1: line1, mrzLine2: line2 };
}

export const SCENARIOS: readonly Scenario[] = [
  // --- WizSM (extract-only) ----------------------------------------------
  withMrz({
    id: "uae",
    mode: "wizsm",
    pillLabel: "UAE passport",
    title: "UAE national presents passport",
    blurb:
      "Officer scans a UAE passport. Hawiya AI returns structured fields " +
      "for WizSM to consume. WizSM runs its own duplicate check.",
    imagePath: "/scenarios/scenario-uae.jpg",
    talkTrack: [
      "Officer at the counter scans this UAE passport.",
      "WizSM POSTs the image to /v1/documents/extract.",
      "Hawiya returns the JSON on the right. WizSM stores it and runs its " +
        "own duplicate check against the Diwan's registry.",
    ],
  }),
  withMrz({
    id: "usa",
    mode: "wizsm",
    pillLabel: "US passport",
    title: "US visitor presents passport",
    blurb:
      "Same flow, different nationality. Hawiya handles ICAO 9303 for " +
      "every country that issues a TD3 passport.",
    imagePath: "/scenarios/scenario-usa.jpg",
    talkTrack: [
      "Different nationality, same flow. Hawiya speaks ICAO 9303.",
      "All five checksums validate the OCR — your team trusts the data.",
    ],
  }),
  withMrz({
    id: "gbr",
    mode: "wizsm",
    pillLabel: "UK passport",
    title: "UK visitor presents passport",
    blurb:
      "A British passport with multiple given names. Hawiya parses the " +
      "MRZ correctly, including name sub-tokens.",
    imagePath: "/scenarios/scenario-gbr.jpg",
    talkTrack: [
      "Compound given names ('Elizabeth Alexandra') — handled per ICAO.",
      "Confidence dots show field-level reliability.",
    ],
  }),

  // --- Registry (extract + Hawiya match) ---------------------------------
  withMrz({
    id: "A",
    mode: "registry",
    pillLabel: "New traveller",
    title: "First-time submission",
    blurb:
      "A passport this tenant has never seen. Hawiya creates a Golden Record.",
    imagePath: "/scenarios/scenario-a.jpg",
    expectedAction: "new_record",
    talkTrack: [
      "First time we see this passport.",
      "It extracts every field, validates checksums, creates a new record.",
      "Click Scan again to see what happens when the same passport returns.",
    ],
  }),
  withMrz({
    id: "B",
    mode: "registry",
    pillLabel: "Returning traveller",
    title: "Returning citizen, recognised",
    blurb:
      "This passport is already in the registry. Deterministic match on " +
      "passport number + nationality + DOB.",
    imagePath: "/scenarios/scenario-b.jpg",
    expectedAction: "auto_matched",
    talkTrack: [
      "Six months later. Same person, same passport.",
      "The system recognises them instantly. No officer typing, no duplicate.",
    ],
  }),
  withMrz({
    id: "C",
    mode: "registry",
    pillLabel: "Possible duplicate",
    title: "Possible duplicate — review required",
    blurb:
      "Same passport number as an existing record but different DOB. " +
      "System refuses to auto-link.",
    imagePath: "/scenarios/scenario-c.jpg",
    expectedAction: "suggested_match",
    talkTrack: [
      "Passport number matches an existing person, DOB doesn't.",
      "Hawiya AI surfaces it for officer review. Will not auto-link.",
    ],
  }),
];

export function scenariosFor(mode: Mode): Scenario[] {
  return SCENARIOS.filter((s) => s.mode === mode);
}

export async function loadScenarioImage(scenario: Scenario): Promise<Blob> {
  const r = await fetch(scenario.imagePath);
  if (!r.ok)
    throw new Error(`Failed to load ${scenario.imagePath}: HTTP ${r.status}`);
  return r.blob();
}
