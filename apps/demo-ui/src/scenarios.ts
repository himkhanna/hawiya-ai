// Three baked-in demo scenarios per demo-ui.md §9, adapted to what the
// Phase 1 backend can actually do. Order-independent: each scenario can
// be triggered in isolation and the result is deterministic given the
// pre-seeded tenant (`scripts/seed_demo_persons.py`).

export type ScenarioId = "A" | "B" | "C";

export interface Scenario {
  id: ScenarioId;
  pillLabel: string;
  title: string;
  blurb: string;
  imagePath: string;
  // What the demo *expects* the API to return — used for the call-out
  // copy (e.g. "the system refused to auto-match").
  expectedAction:
    | "new_record"
    | "auto_matched"
    | "suggested_match";
  // Two-line narrative the operator reads to the audience.
  talkTrack: string[];
}

export const SCENARIOS: readonly Scenario[] = [
  {
    id: "A",
    pillLabel: "New traveller",
    title: "First-time submission",
    blurb:
      "A passport this tenant has never seen before. Hawiya AI extracts " +
      "the data, validates the ICAO checksums, and creates a Golden Record.",
    imagePath: "/scenarios/scenario-a.jpg",
    expectedAction: "new_record",
    talkTrack: [
      "First time we see this passport. The system has nothing to match against.",
      "It extracts every field, validates the checksums, and creates a new record.",
      "Click Scan again to see what happens when the same passport returns.",
    ],
  },
  {
    id: "B",
    pillLabel: "Returning traveller",
    title: "Returning citizen, recognised",
    blurb:
      "This passport belongs to a person already in the registry. " +
      "Deterministic match on passport number + nationality + DOB.",
    imagePath: "/scenarios/scenario-b.jpg",
    expectedAction: "auto_matched",
    talkTrack: [
      "Six months later. Same person, same passport.",
      "The system recognises them instantly. No officer typing, no duplicate.",
      "This is the headline outcome.",
    ],
  },
  {
    id: "C",
    pillLabel: "Possible duplicate",
    title: "Possible duplicate — review required",
    blurb:
      "Same passport number as an existing record, but with a different " +
      "date of birth. Could be a tampered document or an officer typo. " +
      "The system refuses to auto-link.",
    imagePath: "/scenarios/scenario-c.jpg",
    expectedAction: "suggested_match",
    talkTrack: [
      "This is the human-in-the-loop scenario.",
      "Passport number matches an existing person — but the date of birth doesn't.",
      "Hawiya AI surfaces it for officer review. It will not auto-link a " +
        "sovereign-affecting decision without approval.",
    ],
  },
] as const;

export async function loadScenarioImage(
  scenario: Scenario
): Promise<Blob> {
  const r = await fetch(scenario.imagePath);
  if (!r.ok) {
    throw new Error(
      `Failed to load ${scenario.imagePath}: HTTP ${r.status}`
    );
  }
  return r.blob();
}
