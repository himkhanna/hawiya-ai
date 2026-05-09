"""IdentityService tests with stub repos and a fake session.

Mirrors the orchestration logic without needing Postgres or Tesseract:
the matcher gets in-memory repos, the ExtractionService gets a stub OCR
that returns hand-crafted MRZ.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date
from typing import Any

import pytest

from hawiya.audit.writer import AuditWriter
from hawiya.extractors.types import Sex
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.matching.types import MatchAction
from hawiya.models import (
    AuditLog,
    DocumentExtraction,
    IdentifierType,
    MatchDecision,
    Person,
    PersonIdentifier,
)
from hawiya.services.extraction_service import ExtractionService
from hawiya.services.identity_service import IdentityService
from hawiya.tenancy.context import TenantContext

from .test_mrz import build_td3

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.executed: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any, attribute_names: list[str] | None = None) -> None:
        # Stand-in for AsyncSession.refresh — the real one populates
        # relationships from the DB. Our tests use stub repos that don't
        # have backing rows; we initialise the requested attrs to empty
        # lists so the response serializer can iterate them.
        for attr in attribute_names or ():
            if not hasattr(obj, attr) or getattr(obj, attr, None) is None:
                setattr(obj, attr, [])

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        # IdentityService issues an UPDATE on document_extractions; we don't
        # need to apply it for service-level assertions.
        self.executed.append(stmt)

        class _Empty:
            def scalar_one_or_none(self) -> None:
                return None

            def scalars(self) -> Any:
                class _S:
                    def all(self_inner) -> list[Any]:
                        return []

                return _S()

        return _Empty()


class StubOCR:
    def __init__(self, line1: str, line2: str) -> None:
        self._lines = (line1, line2)

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        return self._lines


@dataclass
class StubPersonRepo:
    persons: dict[uuid.UUID, Person] = field(default_factory=dict)
    created: list[Person] = field(default_factory=list)
    create_calls: list[dict[str, Any]] = field(default_factory=list)

    async def get(self, tenant_id: uuid.UUID, person_uuid: uuid.UUID) -> Person | None:
        p = self.persons.get(person_uuid)
        return p if p and p.tenant_id == tenant_id else None

    async def create(
        self,
        tenant_id: uuid.UUID,
        *,
        canonical_name_ar: str | None = None,
        canonical_name_en: str | None = None,
        date_of_birth: date | None = None,
        nationality: str | None = None,
        sex: Sex | None = None,
        name_variants: list[dict[str, Any]] | None = None,
    ) -> Person:
        self.create_calls.append(
            {
                "canonical_name_ar": canonical_name_ar,
                "canonical_name_en": canonical_name_en,
                "name_variants": name_variants,
            }
        )
        from datetime import datetime

        from hawiya.models import PersonStatus

        p = Person(
            person_uuid=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_name_ar=canonical_name_ar,
            canonical_name_en=canonical_name_en,
            date_of_birth=date_of_birth,
            nationality=nationality,
            sex=sex,
            status=PersonStatus.ACTIVE,
        )
        # Server-side defaults (created_at/updated_at) aren't populated for
        # in-memory objects; set them so response serialisers don't crash.
        now = datetime.now(tz=UTC)
        p.created_at = now
        p.updated_at = now
        self.persons[p.person_uuid] = p
        self.created.append(p)
        return p


@dataclass
class StubIdentifierRepo:
    rows: list[PersonIdentifier] = field(default_factory=list)
    created: list[PersonIdentifier] = field(default_factory=list)

    async def find_active(
        self,
        tenant_id: uuid.UUID,
        identifier_type: IdentifierType,
        identifier_value: str,
    ) -> PersonIdentifier | None:
        for r in self.rows:
            if (
                r.tenant_id == tenant_id
                and r.identifier_type is identifier_type
                and r.identifier_value == identifier_value
            ):
                return r
        return None

    async def create(
        self,
        tenant_id: uuid.UUID,
        *,
        person_uuid: uuid.UUID,
        identifier_type: IdentifierType,
        identifier_value: str,
        **kwargs: Any,
    ) -> PersonIdentifier:
        p = PersonIdentifier(
            identifier_id=uuid.uuid4(),
            tenant_id=tenant_id,
            person_uuid=person_uuid,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            **kwargs,
        )
        self.rows.append(p)
        self.created.append(p)
        return p


def _build_service(
    line1: str,
    line2: str,
    persons: dict[uuid.UUID, Person] | None = None,
    identifiers: list[PersonIdentifier] | None = None,
) -> tuple[IdentityService, FakeSession, StubPersonRepo, StubIdentifierRepo]:
    session = FakeSession()
    person_repo = StubPersonRepo(persons=persons or {})
    identifier_repo = StubIdentifierRepo(rows=identifiers or [])
    matcher = DeterministicMatcher(
        identifier_repo=identifier_repo,  # type: ignore[arg-type]
        person_repo=person_repo,  # type: ignore[arg-type]
    )
    audit = AuditWriter(session)  # type: ignore[arg-type]
    extraction = ExtractionService(
        session=session,  # type: ignore[arg-type]
        ocr=StubOCR(line1, line2),  # type: ignore[arg-type]
        audit=audit,
    )
    service = IdentityService(
        session=session,  # type: ignore[arg-type]
        extraction_service=extraction,
        matcher=matcher,
        person_repo=person_repo,  # type: ignore[arg-type]
        identifier_repo=identifier_repo,  # type: ignore[arg-type]
        audit=audit,
    )
    return service, session, person_repo, identifier_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_resolve_no_match_creates_new_person_and_identifier() -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3(doc_number="P1234567", surname="ALMANSOORI", given="MOHAMED")
    service, session, person_repo, identifier_repo = _build_service(line1, line2)

    with TenantContext(tenant):
        result = await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    assert result.action is MatchAction.NEW_RECORD
    assert result.person_uuid is not None
    assert result.confidence == 1.0
    assert len(person_repo.created) == 1
    assert len(identifier_repo.created) == 1
    new_person = person_repo.created[0]
    assert new_person.canonical_name_en == "MOHAMED ALMANSOORI"
    assert new_person.nationality == "ARE"
    assert new_person.date_of_birth == date(1990, 1, 12)
    new_ident = identifier_repo.created[0]
    assert new_ident.identifier_type is IdentifierType.PASSPORT
    assert new_ident.identifier_value == "P1234567"
    assert new_ident.is_primary is True

    # MatchDecision audit row written, extraction + audit linked.
    decisions = [a for a in session.added if isinstance(a, MatchDecision)]
    assert len(decisions) == 1
    assert decisions[0].decision.value == "no_match"
    audits = [a for a in session.added if isinstance(a, AuditLog)]
    # Two audit rows: one from extraction service, one from identity service.
    endpoints = [a.endpoint for a in audits]
    assert "/v1/documents/extract" in endpoints
    assert "/v1/identity/resolve" in endpoints


async def test_resolve_no_match_no_create_returns_no_match() -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3()
    service, _, person_repo, identifier_repo = _build_service(line1, line2)

    with TenantContext(tenant):
        result = await service.resolve(
            tenant, JPEG_HEADER + b"x" * 200, "image/jpeg", create_if_missing=False
        )

    assert result.action is MatchAction.NO_MATCH_NO_CREATE
    assert result.person_uuid is None
    assert person_repo.created == []
    assert identifier_repo.created == []


async def test_resolve_existing_passport_full_match_returns_auto_matched() -> None:
    tenant = uuid.uuid4()
    existing_person_uuid = uuid.uuid4()
    existing_person = Person(
        person_uuid=existing_person_uuid,
        tenant_id=tenant,
        nationality="ARE",
        date_of_birth=date(1990, 1, 12),
    )
    existing_identifier = PersonIdentifier(
        identifier_id=uuid.uuid4(),
        tenant_id=tenant,
        person_uuid=existing_person_uuid,
        identifier_type=IdentifierType.PASSPORT,
        identifier_value="P1234567",
    )
    line1, line2 = build_td3(doc_number="P1234567")
    service, _, person_repo, identifier_repo = _build_service(
        line1,
        line2,
        persons={existing_person_uuid: existing_person},
        identifiers=[existing_identifier],
    )

    with TenantContext(tenant):
        result = await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    assert result.action is MatchAction.AUTO_MATCHED
    assert result.person_uuid == existing_person_uuid
    assert result.confidence == 0.99
    # Critically: no new person/identifier created on a match.
    assert person_repo.created == []
    assert identifier_repo.created == []


async def test_resolve_passport_match_with_dob_mismatch_yields_suggested() -> None:
    tenant = uuid.uuid4()
    existing_uuid = uuid.uuid4()
    existing = Person(
        person_uuid=existing_uuid,
        tenant_id=tenant,
        nationality="USA",  # different
        date_of_birth=date(1985, 5, 5),  # different
    )
    line1, line2 = build_td3(doc_number="P1234567")  # ARE / 1990-01-12
    service, _, _, _ = _build_service(
        line1,
        line2,
        persons={existing_uuid: existing},
        identifiers=[
            PersonIdentifier(
                identifier_id=uuid.uuid4(),
                tenant_id=tenant,
                person_uuid=existing_uuid,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value="P1234567",
            )
        ],
    )

    with TenantContext(tenant):
        result = await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    assert result.action is MatchAction.SUGGESTED_MATCH
    assert result.person_uuid == existing_uuid
    assert result.confidence == 0.90


async def test_resolve_writes_match_decision_with_features() -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3()
    service, session, _, _ = _build_service(line1, line2)

    with TenantContext(tenant):
        await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    decisions = [a for a in session.added if isinstance(a, MatchDecision)]
    assert len(decisions) == 1
    assert decisions[0].match_type.value == "deterministic"
    assert decisions[0].features.get("had_passport_number") is True


async def test_idempotent_extraction_id_links_back_to_extraction() -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3()
    service, session, _, _ = _build_service(line1, line2)

    with TenantContext(tenant):
        result = await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    extractions = [a for a in session.added if isinstance(a, DocumentExtraction)]
    assert len(extractions) == 1
    assert extractions[0].extraction_id == uuid.UUID(result.extraction_id)
    # An UPDATE was issued to link the extraction to the new person_uuid.
    assert len(session.executed) >= 1


async def test_create_request_includes_name_variant_for_new_person() -> None:
    """The orchestrator asks the repo to seed a name variant for new persons."""
    tenant = uuid.uuid4()
    line1, line2 = build_td3(surname="ALMANSOORI", given="MOHAMED")
    service, _, person_repo, _ = _build_service(line1, line2)

    with TenantContext(tenant):
        await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")

    assert len(person_repo.create_calls) == 1
    call = person_repo.create_calls[0]
    assert call["canonical_name_en"] == "MOHAMED ALMANSOORI"
    assert call["name_variants"] == [{"name_value": "MOHAMED ALMANSOORI"}]


@pytest.mark.parametrize(
    ("line1_doc", "expected_action"),
    [
        ("P1234567", MatchAction.NEW_RECORD),  # nothing in DB → create
    ],
)
async def test_resolve_returns_extraction_id(line1_doc: str, expected_action: MatchAction) -> None:
    tenant = uuid.uuid4()
    line1, line2 = build_td3(doc_number=line1_doc)
    service, _, _, _ = _build_service(line1, line2)

    with TenantContext(tenant):
        result = await service.resolve(tenant, JPEG_HEADER + b"x" * 200, "image/jpeg")
    assert result.action is expected_action
    assert result.extraction_id  # non-empty
    assert result.fields["document_number"] == line1_doc
