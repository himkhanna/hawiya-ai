"""ExtractionService unit tests with mocked OCR and a fake session."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from hawiya.audit.writer import AuditWriter
from hawiya.extractors.document_classifier import UnsupportedDocumentError
from hawiya.extractors.ocr import NoMRZFoundError
from hawiya.extractors.types import ChecksumStatus, DocumentType, ProcessingPath
from hawiya.models import AuditLog, DocumentExtraction
from hawiya.services.base import CrossTenantError
from hawiya.services.extraction_service import ExtractionService
from hawiya.tenancy.context import TenantContext

from .test_mrz import build_td3

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


class FakeSession:
    """Captures `add` calls. The service never flushes/commits in tests."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)


class StubOCR:
    def __init__(self, line1: str, line2: str) -> None:
        self._lines = (line1, line2)

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        return self._lines


class FailingOCR:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        raise self._exc


def _service(ocr: Any) -> tuple[ExtractionService, FakeSession]:
    session = FakeSession()
    audit = AuditWriter(session)  # type: ignore[arg-type]
    return ExtractionService(session=session, ocr=ocr, audit=audit), session  # type: ignore[arg-type]


async def test_extract_happy_path_creates_extraction_and_audit() -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3(doc_number="P1234567", surname="ALMANSOORI", given="MOHAMED")
    service, session = _service(StubOCR(line1, line2))

    with TenantContext(tenant):
        result = await service.extract(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    assert result.document_type is DocumentType.PASSPORT
    assert result.checksum_status is ChecksumStatus.ALL_PASS
    assert result.processing_path is ProcessingPath.MRZ_ONLY
    assert result.fields["document_number"] == "P1234567"
    assert result.fields["surname"] == "ALMANSOORI"
    assert result.fields["given_names"] == "MOHAMED"
    assert result.confidence_per_field["document_number"] == 0.99

    extractions = [a for a in session.added if isinstance(a, DocumentExtraction)]
    audits = [a for a in session.added if isinstance(a, AuditLog)]
    assert len(extractions) == 1
    assert len(audits) == 1
    assert extractions[0].tenant_id == tenant
    assert audits[0].tenant_id == tenant
    assert audits[0].endpoint == "/v1/documents/extract"


async def test_extract_failed_checksum_yields_partial_status() -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3()
    # Corrupt the document-number check digit.
    bad_line2 = line2[:9] + ("0" if line2[9] != "0" else "1") + line2[10:]
    service, _ = _service(StubOCR(line1, bad_line2))

    with TenantContext(tenant):
        result = await service.extract(tenant, JPEG_HEADER, "image/jpeg")
    assert result.checksum_status is ChecksumStatus.PARTIAL
    assert result.confidence_per_field["document_number"] == 0.50


async def test_extract_unsupported_document_raises_before_ocr() -> None:
    tenant = uuid.uuid4()
    service, session = _service(StubOCR("x" * 44, "y" * 44))

    with TenantContext(tenant), pytest.raises(UnsupportedDocumentError):
        await service.extract(tenant, b"not-an-image", "text/plain")
    # No DB writes when classification fails.
    assert session.added == []


async def test_extract_no_mrz_writes_failure_audit_then_raises() -> None:
    tenant = uuid.uuid4()
    service, session = _service(FailingOCR(NoMRZFoundError("no MRZ")))

    with TenantContext(tenant), pytest.raises(NoMRZFoundError):
        await service.extract(tenant, JPEG_HEADER + b"x" * 100, "image/jpeg")

    audits = [a for a in session.added if isinstance(a, AuditLog)]
    assert len(audits) == 1
    assert audits[0].decision == "failed"
    assert audits[0].output_summary["error"] == "NoMRZFoundError"


async def test_cross_tenant_call_raises() -> None:
    tenant_ctx = uuid.uuid4()
    tenant_arg = uuid.uuid4()
    line1, line2 = build_td3()
    service, _ = _service(StubOCR(line1, line2))

    with TenantContext(tenant_ctx), pytest.raises(CrossTenantError):
        await service.extract(tenant_arg, JPEG_HEADER, "image/jpeg")
