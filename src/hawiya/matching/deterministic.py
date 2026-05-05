"""Deterministic identity matching (CLAUDE.md §7 steps 1-3).

Phase 1 walks only deterministic rules:

    1. Emirates ID exact          → AUTO_MATCHED  (confidence 1.00)
    2. Passport + nationality + DOB exact → AUTO_MATCHED  (0.99)
    3. Passport number exact alone → SUGGESTED_MATCH (0.90)

Probabilistic name matching (steps 4-7) is Phase 2.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from hawiya.db.repositories.person_identifier_repository import (
    PersonIdentifierRepository,
)
from hawiya.db.repositories.person_repository import PersonRepository
from hawiya.matching.types import MatchAction, MatchResult
from hawiya.models import IdentifierType

CONF_EMIRATES_ID_EXACT = 1.00
CONF_PASSPORT_FULL = 0.99
CONF_PASSPORT_NUMBER_ONLY = 0.90


class DeterministicMatcher:
    """Phase 1 matcher. Order: Emirates ID → passport+demographics → passport-only."""

    def __init__(
        self,
        identifier_repo: PersonIdentifierRepository,
        person_repo: PersonRepository,
    ) -> None:
        self.identifier_repo = identifier_repo
        self.person_repo = person_repo

    async def match(
        self,
        tenant_id: UUID,
        *,
        emirates_id: str | None = None,
        passport_number: str | None = None,
        nationality: str | None = None,
        date_of_birth: date | None = None,
    ) -> MatchResult:
        # ---- Step 1: Emirates ID exact ------------------------------------
        if emirates_id:
            ident = await self.identifier_repo.find_active(
                tenant_id, IdentifierType.EMIRATES_ID, emirates_id
            )
            if ident is not None:
                return MatchResult(
                    action=MatchAction.AUTO_MATCHED,
                    person_uuid=ident.person_uuid,
                    confidence=CONF_EMIRATES_ID_EXACT,
                    method="emirates_id_exact",
                    features={"identifier_type": "emirates_id"},
                )

        # ---- Steps 2 & 3: Passport ----------------------------------------
        if passport_number:
            ident = await self.identifier_repo.find_active(
                tenant_id, IdentifierType.PASSPORT, passport_number
            )
            if ident is not None:
                person = await self.person_repo.get(tenant_id, ident.person_uuid)
                nationality_match = bool(
                    person
                    and nationality
                    and person.nationality
                    and person.nationality == nationality
                )
                dob_match = bool(
                    person
                    and date_of_birth
                    and person.date_of_birth
                    and person.date_of_birth == date_of_birth
                )
                # Step 2: full match (passport + nationality + DOB)
                if nationality_match and dob_match:
                    return MatchResult(
                        action=MatchAction.AUTO_MATCHED,
                        person_uuid=ident.person_uuid,
                        confidence=CONF_PASSPORT_FULL,
                        method="passport_plus_demographics",
                        features={
                            "identifier_type": "passport",
                            "nationality_match": True,
                            "dob_match": True,
                        },
                    )
                # Step 3: passport-only — confidence drops, caller reviews
                return MatchResult(
                    action=MatchAction.SUGGESTED_MATCH,
                    person_uuid=ident.person_uuid,
                    confidence=CONF_PASSPORT_NUMBER_ONLY,
                    method="passport_number_only",
                    features={
                        "identifier_type": "passport",
                        "nationality_match": nationality_match,
                        "dob_match": dob_match,
                    },
                )

        # ---- No deterministic hit -----------------------------------------
        return MatchResult(
            action=MatchAction.NO_MATCH_NO_CREATE,
            person_uuid=None,
            confidence=0.0,
            method="no_deterministic_match",
            features={
                "had_emirates_id": emirates_id is not None,
                "had_passport_number": passport_number is not None,
            },
        )
