"""ICAO 9303 check-digit primitives.

Reference: ICAO Doc 9303, Part 4 (TD3, e-passports).

The check-digit algorithm is shared across all five passport checksums:

    1. Each character contributes a numeric value:
         digits '0'..'9' → 0..9
         letters 'A'..'Z' → 10..35
         filler '<'      → 0
    2. Multiply by repeating weight pattern 7, 3, 1.
    3. Sum the products, take mod 10. That is the check digit.

A check digit position itself can be a digit ('0'..'9') OR '<' meaning
"no value provided"; per ICAO, a '<' check digit is treated as 0 when
recomputing the composite checksum.
"""

from __future__ import annotations

from collections.abc import Iterable

WEIGHTS: tuple[int, ...] = (7, 3, 1)
FILLER = "<"

# TD3 (passport) field positions and lengths within the 2 x 44-char MRZ.
# 0-indexed slices into the 88-char concatenated MRZ.
TD3_DOC_NUMBER = slice(44, 53)  # line 2, cols 1-9
TD3_DOC_NUMBER_CHECK = 53  # line 2, col 10
TD3_DOB = slice(57, 63)  # line 2, cols 14-19
TD3_DOB_CHECK = 63  # line 2, col 20
TD3_EXPIRY = slice(65, 71)  # line 2, cols 22-27
TD3_EXPIRY_CHECK = 71  # line 2, col 28
TD3_PERSONAL = slice(72, 86)  # line 2, cols 29-42
TD3_PERSONAL_CHECK = 86  # line 2, col 43
TD3_COMPOSITE_CHECK = 87  # line 2, col 44


def char_value(ch: str) -> int:
    """Return the ICAO 9303 numeric value of a single character.

    Raises ValueError on anything outside [0-9A-Z<].
    """
    if len(ch) != 1:
        raise ValueError(f"char_value expects 1 character, got {len(ch)!r}")
    if ch == FILLER:
        return 0
    if "0" <= ch <= "9":
        return ord(ch) - ord("0")
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    raise ValueError(f"invalid MRZ character: {ch!r}")


def compute_check_digit(field: str) -> int:
    """Apply the ICAO 9303 weighted-sum check-digit to ``field``.

    ``field`` is a string of MRZ characters (no length restriction; weights
    cycle). Returns the resulting digit 0-9.
    """
    total = 0
    for i, ch in enumerate(field):
        total += char_value(ch) * WEIGHTS[i % len(WEIGHTS)]
    return total % 10


def parse_check_digit(ch: str) -> int:
    """Parse a check-digit position. '<' is treated as 0 per ICAO 9303."""
    if ch == FILLER:
        return 0
    if "0" <= ch <= "9":
        return int(ch)
    raise ValueError(f"check digit must be 0-9 or '<', got {ch!r}")


def verify(field: str, check_digit_char: str) -> bool:
    """True if the check digit on ``field`` matches the provided digit."""
    return compute_check_digit(field) == parse_check_digit(check_digit_char)


def composite_input(parts: Iterable[str]) -> str:
    """Concatenate the fields that feed the TD3 composite check digit.

    Per ICAO 9303 Part 4: document number + its check + DOB + its check +
    expiry + its check + personal data + its check.
    """
    return "".join(parts)
