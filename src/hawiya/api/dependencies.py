"""FastAPI dependency providers.

The OCR adapter is exposed as a dependency so tests can swap a mock via
``app.dependency_overrides[get_ocr_adapter] = ...`` without monkey-patching.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.audit.writer import AuditWriter
from hawiya.db.session import get_session
from hawiya.extractors.ocr import OCRAdapter, PassportEyeAdapter
from hawiya.services.extraction_service import ExtractionService

_ocr_singleton: OCRAdapter | None = None


def get_ocr_adapter() -> OCRAdapter:
    """Lazy singleton; tests override via ``dependency_overrides``."""
    global _ocr_singleton  # noqa: PLW0603 — process-wide adapter singleton
    if _ocr_singleton is None:
        _ocr_singleton = PassportEyeAdapter()
    return _ocr_singleton


async def get_audit_writer(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AuditWriter]:
    yield AuditWriter(session)


async def get_extraction_service(
    session: AsyncSession = Depends(get_session),
    ocr: OCRAdapter = Depends(get_ocr_adapter),
) -> AsyncIterator[ExtractionService]:
    audit = AuditWriter(session)
    yield ExtractionService(session=session, ocr=ocr, audit=audit)
