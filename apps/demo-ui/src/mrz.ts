// ICAO 9303 MRZ helpers, mirrored from
// src/hawiya/extractors/validators.py + scripts/generate_passport_image.py
// so the UI can reproduce the exact MRZ that the backend will OCR.

const WEIGHTS = [7, 3, 1];

function charValue(ch: string): number {
  if (ch === "<") return 0;
  if (ch >= "0" && ch <= "9") return ch.charCodeAt(0) - "0".charCodeAt(0);
  if (ch >= "A" && ch <= "Z") return ch.charCodeAt(0) - "A".charCodeAt(0) + 10;
  throw new Error(`invalid MRZ char: ${ch}`);
}

export function computeCheckDigit(field: string): number {
  let total = 0;
  for (let i = 0; i < field.length; i++) {
    total += charValue(field[i]) * WEIGHTS[i % 3];
  }
  return total % 10;
}

function pad(value: string, length: number): string {
  if (value.length > length) {
    throw new Error(`value ${value} too long for field of ${length}`);
  }
  return value + "<".repeat(length - value.length);
}

export interface PassportFields {
  issuing: string;       // 3-letter
  nationality: string;   // 3-letter
  surname: string;
  given: string;
  passportNumber: string;
  dob: string;           // YYMMDD
  sex: "M" | "F" | "X";
  expiry: string;        // YYMMDD
  personal?: string;
}

export function buildTd3Mrz(p: PassportFields): [string, string] {
  const nameField = pad(
    p.surname.toUpperCase().replace(/ /g, "<") +
      "<<" +
      p.given.toUpperCase().replace(/ /g, "<"),
    39
  );
  const line1 = "P<" + p.issuing + nameField;
  if (line1.length !== 44) throw new Error(`line1 length ${line1.length}`);

  const docField = pad(p.passportNumber, 9);
  const docCheck = String(computeCheckDigit(docField));
  const dobCheck = String(computeCheckDigit(p.dob));
  const expCheck = String(computeCheckDigit(p.expiry));
  const personalField = pad(p.personal ?? "", 14);
  const personalCheck = String(computeCheckDigit(personalField));
  const compositeInput =
    docField +
    docCheck +
    p.dob +
    dobCheck +
    p.expiry +
    expCheck +
    personalField +
    personalCheck;
  const compositeCheck = String(computeCheckDigit(compositeInput));

  const line2 =
    docField +
    docCheck +
    p.nationality +
    p.dob +
    dobCheck +
    p.sex +
    p.expiry +
    expCheck +
    personalField +
    personalCheck +
    compositeCheck;
  if (line2.length !== 44) throw new Error(`line2 length ${line2.length}`);
  return [line1, line2];
}

// Five ICAO 9303 checksums on a TD3 MRZ. Synthetic specimens always pass
// all five — kept as a constant so the UI can show the row without
// re-parsing the OCR result.
export const CHECKSUM_LABELS = [
  "Passport No.",
  "Date of birth",
  "Date of expiry",
  "Personal No.",
  "Composite",
] as const;
