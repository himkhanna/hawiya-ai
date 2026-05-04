"""Unit tests for ICAO 9303 check-digit primitives.

Reference values come from the canonical ICAO 9303 Part 4 specimens:
- Specimen passport: doc number ``L898902C3`` → check ``6``
- DOB ``740812`` → check ``2``
- Expiry ``120415`` → check ``9``
"""

from __future__ import annotations

import pytest

from hawiya.extractors.validators import (
    char_value,
    compute_check_digit,
    parse_check_digit,
    verify,
)


def test_char_value_digits() -> None:
    for i in range(10):
        assert char_value(str(i)) == i


def test_char_value_letters() -> None:
    assert char_value("A") == 10
    assert char_value("M") == 22
    assert char_value("Z") == 35


def test_char_value_filler_is_zero() -> None:
    assert char_value("<") == 0


@pytest.mark.parametrize("bad", ["", "AA", "a", "?", "/"])
def test_char_value_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        char_value(bad)


def test_compute_check_digit_doc_number_specimen() -> None:
    # ICAO 9303 Part 4 Appendix B: doc number L898902C3 → 6
    assert compute_check_digit("L898902C3") == 6


def test_compute_check_digit_dob_specimen() -> None:
    # ICAO 9303 Part 4 Appendix B: DOB 740812 → 2
    assert compute_check_digit("740812") == 2


def test_compute_check_digit_expiry_specimen() -> None:
    # ICAO 9303 Part 4 Appendix B: Expiry 120415 → 9
    assert compute_check_digit("120415") == 9


def test_compute_check_digit_with_fillers() -> None:
    # Personal data field of length 14, all fillers → check digit 0.
    assert compute_check_digit("<" * 14) == 0


def test_compute_check_digit_mixed_alphanumeric() -> None:
    # Hand-computed: "AB1<23" with weights 7,3,1,7,3,1
    # = 10*7 + 11*3 + 1*1 + 0*7 + 2*3 + 3*1 = 70+33+1+0+6+3 = 113 → 3
    assert compute_check_digit("AB1<23") == 3


def test_parse_check_digit_filler_is_zero() -> None:
    assert parse_check_digit("<") == 0


def test_parse_check_digit_digit() -> None:
    for i in range(10):
        assert parse_check_digit(str(i)) == i


@pytest.mark.parametrize("bad", ["A", "?", "", "X"])
def test_parse_check_digit_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_check_digit(bad)


def test_verify_positive() -> None:
    assert verify("L898902C3", "6") is True
    assert verify("740812", "2") is True
    assert verify("120415", "9") is True


def test_verify_negative() -> None:
    assert verify("L898902C3", "5") is False
    assert verify("740812", "0") is False
