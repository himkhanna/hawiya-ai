"""PII redaction helpers.

CLAUDE.md §2 forbids logging passport numbers, full names, DOB, nationality,
or photo bytes at INFO level. Run any structure that may carry those through
``redact_pii`` before logging.

Redaction is conservative: when in doubt, redact. Recall over precision.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Field names that should never appear in logs in cleartext.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "passport_number",
        "passport_no",
        "document_number",
        "doc_number",
        "mrz",
        "mrz_line_1",
        "mrz_line_2",
        "mrz_line_3",
        "emirates_id",
        "national_id",
        "gcc_id",
        "identifier_value",
        "name",
        "full_name",
        "given_names",
        "surname",
        "family_name",
        "canonical_name_ar",
        "canonical_name_en",
        "name_value",
        "date_of_birth",
        "dob",
        "birth_date",
        "nationality",
        "place_of_birth",
        "photo",
        "photo_bytes",
        "image",
        "image_bytes",
        "signature",
        "address",
        "phone",
        "phone_number",
        "email",
        "password",
        "authorization",
        "token",
        "secret",
        "api_key",
    }
)

REDACTED = "***REDACTED***"

# Patterns for PII that may appear in free-form strings.
_PASSPORT_RE = re.compile(r"\b[A-Z]{1,2}[0-9]{6,9}\b")
_MRZ_LINE_RE = re.compile(r"[A-Z0-9<]{30,}")
_DATE_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _is_sensitive_key(key: str) -> bool:
    return key.lower() in SENSITIVE_KEYS


def _redact_string(value: str) -> str:
    value = _MRZ_LINE_RE.sub(REDACTED, value)
    value = _PASSPORT_RE.sub(REDACTED, value)
    value = _EMAIL_RE.sub(REDACTED, value)
    return _DATE_RE.sub(REDACTED, value)


def redact_pii(value: Any) -> Any:
    """Return a deep-copied structure with PII fields and patterns redacted.

    Mappings: redacts any key in ``SENSITIVE_KEYS``, recurses into the rest.
    Lists/tuples: recurses into elements.
    Strings: pattern-redacts passport numbers, MRZ lines, emails, ISO dates.
    Everything else: returned as-is.
    """
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_sensitive_key(k):
                out[k] = REDACTED
            else:
                out[k] = redact_pii(v)
        return out
    if isinstance(value, list):
        return [redact_pii(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_pii(v) for v in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value
