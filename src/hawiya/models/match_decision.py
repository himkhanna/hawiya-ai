"""MatchDecision — auditable record of every matching call (CLAUDE.md §6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hawiya.models.base import Base


class MatchType(StrEnum):
    DETERMINISTIC = "deterministic"
    PROBABILISTIC = "probabilistic"
    LLM_ASSISTED = "llm_assisted"


class MatchDecisionValue(StrEnum):
    AUTO_MERGE = "auto_merge"
    SUGGEST_MERGE = "suggest_merge"
    NO_MATCH = "no_match"
    MANUAL_REVIEW = "manual_review"


class ReviewOutcome(StrEnum):
    CONFIRMED_MATCH = "confirmed_match"
    REJECTED_MATCH = "rejected_match"
    ESCALATED = "escalated"


class MatchDecision(Base):
    __tablename__ = "match_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    candidate_a: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    candidate_b: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    match_type: Mapped[MatchType] = mapped_column(
        SAEnum(MatchType, name="match_type", native_enum=True),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    decision: Mapped[MatchDecisionValue] = mapped_column(
        SAEnum(MatchDecisionValue, name="match_decision_value", native_enum=True),
        nullable=False,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_outcome: Mapped[ReviewOutcome | None] = mapped_column(
        SAEnum(ReviewOutcome, name="review_outcome", native_enum=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
