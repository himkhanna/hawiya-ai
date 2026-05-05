"""Tenant-scoped lookup over ``person_identifiers``."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.models import (
    IdentifierStatus,
    IdentifierType,
    PersonIdentifier,
)


class PersonIdentifierRepository:
    """Read/write access to ``person_identifiers``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_active(
        self,
        tenant_id: UUID,
        identifier_type: IdentifierType,
        identifier_value: str,
    ) -> PersonIdentifier | None:
        """Fetch the (single) active identifier for a tenant + type + value."""
        stmt = select(PersonIdentifier).where(
            PersonIdentifier.tenant_id == tenant_id,
            PersonIdentifier.identifier_type == identifier_type,
            PersonIdentifier.identifier_value == identifier_value,
            PersonIdentifier.status == IdentifierStatus.ACTIVE,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        tenant_id: UUID,
        *,
        person_uuid: UUID,
        identifier_type: IdentifierType,
        identifier_value: str,
        issuing_country: str | None = None,
        issue_date: date | None = None,
        expiry_date: date | None = None,
        is_primary: bool = False,
        source: str | None = None,
        confidence: float | None = None,
    ) -> PersonIdentifier:
        identifier = PersonIdentifier(
            tenant_id=tenant_id,
            person_uuid=person_uuid,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            issuing_country=issuing_country,
            issue_date=issue_date,
            expiry_date=expiry_date,
            is_primary=is_primary,
            source=source,
            confidence=confidence,
            status=IdentifierStatus.ACTIVE,
        )
        self.session.add(identifier)
        return identifier
