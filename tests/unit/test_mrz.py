"""TD3 MRZ parser tests, including 20 synthetic cases per BUILD_PLAN week 2."""

from __future__ import annotations

from datetime import date

import pytest

from hawiya.extractors.mrz import MRZFormatError, parse_td3
from hawiya.extractors.types import ChecksumStatus, Sex
from hawiya.extractors.validators import compute_check_digit

# ---------------------------------------------------------------------------
# Helpers to build synthetic TD3 MRZ strings with valid check digits.
# ---------------------------------------------------------------------------

NAME_LENGTH = 39  # line 1 chars 6-44


def _pad(value: str, length: int) -> str:
    if len(value) > length:
        raise ValueError(f"value {value!r} too long for field of {length}")
    return value + "<" * (length - len(value))


def _name_field(surname: str, given: str) -> str:
    """Build the 39-char name field for line 1."""
    body = surname.upper().replace(" ", "<") + "<<" + given.upper().replace(" ", "<")
    return _pad(body, NAME_LENGTH)


def build_td3(
    *,
    issuing: str = "ARE",
    nationality: str = "ARE",
    surname: str = "ALMANSOORI",
    given: str = "MOHAMED ALI",
    doc_number: str = "P1234567",
    dob: str = "900112",  # YYMMDD
    sex: str = "M",
    expiry: str = "300101",
    personal: str = "",
) -> tuple[str, str]:
    """Build a TD3 MRZ pair with all 5 check digits computed correctly."""
    line1 = "P<" + issuing + _name_field(surname, given)
    assert len(line1) == 44, f"line1 length {len(line1)}"

    doc_field = _pad(doc_number, 9)
    doc_check = str(compute_check_digit(doc_field))
    dob_check = str(compute_check_digit(dob))
    expiry_check = str(compute_check_digit(expiry))
    personal_field = _pad(personal, 14)
    personal_check = str(compute_check_digit(personal_field))

    composite_input = (
        doc_field
        + doc_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + personal_field
        + personal_check
    )
    composite_check = str(compute_check_digit(composite_input))

    line2 = (
        doc_field
        + doc_check
        + nationality
        + dob
        + dob_check
        + sex
        + expiry
        + expiry_check
        + personal_field
        + personal_check
        + composite_check
    )
    assert len(line2) == 44, f"line2 length {len(line2)}"
    return line1, line2


# ---------------------------------------------------------------------------
# 20 synthetic specimens — varied countries, names, sex, doc numbers, dates.
# ---------------------------------------------------------------------------

SPECIMENS = [
    dict(
        issuing="ARE",
        nationality="ARE",
        surname="ALMANSOORI",
        given="MOHAMED",
        doc_number="P1234567",
        dob="900112",
        sex="M",
        expiry="300101",
        personal="",
    ),
    dict(
        issuing="ARE",
        nationality="ARE",
        surname="ALSHAMSI",
        given="FATIMA AISHA",
        doc_number="P9876543",
        dob="850606",
        sex="F",
        expiry="290815",
        personal="",
    ),
    dict(
        issuing="USA",
        nationality="USA",
        surname="SMITH",
        given="JOHN ROBERT",
        doc_number="123456789",
        dob="780404",
        sex="M",
        expiry="320404",
        personal="",
    ),
    dict(
        issuing="GBR",
        nationality="GBR",
        surname="WINDSOR",
        given="ELIZABETH ALEXANDRA",
        doc_number="GB1234567",
        dob="260421",
        sex="F",
        expiry="350421",
        personal="",
    ),
    dict(
        issuing="FRA",
        nationality="FRA",
        surname="DUPONT",
        given="JEAN PIERRE",
        doc_number="FR0001234",
        dob="650730",
        sex="M",
        expiry="280730",
        personal="PARIS",
    ),
    dict(
        issuing="DEU",
        nationality="DEU",
        surname="MUELLER",
        given="ANNA MARIA",
        doc_number="DE9988776",
        dob="930215",
        sex="F",
        expiry="300215",
        personal="",
    ),
    dict(
        issuing="JPN",
        nationality="JPN",
        surname="TANAKA",
        given="YUKI",
        doc_number="TZ0123456",
        dob="881111",
        sex="F",
        expiry="291230",
        personal="",
    ),
    dict(
        issuing="IND",
        nationality="IND",
        surname="PATEL",
        given="RAVI KUMAR",
        doc_number="N1234567",
        dob="760315",
        sex="M",
        expiry="310315",
        personal="",
    ),
    dict(
        issuing="EGY",
        nationality="EGY",
        surname="HASSAN",
        given="OMAR",
        doc_number="EG7654321",
        dob="950808",
        sex="M",
        expiry="290808",
        personal="",
    ),
    dict(
        issuing="SAU",
        nationality="SAU",
        surname="ALSAUDI",
        given="KHALID",
        doc_number="SA1112223",
        dob="820505",
        sex="M",
        expiry="270505",
        personal="",
    ),
    dict(
        issuing="KWT",
        nationality="KWT",
        surname="ALSABAH",
        given="NOURA",
        doc_number="KW3334445",
        dob="911011",
        sex="F",
        expiry="280101",
        personal="",
    ),
    dict(
        issuing="QAT",
        nationality="QAT",
        surname="ALTHANI",
        given="HAMAD",
        doc_number="QA5556667",
        dob="700102",
        sex="M",
        expiry="290504",
        personal="",
    ),
    dict(
        issuing="OMN",
        nationality="OMN",
        surname="ALBUSAIDI",
        given="SAID",
        doc_number="OM7778889",
        dob="830707",
        sex="M",
        expiry="280707",
        personal="",
    ),
    dict(
        issuing="BHR",
        nationality="BHR",
        surname="ALKHALIFA",
        given="ISA",
        doc_number="BH9990001",
        dob="990929",
        sex="M",
        expiry="320929",
        personal="",
    ),
    dict(
        issuing="LBN",
        nationality="LBN",
        surname="HARIRI",
        given="LEILA",
        doc_number="LB1212121",
        dob="000229",
        sex="F",
        expiry="300229",
        personal="",
    ),
    dict(
        issuing="JOR",
        nationality="JOR",
        surname="ALHASHEMI",
        given="ABDULLAH",
        doc_number="JO3434343",
        dob="620812",
        sex="M",
        expiry="261231",
        personal="",
    ),
    dict(
        issuing="MAR",
        nationality="MAR",
        surname="ELALAOUI",
        given="YASMINE",
        doc_number="MA5656565",
        dob="940420",
        sex="F",
        expiry="270420",
        personal="",
    ),
    dict(
        issuing="TUN",
        nationality="TUN",
        surname="BENALI",
        given="MOHAMED SALAH",
        doc_number="TN7878787",
        dob="870630",
        sex="M",
        expiry="300630",
        personal="",
    ),
    dict(
        issuing="DZA",
        nationality="DZA",
        surname="BOUTEFLIKA",
        given="AMINA",
        doc_number="DZ9090909",
        dob="010101",
        sex="F",
        expiry="310101",
        personal="ALGER",
    ),
    dict(
        issuing="CAN",
        nationality="CAN",
        surname="OREILLY",
        given="SEAN",
        doc_number="CA0202020",
        dob="681225",
        sex="M",
        expiry="281225",
        personal="",
    ),
]
assert len(SPECIMENS) == 20, "must keep 20 synthetic specimens"


@pytest.mark.parametrize("spec", SPECIMENS, ids=[s["doc_number"] for s in SPECIMENS])
def test_synthetic_specimen_round_trips(spec: dict[str, str]) -> None:
    line1, line2 = build_td3(**spec)
    parsed = parse_td3(line1, line2)

    assert parsed.document_type == "P"
    assert parsed.issuing_country == spec["issuing"]
    assert parsed.nationality == spec["nationality"]
    assert parsed.document_number == spec["doc_number"].rstrip("<")
    assert parsed.surname == spec["surname"].upper()
    # Given names join with single space; the builder uppercases.
    expected_given = spec["given"].upper()
    assert parsed.given_names == expected_given
    assert parsed.checksums.status is ChecksumStatus.ALL_PASS


def test_specimen_dob_century_inference_past_year() -> None:
    line1, line2 = build_td3(dob="900112")
    parsed = parse_td3(line1, line2)
    assert parsed.date_of_birth == date(1990, 1, 12)


def test_specimen_dob_century_inference_recent_year() -> None:
    # Current is 2026; YY=24 → 2024 (recent past). YY=27 → 1927 (must not be future).
    line1, line2 = build_td3(dob="240115")
    parsed = parse_td3(line1, line2)
    assert parsed.date_of_birth == date(2024, 1, 15)


def test_expiry_uses_2000s_when_within_window() -> None:
    line1, line2 = build_td3(expiry="350101")
    parsed = parse_td3(line1, line2)
    assert parsed.date_of_expiry == date(2035, 1, 1)


def test_sex_male_female_unspecified() -> None:
    for raw, expected in [("M", Sex.MALE), ("F", Sex.FEMALE), ("X", Sex.UNSPECIFIED)]:
        line1, line2 = build_td3(sex=raw)
        parsed = parse_td3(line1, line2)
        assert parsed.sex is expected


def test_sex_filler_treated_as_unspecified() -> None:
    line1, line2 = build_td3(sex="<")
    parsed = parse_td3(line1, line2)
    assert parsed.sex is Sex.UNSPECIFIED


def test_personal_number_rstrip_fillers() -> None:
    line1, line2 = build_td3(personal="ABC123")
    parsed = parse_td3(line1, line2)
    assert parsed.personal_number == "ABC123"


def test_invalid_dob_returns_none() -> None:
    # Build a valid MRZ then corrupt the DOB with an invalid month.
    line1, line2 = build_td3(dob="901301")
    parsed = parse_td3(line1, line2)
    assert parsed.date_of_birth is None
    # Checksum is still valid because it's computed over the raw chars.
    assert parsed.checksums.dob is True


def test_corrupted_doc_number_check_fails_doc_and_composite() -> None:
    line1, line2 = build_td3()
    # Flip the doc-number check digit.
    bad_check = "0" if line2[9] != "0" else "1"
    line2_bad = line2[:9] + bad_check + line2[10:]
    parsed = parse_td3(line1, line2_bad)
    assert parsed.checksums.doc_number is False
    assert parsed.checksums.composite is False
    assert parsed.checksums.status is ChecksumStatus.PARTIAL


def test_all_checksums_corrupted_yields_all_fail() -> None:
    line1, line2 = build_td3()
    # Corrupt every check digit position by adding 1 mod 10.
    positions = [9, 19, 27, 42, 43]
    chars = list(line2)
    for p in positions:
        chars[p] = str((int(chars[p]) + 1) % 10)
    parsed = parse_td3(line1, "".join(chars))
    assert parsed.checksums.status is ChecksumStatus.ALL_FAIL


def test_line_length_mismatch_raises() -> None:
    with pytest.raises(MRZFormatError):
        parse_td3("P<ARE" + "<" * 38, "P1234567" + "<" * 36)
    with pytest.raises(MRZFormatError):
        parse_td3("P<ARE" + "<" * 39, "short")


def test_empty_personal_check_passes() -> None:
    line1, line2 = build_td3(personal="")
    parsed = parse_td3(line1, line2)
    assert parsed.personal_number == ""
    assert parsed.checksums.personal is True
