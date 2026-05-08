"""Pydantic types shared across the extraction pipeline and the API layer."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    """Document classes Hawiya AI knows about. Phase 1: passport only."""

    PASSPORT = "passport"
    EMIRATES_ID = "emirates_id"
    GCC_ID = "gcc_id"
    RESIDENCE_PERMIT = "residence_permit"
    OTHER = "other"


class ChecksumStatus(StrEnum):
    """Aggregate result of the per-field MRZ checksums (per CLAUDE.md §6)."""

    ALL_PASS = "all_pass"  # noqa: S105 — enum value, not a credential  # nosec B105
    PARTIAL = "partial"
    ALL_FAIL = "all_fail"
    NOT_APPLICABLE = "n/a"


class ProcessingPath(StrEnum):
    """Which pipeline branch produced the result (per CLAUDE.md §6)."""

    MRZ_ONLY = "mrz_only"
    MRZ_PLUS_VISUAL = "mrz_plus_visual"
    VISUAL_ONLY = "visual_only"
    VISION_FALLBACK = "vision_fallback"


class Sex(StrEnum):
    MALE = "M"
    FEMALE = "F"
    UNSPECIFIED = "X"


class ChecksumReport(BaseModel):
    """Per-field ICAO 9303 checksum results."""

    doc_number: bool
    dob: bool
    expiry: bool
    personal: bool
    composite: bool

    @property
    def status(self) -> ChecksumStatus:
        results = [self.doc_number, self.dob, self.expiry, self.personal, self.composite]
        if all(results):
            return ChecksumStatus.ALL_PASS
        if not any(results):
            return ChecksumStatus.ALL_FAIL
        return ChecksumStatus.PARTIAL


class ParsedMRZ(BaseModel):
    """Structured fields parsed from a TD3 MRZ. Dates may be None if invalid."""

    document_type: str
    issuing_country: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    date_of_birth: date | None
    sex: Sex | None
    date_of_expiry: date | None
    personal_number: str
    checksums: ChecksumReport

    raw_line_1: str
    raw_line_2: str


class ExtractionResult(BaseModel):
    """The public-facing result of a document extraction call."""

    extraction_id: str
    document_type: DocumentType
    fields: dict[str, str | None] = Field(default_factory=dict)
    confidence_per_field: dict[str, float] = Field(default_factory=dict)
    checksum_status: ChecksumStatus
    processing_path: ProcessingPath
    processing_time_ms: int
