"""PersonService — read/write/search the Person aggregate.

Wraps ``PersonRepository`` + ``PersonIdentifierRepository`` and adds the
duplicate-check guard required for ``POST /v1/persons``: before creating,
the deterministic matcher runs on whatever identifiers were supplied; a
hit raises ``PossibleDuplicateError`` (which the API turns into a 409).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.audit.writer import AuditWriter
from hawiya.db.repositories.person_identifier_repository import (
    PersonIdentifierRepository,
)
from hawiya.db.repositories.person_repository import PersonRepository
from hawiya.extractors.types import Sex
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.matching.types import MatchAction, MatchResult
from hawiya.models import IdentifierType, Person
from hawiya.services.base import ServiceBase, requires_tenant


class PossibleDuplicateError(RuntimeError):
    """Create rejected because the matcher found a likely existing record."""

    def __init__(self, match: MatchResult) -> None:
        super().__init__(
            f"Possible duplicate of person {match.person_uuid} "
            f"(method={match.method}, confidence={match.confidence})"
        )
        self.match = match


class PersonService(ServiceBase):
    def __init__(
        self,
        session: AsyncSession,
        person_repo: PersonRepository,
        identifier_repo: PersonIdentifierRepository,
        matcher: DeterministicMatcher,
        audit: AuditWriter,
    ) -> None:
        super().__init__(session)
        self.person_repo = person_repo
        self.identifier_repo = identifier_repo
        self.matcher = matcher
        self.audit = audit

    @requires_tenant
    async def get(self, tenant_id: UUID, person_uuid: UUID) -> Person | None:
        return await self.person_repo.get(tenant_id, person_uuid)

    @requires_tenant
    async def search(self, tenant_id: UUID, query: str, *, limit: int = 10) -> list[Person]:
        return await self.person_repo.search_by_name(tenant_id, query, limit=limit)

    @requires_tenant
    async def create(
        self,
        tenant_id: UUID,
        *,
        canonical_name_ar: str | None = None,
        canonical_name_en: str | None = None,
        date_of_birth: date | None = None,
        nationality: str | None = None,
        sex: Sex | None = None,
        passport_number: str | None = None,
        emirates_id: str | None = None,
        issuing_country: str | None = None,
        expiry_date: date | None = None,
    ) -> Person:
        # Duplicate guard: run the deterministic matcher before insertion.
        match_result = await self.matcher.match(
            tenant_id,
            emirates_id=emirates_id,
            passport_number=passport_number,
            nationality=nationality,
            date_of_birth=date_of_birth,
        )
        if match_result.action in (
            MatchAction.AUTO_MATCHED,
            MatchAction.SUGGESTED_MATCH,
        ):
            raise PossibleDuplicateError(match_result)

        person = await self.person_repo.create(
            tenant_id,
            canonical_name_ar=canonical_name_ar,
            canonical_name_en=canonical_name_en,
            date_of_birth=date_of_birth,
            nationality=nationality,
            sex=sex,
            name_variants=_seed_variants(canonical_name_ar, canonical_name_en),
        )

        if passport_number:
            await self.identifier_repo.create(
                tenant_id,
                person_uuid=person.person_uuid,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value=passport_number,
                issuing_country=issuing_country,
                expiry_date=expiry_date,
                is_primary=True,
                source="api_create",
            )
        if emirates_id:
            await self.identifier_repo.create(
                tenant_id,
                person_uuid=person.person_uuid,
                identifier_type=IdentifierType.EMIRATES_ID,
                identifier_value=emirates_id,
                source="api_create",
            )

        await self.audit.write(
            tenant_id=tenant_id,
            endpoint="/v1/persons",
            output_summary={"person_uuid": str(person.person_uuid), "action": "created"},
            decision="created",
        )

        # Newly-created Person has unloaded relationships. Refresh so the
        # response serializer can iterate `identifiers` / `name_variants`
        # without triggering a sync lazy-load (MissingGreenlet) inside the
        # async session.
        await self.session.flush()
        await self.session.refresh(person, ["identifiers", "name_variants"])
        return person


def _seed_variants(
    canonical_name_ar: str | None, canonical_name_en: str | None
) -> list[dict[str, Any]] | None:
    variants: list[dict[str, Any]] = []
    if canonical_name_ar:
        variants.append({"name_value": canonical_name_ar})
    if canonical_name_en:
        variants.append({"name_value": canonical_name_en})
    return variants or None
