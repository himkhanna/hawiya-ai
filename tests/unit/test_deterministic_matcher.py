"""DeterministicMatcher unit tests using stub repositories."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

import pytest

from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.matching.types import MatchAction
from hawiya.models import IdentifierType


@dataclass
class StubIdentifier:
    person_uuid: uuid.UUID
    identifier_type: IdentifierType
    identifier_value: str


@dataclass
class StubPerson:
    person_uuid: uuid.UUID
    nationality: str | None = None
    date_of_birth: date | None = None


@dataclass
class StubIdentifierRepo:
    rows: list[StubIdentifier] = field(default_factory=list)

    async def find_active(
        self,
        tenant_id: uuid.UUID,
        identifier_type: IdentifierType,
        identifier_value: str,
    ) -> StubIdentifier | None:
        for r in self.rows:
            if r.identifier_type is identifier_type and r.identifier_value == identifier_value:
                return r
        return None


@dataclass
class StubPersonRepo:
    rows: dict[uuid.UUID, StubPerson] = field(default_factory=dict)

    async def get(self, tenant_id: uuid.UUID, person_uuid: uuid.UUID) -> StubPerson | None:
        return self.rows.get(person_uuid)


def _matcher(
    identifiers: list[StubIdentifier] | None = None,
    persons: dict[uuid.UUID, StubPerson] | None = None,
) -> DeterministicMatcher:
    return DeterministicMatcher(
        identifier_repo=StubIdentifierRepo(rows=identifiers or []),  # type: ignore[arg-type]
        person_repo=StubPersonRepo(rows=persons or {}),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Step 1: Emirates ID exact match
# ---------------------------------------------------------------------------


async def test_emirates_id_exact_match_auto_matched() -> None:
    tenant = uuid.uuid4()
    person = uuid.uuid4()
    matcher = _matcher(
        identifiers=[
            StubIdentifier(
                person_uuid=person,
                identifier_type=IdentifierType.EMIRATES_ID,
                identifier_value="784-1990-1234567-1",
            ),
        ]
    )
    result = await matcher.match(tenant, emirates_id="784-1990-1234567-1")
    assert result.action is MatchAction.AUTO_MATCHED
    assert result.person_uuid == person
    assert result.confidence == 1.00
    assert result.method == "emirates_id_exact"


async def test_emirates_id_no_match_falls_through() -> None:
    tenant = uuid.uuid4()
    matcher = _matcher()
    result = await matcher.match(tenant, emirates_id="784-1990-9999999-9")
    assert result.action is MatchAction.NO_MATCH_NO_CREATE
    assert result.person_uuid is None
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Step 2: Passport + nationality + DOB exact
# ---------------------------------------------------------------------------


async def test_passport_full_match_auto_matched() -> None:
    tenant = uuid.uuid4()
    person = uuid.uuid4()
    matcher = _matcher(
        identifiers=[
            StubIdentifier(
                person_uuid=person,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value="P1234567",
            ),
        ],
        persons={
            person: StubPerson(
                person_uuid=person, nationality="ARE", date_of_birth=date(1990, 1, 12)
            ),
        },
    )
    result = await matcher.match(
        tenant,
        passport_number="P1234567",
        nationality="ARE",
        date_of_birth=date(1990, 1, 12),
    )
    assert result.action is MatchAction.AUTO_MATCHED
    assert result.person_uuid == person
    assert result.confidence == 0.99
    assert result.features["nationality_match"] is True
    assert result.features["dob_match"] is True


# ---------------------------------------------------------------------------
# Step 3: Passport number alone → SUGGESTED_MATCH
# ---------------------------------------------------------------------------


async def test_passport_number_alone_yields_suggested() -> None:
    """Passport number matches but nationality/DOB are missing or differ."""
    tenant = uuid.uuid4()
    person = uuid.uuid4()
    matcher = _matcher(
        identifiers=[
            StubIdentifier(
                person_uuid=person,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value="P1234567",
            ),
        ],
        persons={
            person: StubPerson(
                person_uuid=person, nationality="ARE", date_of_birth=date(1990, 1, 12)
            ),
        },
    )
    result = await matcher.match(
        tenant,
        passport_number="P1234567",
        nationality="USA",  # mismatched
        date_of_birth=date(1985, 5, 5),
    )
    assert result.action is MatchAction.SUGGESTED_MATCH
    assert result.person_uuid == person
    assert result.confidence == 0.90
    assert result.features["nationality_match"] is False
    assert result.features["dob_match"] is False


async def test_passport_number_only_no_demographics_supplied() -> None:
    tenant = uuid.uuid4()
    person = uuid.uuid4()
    matcher = _matcher(
        identifiers=[
            StubIdentifier(
                person_uuid=person,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value="P1234567",
            ),
        ],
        persons={person: StubPerson(person_uuid=person)},
    )
    result = await matcher.match(tenant, passport_number="P1234567")
    assert result.action is MatchAction.SUGGESTED_MATCH
    assert result.confidence == 0.90


async def test_passport_no_match_returns_no_match() -> None:
    tenant = uuid.uuid4()
    matcher = _matcher()
    result = await matcher.match(
        tenant,
        passport_number="P9999999",
        nationality="ARE",
        date_of_birth=date(1990, 1, 12),
    )
    assert result.action is MatchAction.NO_MATCH_NO_CREATE
    assert result.person_uuid is None


# ---------------------------------------------------------------------------
# Order: Emirates ID is checked before passport
# ---------------------------------------------------------------------------


async def test_emirates_id_takes_precedence_over_passport() -> None:
    tenant = uuid.uuid4()
    person_eid = uuid.uuid4()
    person_passport = uuid.uuid4()
    matcher = _matcher(
        identifiers=[
            StubIdentifier(
                person_uuid=person_eid,
                identifier_type=IdentifierType.EMIRATES_ID,
                identifier_value="784-1234567-1",
            ),
            StubIdentifier(
                person_uuid=person_passport,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value="P9999999",
            ),
        ],
        persons={
            person_eid: StubPerson(person_uuid=person_eid),
            person_passport: StubPerson(person_uuid=person_passport),
        },
    )
    result = await matcher.match(
        tenant,
        emirates_id="784-1234567-1",
        passport_number="P9999999",
    )
    assert result.person_uuid == person_eid
    assert result.confidence == 1.00


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


async def test_no_identifiers_supplied_returns_no_match() -> None:
    tenant = uuid.uuid4()
    matcher = _matcher()
    result = await matcher.match(tenant)
    assert result.action is MatchAction.NO_MATCH_NO_CREATE


# Phase 1 sanity: SUGGESTED_MATCH never auto-matches; AUTO requires demographics.
@pytest.mark.parametrize(
    ("nationality", "dob", "expected_confidence"),
    [
        ("ARE", date(1990, 1, 12), 0.99),  # full match
        ("ARE", date(1990, 1, 13), 0.90),  # DOB off by one day
        ("USA", date(1990, 1, 12), 0.90),  # nationality differs
        (None, None, 0.90),  # no demographics provided
    ],
)
async def test_passport_confidence_table(
    nationality: str | None, dob: date | None, expected_confidence: float
) -> None:
    tenant = uuid.uuid4()
    person = uuid.uuid4()
    matcher = _matcher(
        identifiers=[
            StubIdentifier(
                person_uuid=person,
                identifier_type=IdentifierType.PASSPORT,
                identifier_value="P1234567",
            ),
        ],
        persons={
            person: StubPerson(
                person_uuid=person, nationality="ARE", date_of_birth=date(1990, 1, 12)
            ),
        },
    )
    result = await matcher.match(
        tenant,
        passport_number="P1234567",
        nationality=nationality,
        date_of_birth=dob,
    )
    assert result.confidence == expected_confidence
