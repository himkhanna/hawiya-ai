"""FastAPI dependency providers.

Tests swap collaborators via ``app.dependency_overrides[get_X] = fake``
without monkey-patching. A request shares one session across every
dependency that asks for it (FastAPI caches `Depends` resolutions per
request), so all repositories and services see the same transaction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.audit.writer import AuditWriter
from hawiya.db.repositories.person_identifier_repository import (
    PersonIdentifierRepository,
)
from hawiya.db.repositories.person_repository import PersonRepository
from hawiya.db.session import get_session
from hawiya.extractors.ocr import OCRAdapter, PassportEyeAdapter
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.services.extraction_service import ExtractionService
from hawiya.services.identity_service import IdentityService

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


async def get_person_repository(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[PersonRepository]:
    yield PersonRepository(session)


async def get_identifier_repository(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[PersonIdentifierRepository]:
    yield PersonIdentifierRepository(session)


async def get_matcher(
    identifier_repo: PersonIdentifierRepository = Depends(get_identifier_repository),
    person_repo: PersonRepository = Depends(get_person_repository),
) -> AsyncIterator[DeterministicMatcher]:
    yield DeterministicMatcher(identifier_repo=identifier_repo, person_repo=person_repo)


async def get_extraction_service(
    session: AsyncSession = Depends(get_session),
    ocr: OCRAdapter = Depends(get_ocr_adapter),
) -> AsyncIterator[ExtractionService]:
    audit = AuditWriter(session)
    yield ExtractionService(session=session, ocr=ocr, audit=audit)


async def get_identity_service(
    session: AsyncSession = Depends(get_session),
    extraction: ExtractionService = Depends(get_extraction_service),
    matcher: DeterministicMatcher = Depends(get_matcher),
    person_repo: PersonRepository = Depends(get_person_repository),
    identifier_repo: PersonIdentifierRepository = Depends(get_identifier_repository),
) -> AsyncIterator[IdentityService]:
    audit = AuditWriter(session)
    yield IdentityService(
        session=session,
        extraction_service=extraction,
        matcher=matcher,
        person_repo=person_repo,
        identifier_repo=identifier_repo,
        audit=audit,
    )
