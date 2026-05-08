"""SQLAlchemy declarative base + shared column helpers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base for all Hawiya AI models."""


def enum_column(enum_cls: type[Enum], *, name: str, **kwargs: Any) -> SAEnum:
    """Postgres ENUM column that serialises the enum *value* (not the name).

    SQLAlchemy's default for ``Enum(MyEnum)`` sends ``MyEnum.ACTIVE.name``
    on insert (``"ACTIVE"``), but our migrations create the Postgres ENUM
    type with lowercase values (``"active"``). Using ``values_callable``
    keeps the wire format aligned with the type definition.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [e.value for e in cls],
        **kwargs,
    )
