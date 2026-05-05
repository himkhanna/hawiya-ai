"""Tenant-scoped Person aggregate access."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.extractors.types import Sex
from hawiya.matching.arabic_names import (
    is_arabic_script,
    phonetic_key,
    to_canonical,
)
from hawiya.models import (
    NameScript,
    NameVariantType,
    Person,
    PersonNameVariant,
    PersonStatus,
)

# pg_trgm similarity below this is treated as "not a candidate".
SIMILARITY_THRESHOLD = 0.3


class PersonRepository:
    """Read/write access to ``persons`` and ``person_name_variants``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: UUID, person_uuid: UUID) -> Person | None:
        stmt = select(Person).where(
            Person.tenant_id == tenant_id,
            Person.person_uuid == person_uuid,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        tenant_id: UUID,
        *,
        canonical_name_ar: str | None = None,
        canonical_name_en: str | None = None,
        date_of_birth: date | None = None,
        nationality: str | None = None,
        sex: Sex | None = None,
        name_variants: list[dict[str, Any]] | None = None,
    ) -> Person:
        """Create a Person plus any seed name variants (with phonetic keys)."""
        person = Person(
            tenant_id=tenant_id,
            canonical_name_ar=to_canonical(canonical_name_ar) if canonical_name_ar else None,
            canonical_name_en=canonical_name_en.strip() if canonical_name_en else None,
            date_of_birth=date_of_birth,
            nationality=nationality,
            sex=sex,
            status=PersonStatus.ACTIVE,
        )
        self.session.add(person)
        await self.session.flush()  # populate person.person_uuid for FK below

        if name_variants:
            for spec in name_variants:
                self._add_name_variant(tenant_id, person.person_uuid, **spec)

        return person

    def _add_name_variant(
        self,
        tenant_id: UUID,
        person_uuid: UUID,
        *,
        name_value: str,
        variant_type: NameVariantType = NameVariantType.CANONICAL,
        script: NameScript | None = None,
    ) -> PersonNameVariant:
        if script is None:
            script = NameScript.ARABIC if is_arabic_script(name_value) else NameScript.LATIN
        variant = PersonNameVariant(
            tenant_id=tenant_id,
            person_uuid=person_uuid,
            name_value=name_value.strip(),
            script=script,
            variant_type=variant_type,
            phonetic_key=phonetic_key(name_value) or None,
        )
        self.session.add(variant)
        return variant

    async def search_by_name(
        self,
        tenant_id: UUID,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Person]:
        """Trigram-based fuzzy name search (uses pg_trgm GIN index).

        Returns results ranked by similarity to either ``canonical_name_ar``
        or ``canonical_name_en``. Phase 1 callers should treat the results
        as candidates, not matches.
        """
        if not query or not query.strip():
            return []
        q = query.strip()
        # `similarity()` is from pg_trgm; falls back to plain ILIKE if the
        # extension isn't available (shouldn't happen in our migrations).
        stmt = (
            select(Person)
            .where(
                Person.tenant_id == tenant_id,
                Person.status == PersonStatus.ACTIVE,
                func.coalesce(
                    func.similarity(Person.canonical_name_ar, q),
                    func.similarity(Person.canonical_name_en, q),
                    0.0,
                )
                > SIMILARITY_THRESHOLD,
            )
            .order_by(
                func.greatest(
                    func.coalesce(func.similarity(Person.canonical_name_ar, q), 0.0),
                    func.coalesce(func.similarity(Person.canonical_name_en, q), 0.0),
                ).desc()
            )
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())
