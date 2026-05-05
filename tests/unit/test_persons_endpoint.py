"""End-to-end tests for /v1/persons routes."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hawiya.api.dependencies import (
    get_audit_writer,
    get_identifier_repository,
    get_matcher,
    get_person_repository,
    get_session,
)
from hawiya.audit.writer import AuditWriter
from hawiya.main import create_app
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.models import (
    IdentifierType,
    Person,
    PersonIdentifier,
    PersonStatus,
)

from .test_identity_service import (
    FakeSession,
    StubIdentifierRepo,
    StubPersonRepo,
)


def _build_app(
    persons: dict[uuid.UUID, Person] | None = None,
    identifiers: list[PersonIdentifier] | None = None,
    search_results: list[Person] | None = None,
) -> tuple[Any, FakeSession, StubPersonRepo, StubIdentifierRepo]:
    app = create_app()
    session = FakeSession()
    person_repo = StubPersonRepo(persons=persons or {})
    identifier_repo = StubIdentifierRepo(rows=identifiers or [])
    audit = AuditWriter(session)  # type: ignore[arg-type]
    matcher = DeterministicMatcher(
        identifier_repo=identifier_repo,  # type: ignore[arg-type]
        person_repo=person_repo,  # type: ignore[arg-type]
    )

    # Patch in a search_by_name method on the stub since the real repo has it.
    async def _search_by_name(tenant_id: uuid.UUID, query: str, *, limit: int = 10) -> list[Person]:
        return list(search_results or [])

    person_repo.search_by_name = _search_by_name  # type: ignore[attr-defined]

    async def _fake_session():
        yield session

    async def _fake_person_repo():
        yield person_repo

    async def _fake_identifier_repo():
        yield identifier_repo

    async def _fake_matcher():
        yield matcher

    async def _fake_audit():
        yield audit

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_person_repository] = _fake_person_repo
    app.dependency_overrides[get_identifier_repository] = _fake_identifier_repo
    app.dependency_overrides[get_matcher] = _fake_matcher
    app.dependency_overrides[get_audit_writer] = _fake_audit
    return app, session, person_repo, identifier_repo


@pytest.fixture
def tenant_id() -> str:
    return str(uuid.uuid4())


def _auth(tenant: str) -> dict[str, str]:
    return {"Authorization": "Bearer dev", "X-Tenant-ID": tenant}


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _person(
    *,
    tenant: uuid.UUID,
    en: str | None = "John Smith",
    nationality: str | None = "USA",
    dob: date | None = date(1980, 1, 1),
) -> Person:
    p = Person(
        person_uuid=uuid.uuid4(),
        tenant_id=tenant,
        canonical_name_en=en,
        nationality=nationality,
        date_of_birth=dob,
        status=PersonStatus.ACTIVE,
    )
    # Server-side defaults aren't populated for in-memory objects; set manually.
    p.created_at = _now()
    p.updated_at = _now()
    return p


# ---------------------------------------------------------------------------
# GET /v1/persons/{uuid}
# ---------------------------------------------------------------------------


async def test_get_person_returns_full_record(tenant_id: str) -> None:
    tenant = uuid.UUID(tenant_id)
    p = _person(tenant=tenant, en="Mohamed Almansoori", nationality="ARE")
    app, _, _, _ = _build_app(persons={p.person_uuid: p})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/persons/{p.person_uuid}", headers=_auth(tenant_id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["person_uuid"] == str(p.person_uuid)
    assert body["canonical_name_en"] == "Mohamed Almansoori"
    assert body["nationality"] == "ARE"
    assert body["status"] == "active"


async def test_get_person_404_when_missing(tenant_id: str) -> None:
    app, _, _, _ = _build_app()
    missing = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/persons/{missing}", headers=_auth(tenant_id))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_get_person_does_not_leak_other_tenants(tenant_id: str) -> None:
    other_tenant = uuid.uuid4()
    p = _person(tenant=other_tenant)
    # The repo's get() filters by tenant_id, so this returns None for
    # tenant_id (the request tenant).
    app, _, _, _ = _build_app(persons={p.person_uuid: p})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/persons/{p.person_uuid}", headers=_auth(tenant_id))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /v1/persons
# ---------------------------------------------------------------------------


async def test_create_person_happy_path(tenant_id: str) -> None:
    app, _, person_repo, identifier_repo = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/persons",
            headers=_auth(tenant_id),
            json={
                "canonical_name_en": "Mohamed Almansoori",
                "canonical_name_ar": "محمد المنصوري",
                "date_of_birth": "1990-01-12",
                "nationality": "ARE",
                "sex": "M",
                "passport_number": "P1234567",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["canonical_name_en"] == "Mohamed Almansoori"
    assert body["nationality"] == "ARE"
    assert len(person_repo.created) == 1
    assert len(identifier_repo.created) == 1
    assert identifier_repo.created[0].identifier_value == "P1234567"


async def test_create_person_409_when_passport_already_exists(tenant_id: str) -> None:
    tenant = uuid.UUID(tenant_id)
    existing_person_uuid = uuid.uuid4()
    existing_person = _person(
        tenant=tenant, en="Existing", nationality="ARE", dob=date(1990, 1, 12)
    )
    existing_person.person_uuid = existing_person_uuid
    existing_identifier = PersonIdentifier(
        identifier_id=uuid.uuid4(),
        tenant_id=tenant,
        person_uuid=existing_person_uuid,
        identifier_type=IdentifierType.PASSPORT,
        identifier_value="P1234567",
    )
    app, _, person_repo, _ = _build_app(
        persons={existing_person_uuid: existing_person},
        identifiers=[existing_identifier],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/persons",
            headers=_auth(tenant_id),
            json={
                "canonical_name_en": "Trying To Re-Create",
                "date_of_birth": "1990-01-12",
                "nationality": "ARE",
                "passport_number": "P1234567",
            },
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "POSSIBLE_DUPLICATE"
    assert body["error"]["details"]["candidate_person_uuid"] == str(existing_person_uuid)
    # Critically: no person actually created.
    assert person_repo.created == []


async def test_create_person_validates_nationality_length(tenant_id: str) -> None:
    app, _, _, _ = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/persons",
            headers=_auth(tenant_id),
            json={"canonical_name_en": "Test", "nationality": "AR"},  # too short
        )
    assert resp.status_code == 422  # Pydantic validation


# ---------------------------------------------------------------------------
# POST /v1/persons/search
# ---------------------------------------------------------------------------


async def test_search_returns_ranked_candidates(tenant_id: str) -> None:
    tenant = uuid.UUID(tenant_id)
    candidates = [
        _person(tenant=tenant, en="Mohamed Almansoori"),
        _person(tenant=tenant, en="Mohamad Almansouri"),
    ]
    app, _, _, _ = _build_app(search_results=candidates)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/persons/search",
            headers=_auth(tenant_id),
            json={"query": "Mohamed Almansoori"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["canonical_name_en"] == "Mohamed Almansoori"


async def test_search_validates_empty_query(tenant_id: str) -> None:
    app, _, _, _ = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/persons/search", headers=_auth(tenant_id), json={"query": ""})
    assert resp.status_code == 422


async def test_search_validates_limit_upper_bound(tenant_id: str) -> None:
    app, _, _, _ = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/persons/search",
            headers=_auth(tenant_id),
            json={"query": "x", "limit": 10000},
        )
    assert resp.status_code == 422
