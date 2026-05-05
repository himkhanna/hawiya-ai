"""Identity resolution: extract → match → return.

Calls ``ExtractionService`` for the OCR/parse, then ``DeterministicMatcher``
for matching. On a no-match the caller can request creation of a new
``Person`` (default behaviour). Every resolve call writes:

- one ``MatchDecision`` row (the matcher's recommendation, with features)
- one ``AuditLog`` row scoped to ``/v1/identity/resolve``
- updates the underlying ``DocumentExtraction.person_uuid`` + ``match_action``

Phase 1 is deterministic-only; the same plumbing carries probabilistic /
LLM tiebreak in Phase 2.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.audit.writer import AuditWriter
from hawiya.db.repositories.person_identifier_repository import (
    PersonIdentifierRepository,
)
from hawiya.db.repositories.person_repository import PersonRepository
from hawiya.extractors.types import Sex
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.matching.types import MatchAction
from hawiya.models import (
    DocumentExtraction,
    IdentifierType,
    MatchDecision,
    MatchDecisionValue,
    MatchType,
)
from hawiya.observability.logger import get_logger
from hawiya.services.base import ServiceBase, requires_tenant
from hawiya.services.extraction_service import ExtractionService

log = get_logger("hawiya.identity")

CONF_NEW_RECORD = 1.0


class ResolveResult(BaseModel):
    """Public-facing result of /v1/identity/resolve."""

    extraction_id: str
    action: MatchAction
    person_uuid: UUID | None = None
    confidence: float
    method: str
    fields: dict[str, str | None] = Field(default_factory=dict)


class IdentityService(ServiceBase):
    def __init__(
        self,
        session: AsyncSession,
        extraction_service: ExtractionService,
        matcher: DeterministicMatcher,
        person_repo: PersonRepository,
        identifier_repo: PersonIdentifierRepository,
        audit: AuditWriter,
    ) -> None:
        super().__init__(session)
        self.extraction = extraction_service
        self.matcher = matcher
        self.person_repo = person_repo
        self.identifier_repo = identifier_repo
        self.audit = audit

    @requires_tenant
    async def resolve(
        self,
        tenant_id: UUID,
        payload: bytes,
        content_type: str,
        *,
        consumer_request_id: str | None = None,
        create_if_missing: bool = True,
    ) -> ResolveResult:
        # 1. Extract fields from the image (also writes its own audit row).
        extraction = await self.extraction.extract(
            tenant_id, payload, content_type, consumer_request_id=consumer_request_id
        )
        fields = extraction.fields
        input_hash = hashlib.sha256(payload).hexdigest()

        # 2. Parse matchable values from extracted fields.
        passport_number = fields.get("document_number") or None
        nationality = fields.get("nationality") or None
        dob = _parse_iso_date(fields.get("date_of_birth"))

        # 3. Run the deterministic matcher.
        match_result = await self.matcher.match(
            tenant_id,
            passport_number=passport_number,
            nationality=nationality,
            date_of_birth=dob,
        )

        # 4. If no match and the caller wants it, create a new Person.
        person_uuid = match_result.person_uuid
        action = match_result.action
        confidence = match_result.confidence

        if action is MatchAction.NO_MATCH_NO_CREATE and create_if_missing:
            person_uuid = await self._create_person_from_extraction(
                tenant_id,
                fields=fields,
                dob=dob,
                nationality=nationality,
                passport_number=passport_number,
                doc_number_confidence=extraction.confidence_per_field.get("document_number"),
            )
            action = MatchAction.NEW_RECORD
            confidence = CONF_NEW_RECORD

        # 5. Link the extraction to the resolved (or newly created) person.
        await self._update_extraction_link(
            tenant_id,
            extraction_id=UUID(extraction.extraction_id),
            person_uuid=person_uuid,
            action=action,
        )

        # 6. Persist the MatchDecision (auditable record of the matcher call).
        decision_value = _action_to_decision(action)
        if decision_value is not None:
            self.session.add(
                MatchDecision(
                    tenant_id=tenant_id,
                    candidate_a=person_uuid,
                    candidate_b=None,
                    match_type=MatchType.DETERMINISTIC,
                    confidence=confidence,
                    features=match_result.features,
                    decision=decision_value,
                )
            )

        # 7. Audit log scoped to /v1/identity/resolve.
        await self.audit.write(
            tenant_id=tenant_id,
            endpoint="/v1/identity/resolve",
            input_hash=input_hash,
            output_summary={
                "extraction_id": extraction.extraction_id,
                "person_uuid": str(person_uuid) if person_uuid else None,
                "action": action.value,
            },
            model_versions={"matcher": "deterministic-v1"},
            confidence=confidence,
            processing_path=extraction.processing_path.value,
            decision=action.value,
        )

        log.info(
            "identity_resolved",
            extraction_id=extraction.extraction_id,
            action=action.value,
            confidence=confidence,
        )

        return ResolveResult(
            extraction_id=extraction.extraction_id,
            action=action,
            person_uuid=person_uuid,
            confidence=confidence,
            method=match_result.method,
            fields=fields,
        )

    async def _create_person_from_extraction(
        self,
        tenant_id: UUID,
        *,
        fields: dict[str, str | None],
        dob: date | None,
        nationality: str | None,
        passport_number: str | None,
        doc_number_confidence: float | None,
    ) -> UUID:
        surname = (fields.get("surname") or "").strip()
        given = (fields.get("given_names") or "").strip()
        canonical_en = " ".join(p for p in (given, surname) if p) or None

        person = await self.person_repo.create(
            tenant_id,
            canonical_name_en=canonical_en,
            date_of_birth=dob,
            nationality=nationality,
            sex=_parse_sex(fields.get("sex")),
            name_variants=([{"name_value": canonical_en}] if canonical_en else None),
        )

        if passport_number:
            expiry = _parse_iso_date(fields.get("date_of_expiry"))
            await self.identifier_repo.create(
                tenant_id,
                person_uuid=person.person_uuid,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value=passport_number,
                issuing_country=fields.get("issuing_country") or None,
                expiry_date=expiry,
                is_primary=True,
                source="extraction",
                confidence=doc_number_confidence,
            )

        return person.person_uuid

    async def _update_extraction_link(
        self,
        tenant_id: UUID,
        *,
        extraction_id: UUID,
        person_uuid: UUID | None,
        action: MatchAction,
    ) -> None:
        await self.session.execute(
            update(DocumentExtraction)
            .where(
                DocumentExtraction.extraction_id == extraction_id,
                DocumentExtraction.tenant_id == tenant_id,
            )
            .values(person_uuid=person_uuid, match_action=action.value)
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_sex(value: Any) -> Sex | None:
    if not value:
        return None
    try:
        return Sex(value)
    except ValueError:
        return None


_ACTION_TO_DECISION: dict[MatchAction, MatchDecisionValue | None] = {
    MatchAction.AUTO_MATCHED: MatchDecisionValue.AUTO_MERGE,
    MatchAction.SUGGESTED_MATCH: MatchDecisionValue.SUGGEST_MERGE,
    MatchAction.MANUAL_REVIEW: MatchDecisionValue.MANUAL_REVIEW,
    MatchAction.NO_MATCH_NO_CREATE: MatchDecisionValue.NO_MATCH,
    MatchAction.NEW_RECORD: MatchDecisionValue.NO_MATCH,
}


def _action_to_decision(action: MatchAction) -> MatchDecisionValue | None:
    return _ACTION_TO_DECISION.get(action)
