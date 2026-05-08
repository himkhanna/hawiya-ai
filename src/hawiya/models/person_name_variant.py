"""PersonNameVariant — every form a name appears in across documents."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hawiya.models.base import Base, enum_column

if TYPE_CHECKING:
    from hawiya.models.person import Person


class NameScript(StrEnum):
    ARABIC = "arabic"
    LATIN = "latin"
    OTHER = "other"


class NameVariantType(StrEnum):
    CANONICAL = "canonical"
    TRANSLITERATION = "transliteration"
    ALIAS = "alias"
    MRZ = "mrz"


class PersonNameVariant(Base):
    __tablename__ = "person_name_variants"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    person_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.person_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    name_value: Mapped[str] = mapped_column(String(255), nullable=False)
    script: Mapped[NameScript] = mapped_column(
        enum_column(NameScript, name="name_script"),
        nullable=False,
    )
    variant_type: Mapped[NameVariantType] = mapped_column(
        enum_column(NameVariantType, name="name_variant_type"),
        nullable=False,
    )
    phonetic_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    person: Mapped[Person] = relationship("Person", back_populates="name_variants")
