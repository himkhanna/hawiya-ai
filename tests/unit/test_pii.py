"""Unit tests for the PII redactor.

Recall over precision: false positives are acceptable, missing PII is not.
"""

from __future__ import annotations

import pytest

from hawiya.security.pii import REDACTED, redact_pii


def test_sensitive_keys_in_dict_are_replaced() -> None:
    payload = {
        "passport_number": "P1234567",
        "given_names": "Mohamed Ali",
        "surname": "Al-Mansoori",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "endpoint": "/v1/documents/extract",
    }
    out = redact_pii(payload)
    assert out["passport_number"] == REDACTED
    assert out["given_names"] == REDACTED
    assert out["surname"] == REDACTED
    # Non-sensitive keys are preserved
    assert out["tenant_id"] == payload["tenant_id"]
    assert out["endpoint"] == payload["endpoint"]


def test_nested_structures_are_recursed() -> None:
    payload = {
        "extraction": {
            "fields": {"date_of_birth": "1990-01-01", "nationality": "ARE"},
            "confidence_per_field": {"date_of_birth": 0.99},
        },
        "candidates": [
            {"passport_number": "X9876543", "score": 0.91},
            {"passport_number": "Y1112223", "score": 0.42},
        ],
    }
    out = redact_pii(payload)
    assert out["extraction"]["fields"]["date_of_birth"] == REDACTED
    assert out["extraction"]["fields"]["nationality"] == REDACTED
    # Confidence sub-dict happens to use a sensitive key as label — that's
    # the conservative (recall-over-precision) trade-off we accept.
    assert out["extraction"]["confidence_per_field"]["date_of_birth"] == REDACTED
    assert out["candidates"][0]["passport_number"] == REDACTED
    assert out["candidates"][0]["score"] == 0.91


def test_passport_number_pattern_in_free_text() -> None:
    msg = "extraction failed for document P1234567 from queue"
    assert REDACTED in redact_pii(msg)
    assert "P1234567" not in redact_pii(msg)


def test_mrz_line_pattern_in_free_text() -> None:
    mrz = "P<UAEMOHAMMED<<ALI<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    out = redact_pii(mrz)
    assert REDACTED in out
    assert "MOHAMMED" not in out


def test_iso_date_pattern_in_free_text() -> None:
    msg = "candidate dob 1990-05-12 matched"
    out = redact_pii(msg)
    assert "1990-05-12" not in out


def test_email_pattern_in_free_text() -> None:
    msg = "officer notified at officer@example.gov.ae"
    out = redact_pii(msg)
    assert "officer@example.gov.ae" not in out


def test_non_string_scalars_pass_through() -> None:
    assert redact_pii(42) == 42
    assert redact_pii(0.99) == 0.99
    assert redact_pii(True) is True
    assert redact_pii(None) is None


def test_lists_and_tuples() -> None:
    assert redact_pii([1, "P1234567", 3]) == [1, REDACTED, 3]
    assert redact_pii(("a", "1990-01-01")) == ("a", REDACTED)


@pytest.mark.parametrize(
    "key",
    ["passport_number", "Passport_Number", "PASSPORT_NUMBER", "mrz", "emirates_id"],
)
def test_key_match_is_case_insensitive(key: str) -> None:
    out = redact_pii({key: "anything"})
    assert out[key] == REDACTED
