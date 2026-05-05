"""Person — the per-tenant Golden Record (CLAUDE.md §6)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hawiya.extractors.types import Sex
from hawiya.models.base import Base

if TYPE_CHECKING:
    from hawiya.models.person_identifier import PersonIdentifier
    from hawiya.models.person_name_variant import PersonNameVariant


class PersonStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


class Person(Base):
    __tablename__ = "persons"

    person_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    canonical_name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(3), nullable=True)
    sex: Mapped[Sex | None] = mapped_column(
        SAEnum(Sex, name="sex", native_enum=True),
        nullable=True,
    )
    status: Mapped[PersonStatus] = mapped_column(
        SAEnum(PersonStatus, name="person_status", native_enum=True),
        default=PersonStatus.ACTIVE,
        nullable=False,
    )
    merged_into: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    identifiers: Mapped[list[PersonIdentifier]] = relationship(
        "PersonIdentifier",
        back_populates="person",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    name_variants: Mapped[list[PersonNameVariant]] = relationship(
        "PersonNameVariant",
        back_populates="person",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
