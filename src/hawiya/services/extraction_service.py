"""Document extraction orchestration.

Pipeline (CLAUDE.md §7):
    1. Classify the input bytes.
    2. OCR → MRZ text lines.
    3. Parse + validate (5 checksums).
    4. Build per-field confidence and ``ExtractionResult``.
    5. Persist a ``DocumentExtraction`` row and an ``AuditLog`` entry.

Phase 1 only walks the deterministic ``mrz_only`` path. The visual and
LLM branches are placeholders for Phase 2.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.audit.writer import AuditWriter
from hawiya.extractors.document_classifier import (
    classify,
)
from hawiya.extractors.mrz import MRZFormatError, parse_td3
from hawiya.extractors.ocr import (
    NoMRZFoundError,
    OCRAdapter,
    OCRUnavailableError,
)
from hawiya.extractors.types import (
    ExtractionResult,
    ParsedMRZ,
    ProcessingPath,
)
from hawiya.models import DocumentExtraction
from hawiya.observability.logger import get_logger
from hawiya.observability.metrics import (
    EXTRACTION_DURATION_SECONDS,
    EXTRACTION_FAILURES_TOTAL,
    EXTRACTIONS_TOTAL,
)
from hawiya.services.base import ServiceBase, requires_tenant

log = get_logger("hawiya.extraction")

CONFIDENCE_CHECKSUM_PASS = 0.99
CONFIDENCE_CHECKSUM_FAIL = 0.50
CONFIDENCE_NAME_DEFAULT = 0.85
CONFIDENCE_SEX_KNOWN = 0.95
CONFIDENCE_SEX_UNSPECIFIED = 0.50


class ExtractionService(ServiceBase):
    """Orchestrates the extract → match → audit pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        ocr: OCRAdapter,
        audit: AuditWriter,
    ) -> None:
        super().__init__(session)
        self.ocr = ocr
        self.audit = audit

    @requires_tenant
    async def extract(
        self,
        tenant_id: UUID,
        payload: bytes,
        content_type: str,
        consumer_request_id: str | None = None,
    ) -> ExtractionResult:
        start_ns = time.perf_counter_ns()
        input_hash = hashlib.sha256(payload).hexdigest()

        document_type = classify(payload, content_type)

        try:
            line1, line2 = await self.ocr.read_mrz(payload, content_type)
        except (NoMRZFoundError, OCRUnavailableError, MRZFormatError) as e:
            EXTRACTION_FAILURES_TOTAL.labels(
                tenant_id=str(tenant_id), reason=type(e).__name__
            ).inc()
            await self.audit.write(
                tenant_id=tenant_id,
                endpoint="/v1/documents/extract",
                input_hash=input_hash,
                processing_path=ProcessingPath.MRZ_ONLY.value,
                decision="failed",
                output_summary={"error": type(e).__name__, "message": str(e)},
            )
            raise

        parsed = parse_td3(line1, line2)

        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        extraction_id = uuid.uuid4()
        fields = _fields_from_parsed(parsed)
        confidences = _confidences_from_parsed(parsed)
        overall_confidence = sum(confidences.values()) / len(confidences)

        record = DocumentExtraction(
            extraction_id=extraction_id,
            tenant_id=tenant_id,
            consumer_request_id=consumer_request_id,
            input_hash=input_hash,
            document_type=document_type,
            extracted_data=fields,
            confidence_per_field=confidences,
            checksum_status=parsed.checksums.status,
            processing_path=ProcessingPath.MRZ_ONLY,
            processing_time_ms=int(elapsed_ms),
        )
        self.session.add(record)

        await self.audit.write(
            tenant_id=tenant_id,
            endpoint="/v1/documents/extract",
            input_hash=input_hash,
            output_summary={
                "extraction_id": str(extraction_id),
                "checksum_status": parsed.checksums.status.value,
            },
            model_versions={"mrz": "icao-9303-td3"},
            confidence=overall_confidence,
            processing_path=ProcessingPath.MRZ_ONLY.value,
            decision=parsed.checksums.status.value,
        )

        EXTRACTIONS_TOTAL.labels(
            tenant_id=str(tenant_id),
            checksum_status=parsed.checksums.status.value,
            processing_path=ProcessingPath.MRZ_ONLY.value,
        ).inc()
        EXTRACTION_DURATION_SECONDS.labels(tenant_id=str(tenant_id)).observe(elapsed_ms / 1000.0)

        log.info(
            "extraction_complete",
            extraction_id=str(extraction_id),
            checksum_status=parsed.checksums.status.value,
            processing_time_ms=elapsed_ms,
        )

        return ExtractionResult(
            extraction_id=str(extraction_id),
            document_type=document_type,
            fields=fields,
            confidence_per_field=confidences,
            checksum_status=parsed.checksums.status,
            processing_path=ProcessingPath.MRZ_ONLY,
            processing_time_ms=int(elapsed_ms),
        )


_MULTISPACE_RE = re.compile(r"\s{2,}")


def _strip_ocr_junk(name: str) -> str:
    """Drop tokens after 2+ consecutive whitespace.

    The MRZ name format uses single ``<`` to separate sub-tokens of a
    given name (``JEAN<PIERRE`` -> ``JEAN PIERRE``). Multiple ``<`` is
    filler. When OCR mis-reads filler chars it produces stray short
    tokens after a long whitespace run (``MOHAMED            KK``); a
    legitimate name never has 2+ consecutive spaces, so anything past
    that boundary is noise.
    """
    if not name:
        return name
    return _MULTISPACE_RE.split(name.strip())[0]


def _fields_from_parsed(p: ParsedMRZ) -> dict[str, str | None]:
    return {
        "document_type": p.document_type,
        "issuing_country": p.issuing_country,
        "surname": _strip_ocr_junk(p.surname),
        "given_names": _strip_ocr_junk(p.given_names),
        "document_number": p.document_number,
        "nationality": p.nationality,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "sex": p.sex.value if p.sex else None,
        "date_of_expiry": p.date_of_expiry.isoformat() if p.date_of_expiry else None,
        "personal_number": p.personal_number or None,
    }


def _confidences_from_parsed(p: ParsedMRZ) -> dict[str, float]:
    cs = p.checksums

    def from_checksum(passed: bool) -> float:
        return CONFIDENCE_CHECKSUM_PASS if passed else CONFIDENCE_CHECKSUM_FAIL

    return {
        "document_number": from_checksum(cs.doc_number),
        "date_of_birth": from_checksum(cs.dob),
        "date_of_expiry": from_checksum(cs.expiry),
        "personal_number": from_checksum(cs.personal),
        "surname": CONFIDENCE_NAME_DEFAULT,
        "given_names": CONFIDENCE_NAME_DEFAULT,
        "issuing_country": CONFIDENCE_NAME_DEFAULT,
        "nationality": CONFIDENCE_NAME_DEFAULT,
        "sex": (
            CONFIDENCE_SEX_KNOWN
            if p.sex and p.sex.value in ("M", "F")
            else CONFIDENCE_SEX_UNSPECIFIED
        ),
    }


# Re-export for callers that want the union without importing Pydantic types.
ExtractedFields = dict[str, Any]
