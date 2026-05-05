"""PersonIdentifier — passport, Emirates ID, GCC ID, prior passports."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hawiya.models.base import Base

if TYPE_CHECKING:
    from hawiya.models.person import Person


class IdentifierType(StrEnum):
    PASSPORT = "passport"
    EMIRATES_ID = "emirates_id"
    GCC_ID = "gcc_id"
    PRIOR_PASSPORT = "prior_passport"


class IdentifierStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PersonIdentifier(Base):
    __tablename__ = "person_identifiers"

    identifier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    person_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.person_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    identifier_type: Mapped[IdentifierType] = mapped_column(
        SAEnum(IdentifierType, name="identifier_type", native_enum=True),
        nullable=False,
    )
    identifier_value: Mapped[str] = mapped_column(String(64), nullable=False)
    issuing_country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[IdentifierStatus] = mapped_column(
        SAEnum(IdentifierStatus, name="identifier_status", native_enum=True),
        default=IdentifierStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    person: Mapped[Person] = relationship("Person", back_populates="identifiers")
