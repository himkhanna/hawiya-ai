"""``/v1/persons`` — Person CRUD + search.

- ``GET /v1/persons/{uuid}`` — full record (or 404)
- ``POST /v1/persons`` — create with duplicate guard (409 on possible duplicate)
- ``POST /v1/persons/search`` — fuzzy name search (Phase 1: pg_trgm only)
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.api.dependencies import (
    get_audit_writer,
    get_identifier_repository,
    get_matcher,
    get_person_repository,
)
from hawiya.api.errors import error_response
from hawiya.audit.writer import AuditWriter
from hawiya.db.repositories.person_identifier_repository import (
    PersonIdentifierRepository,
)
from hawiya.db.repositories.person_repository import PersonRepository
from hawiya.db.session import get_session
from hawiya.extractors.types import Sex
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.models import Person
from hawiya.services.person_service import PersonService, PossibleDuplicateError
from hawiya.tenancy.context import require_tenant_id

router = APIRouter(prefix="/v1/persons", tags=["persons"])

SEARCH_DEFAULT_LIMIT = 10
SEARCH_MAX_LIMIT = 50
PERSON_SUMMARY_NAME_LIMIT = 255


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PersonCreateRequest(BaseModel):
    canonical_name_ar: str | None = Field(default=None, max_length=PERSON_SUMMARY_NAME_LIMIT)
    canonical_name_en: str | None = Field(default=None, max_length=PERSON_SUMMARY_NAME_LIMIT)
    date_of_birth: date | None = None
    nationality: str | None = Field(default=None, min_length=3, max_length=3)
    sex: Sex | None = None
    passport_number: str | None = Field(default=None, max_length=64)
    emirates_id: str | None = Field(default=None, max_length=64)
    issuing_country: str | None = Field(default=None, min_length=3, max_length=3)
    expiry_date: date | None = None


class IdentifierResponse(BaseModel):
    identifier_type: str
    identifier_value: str
    issuing_country: str | None
    expiry_date: str | None
    is_primary: bool


class NameVariantResponse(BaseModel):
    name_value: str
    script: str
    variant_type: str


class PersonResponse(BaseModel):
    person_uuid: str
    canonical_name_ar: str | None
    canonical_name_en: str | None
    date_of_birth: str | None
    nationality: str | None
    sex: str | None
    status: str
    identifiers: list[IdentifierResponse] = Field(default_factory=list)
    name_variants: list[NameVariantResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


class PersonSummary(BaseModel):
    person_uuid: str
    canonical_name_ar: str | None
    canonical_name_en: str | None
    date_of_birth: str | None
    nationality: str | None


class PersonSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=255)
    limit: int = Field(default=SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT)


class PersonSearchResponse(BaseModel):
    candidates: list[PersonSummary]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(person: Person) -> PersonResponse:
    return PersonResponse(
        person_uuid=str(person.person_uuid),
        canonical_name_ar=person.canonical_name_ar,
        canonical_name_en=person.canonical_name_en,
        date_of_birth=person.date_of_birth.isoformat() if person.date_of_birth else None,
        nationality=person.nationality,
        sex=person.sex.value if person.sex else None,
        status=person.status.value,
        identifiers=[
            IdentifierResponse(
                identifier_type=i.identifier_type.value,
                identifier_value=i.identifier_value,
                issuing_country=i.issuing_country,
                expiry_date=i.expiry_date.isoformat() if i.expiry_date else None,
                is_primary=i.is_primary,
            )
            for i in person.identifiers
        ],
        name_variants=[
            NameVariantResponse(
                name_value=v.name_value,
                script=v.script.value,
                variant_type=v.variant_type.value,
            )
            for v in person.name_variants
        ],
        created_at=person.created_at.isoformat() if person.created_at else "",
        updated_at=person.updated_at.isoformat() if person.updated_at else "",
    )


def _to_summary(person: Person) -> PersonSummary:
    return PersonSummary(
        person_uuid=str(person.person_uuid),
        canonical_name_ar=person.canonical_name_ar,
        canonical_name_en=person.canonical_name_en,
        date_of_birth=person.date_of_birth.isoformat() if person.date_of_birth else None,
        nationality=person.nationality,
    )


def _build_service(
    session: AsyncSession,
    person_repo: PersonRepository,
    identifier_repo: PersonIdentifierRepository,
    matcher: DeterministicMatcher,
    audit: AuditWriter,
) -> PersonService:
    return PersonService(
        session=session,
        person_repo=person_repo,
        identifier_repo=identifier_repo,
        matcher=matcher,
        audit=audit,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{person_uuid}",
    response_model=PersonResponse,
    responses={404: {"description": "Person not found in this tenant"}},
)
async def get_person(
    person_uuid: UUID,
    session: AsyncSession = Depends(get_session),
    person_repo: PersonRepository = Depends(get_person_repository),
    identifier_repo: PersonIdentifierRepository = Depends(get_identifier_repository),
    matcher: DeterministicMatcher = Depends(get_matcher),
    audit: AuditWriter = Depends(get_audit_writer),
) -> PersonResponse | JSONResponse:
    tenant_id = require_tenant_id()
    service = _build_service(session, person_repo, identifier_repo, matcher, audit)
    person = await service.get(tenant_id, person_uuid)
    if person is None:
        return error_response(
            code="NOT_FOUND",
            message=f"Person {person_uuid} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _to_response(person)


@router.post(
    "",
    response_model=PersonResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Possible duplicate of an existing Person"}},
)
async def create_person(
    body: PersonCreateRequest,
    session: AsyncSession = Depends(get_session),
    person_repo: PersonRepository = Depends(get_person_repository),
    identifier_repo: PersonIdentifierRepository = Depends(get_identifier_repository),
    matcher: DeterministicMatcher = Depends(get_matcher),
    audit: AuditWriter = Depends(get_audit_writer),
) -> PersonResponse | JSONResponse:
    tenant_id = require_tenant_id()
    service = _build_service(session, person_repo, identifier_repo, matcher, audit)
    try:
        person = await service.create(tenant_id, **body.model_dump(exclude_none=True))
    except PossibleDuplicateError as e:
        return error_response(
            code="POSSIBLE_DUPLICATE",
            message=str(e),
            status_code=status.HTTP_409_CONFLICT,
            details={
                "candidate_person_uuid": str(e.match.person_uuid),
                "method": e.match.method,
                "confidence": e.match.confidence,
            },
        )
    return _to_response(person)


@router.post("/search", response_model=PersonSearchResponse)
async def search_persons(
    body: PersonSearchRequest,
    session: AsyncSession = Depends(get_session),
    person_repo: PersonRepository = Depends(get_person_repository),
    identifier_repo: PersonIdentifierRepository = Depends(get_identifier_repository),
    matcher: DeterministicMatcher = Depends(get_matcher),
    audit: AuditWriter = Depends(get_audit_writer),
) -> PersonSearchResponse:
    tenant_id = require_tenant_id()
    service = _build_service(session, person_repo, identifier_repo, matcher, audit)
    candidates = await service.search(tenant_id, body.query, limit=body.limit)
    return PersonSearchResponse(candidates=[_to_summary(p) for p in candidates])
