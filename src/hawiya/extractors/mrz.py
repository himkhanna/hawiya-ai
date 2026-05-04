"""TD3 (passport) MRZ parser.

A TD3 MRZ is exactly two lines of 44 characters each. This module is a
pure function: bytes/images are out of scope (see ``extractors.ocr`` for
the OCR adapter that produces these strings).

Field layout — line 1 (44 chars):
    1-2     document type (e.g. ``P<``)
    3-5     issuing state (3-letter ISO 3166-1)
    6-44    name: SURNAME<<GIVEN<NAMES<<<<…

Field layout — line 2 (44 chars):
    1-9     document number
    10      doc number check digit
    11-13   nationality (3-letter)
    14-19   date of birth (YYMMDD)
    20      DOB check digit
    21      sex (M / F / <)
    22-27   date of expiry (YYMMDD)
    28      expiry check digit
    29-42   personal number / optional data
    43      personal check digit
    44      composite check digit

CLAUDE.md §7 calls for 5 checksums; this parser computes all of them and
records pass/fail per field on the resulting ``ChecksumReport``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from hawiya.extractors.types import ChecksumReport, ParsedMRZ, Sex
from hawiya.extractors.validators import (
    TD3_COMPOSITE_CHECK,
    TD3_DOB,
    TD3_DOB_CHECK,
    TD3_DOC_NUMBER,
    TD3_DOC_NUMBER_CHECK,
    TD3_EXPIRY,
    TD3_EXPIRY_CHECK,
    TD3_PERSONAL,
    TD3_PERSONAL_CHECK,
    compute_check_digit,
    verify,
)

TD3_LINE_LENGTH = 44

# Year window: a 2-digit year > (current_year_yy + DOB_FUTURE_SLACK) is
# treated as 19YY for DOB. Slack is small because future-dated DOBs are
# always wrong but a newborn's record may briefly look future-dated due to
# tz skew.
DOB_FUTURE_SLACK = 1
EXPIRY_CENTURY_CUTOFF = 50  # YY < cutoff → 20YY for expiry, else 19YY


class MRZFormatError(ValueError):
    """The MRZ string is malformed before any field-level checks."""


def parse_td3(line1: str, line2: str) -> ParsedMRZ:
    """Parse a TD3 MRZ. Both lines must be exactly 44 characters.

    Raises ``MRZFormatError`` on length mismatch. Field-level issues
    (invalid dates, failed checksums) do NOT raise — they surface in the
    returned ``ParsedMRZ`` (date fields = None, checksum flags = False).
    """
    if len(line1) != TD3_LINE_LENGTH:
        raise MRZFormatError(f"line 1 must be {TD3_LINE_LENGTH} chars, got {len(line1)}")
    if len(line2) != TD3_LINE_LENGTH:
        raise MRZFormatError(f"line 2 must be {TD3_LINE_LENGTH} chars, got {len(line2)}")

    full = line1 + line2

    # Line 1
    document_type = line1[0:2].rstrip("<")
    issuing_country = line1[2:5]
    surname, given_names = _parse_name(line1[5:44])

    # Line 2
    document_number_raw = full[TD3_DOC_NUMBER]
    document_number = document_number_raw.rstrip("<")
    doc_number_check_char = full[TD3_DOC_NUMBER_CHECK]

    nationality = line2[10:13]

    dob_raw = full[TD3_DOB]
    dob_check_char = full[TD3_DOB_CHECK]
    date_of_birth = _parse_dob(dob_raw)

    sex_char = line2[20]
    sex = _parse_sex(sex_char)

    expiry_raw = full[TD3_EXPIRY]
    expiry_check_char = full[TD3_EXPIRY_CHECK]
    date_of_expiry = _parse_expiry(expiry_raw)

    personal_raw = full[TD3_PERSONAL]
    personal_number = personal_raw.rstrip("<")
    personal_check_char = full[TD3_PERSONAL_CHECK]

    composite_check_char = full[TD3_COMPOSITE_CHECK]

    # Checksums
    doc_number_ok = verify(document_number_raw, doc_number_check_char)
    dob_ok = verify(dob_raw, dob_check_char)
    expiry_ok = verify(expiry_raw, expiry_check_char)
    personal_ok = verify(personal_raw, personal_check_char)

    composite_field = (
        document_number_raw
        + doc_number_check_char
        + dob_raw
        + dob_check_char
        + expiry_raw
        + expiry_check_char
        + personal_raw
        + personal_check_char
    )
    composite_ok = compute_check_digit(composite_field) == _parse_check_for_composite(
        composite_check_char
    )

    checksums = ChecksumReport(
        doc_number=doc_number_ok,
        dob=dob_ok,
        expiry=expiry_ok,
        personal=personal_ok,
        composite=composite_ok,
    )

    return ParsedMRZ(
        document_type=document_type,
        issuing_country=issuing_country,
        surname=surname,
        given_names=given_names,
        document_number=document_number,
        nationality=nationality,
        date_of_birth=date_of_birth,
        sex=sex,
        date_of_expiry=date_of_expiry,
        personal_number=personal_number,
        checksums=checksums,
        raw_line_1=line1,
        raw_line_2=line2,
    )


def _parse_name(field: str) -> tuple[str, str]:
    """Split ``SURNAME<<GIVEN<NAMES<<<…`` into (surname, given names)."""
    parts = field.split("<<", 1)
    surname = parts[0].replace("<", " ").strip()
    given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
    return surname, given


def _parse_sex(ch: str) -> Sex | None:
    if ch == "M":
        return Sex.MALE
    if ch == "F":
        return Sex.FEMALE
    if ch in ("X", "<"):
        return Sex.UNSPECIFIED
    return None


def _parse_dob(raw: str) -> date | None:
    """YYMMDD, century inferred relative to today (no future DOBs)."""
    if not raw.isdigit():
        return None
    yy = int(raw[0:2])
    mm = int(raw[2:4])
    dd = int(raw[4:6])
    today = datetime.now(tz=UTC).date()
    current_yy = today.year % 100
    century = 1900 if yy > current_yy + DOB_FUTURE_SLACK else 2000
    try:
        return date(century + yy, mm, dd)
    except ValueError:
        return None


def _parse_expiry(raw: str) -> date | None:
    """YYMMDD, century inferred — most expiries are within 20YY range."""
    if not raw.isdigit():
        return None
    yy = int(raw[0:2])
    mm = int(raw[2:4])
    dd = int(raw[4:6])
    century = 2000 if yy < EXPIRY_CENTURY_CUTOFF else 1900
    try:
        return date(century + yy, mm, dd)
    except ValueError:
        return None


def _parse_check_for_composite(ch: str) -> int:
    """The composite check digit must itself be 0-9 (not '<') per ICAO."""
    if "0" <= ch <= "9":
        return int(ch)
    return -1  # forces mismatch
