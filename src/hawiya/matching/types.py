"""Shared types for matching results."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MatchAction(StrEnum):
    """Final action surfaced to the consumer (per CLAUDE.md §6 / §7).

    The matcher itself returns ``AUTO_MATCHED``, ``SUGGESTED_MATCH``, or
    ``NO_MATCH_NO_CREATE``; the orchestrator may upgrade the last to
    ``NEW_RECORD`` if the caller asked us to create on miss.
    """

    AUTO_MATCHED = "auto_matched"
    SUGGESTED_MATCH = "suggested_match"
    NEW_RECORD = "new_record"
    MANUAL_REVIEW = "manual_review"  # Phase 2 (probabilistic / LLM tiebreak)
    NO_MATCH_NO_CREATE = "no_match_no_create"


class MatchResult(BaseModel):
    """One matching call's outcome — what the matcher recommends."""

    action: MatchAction
    person_uuid: UUID | None = None
    confidence: float
    method: str  # short label of the rule that fired
    features: dict[str, Any] = Field(default_factory=dict)
