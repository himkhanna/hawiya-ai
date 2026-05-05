"""End-to-end test for POST /v1/identity/resolve.

Overrides the IdentityService dependency with a hand-built service backed
by stub OCR + in-memory repos so we exercise the real router/middleware
without Postgres or Tesseract.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hawiya.api.dependencies import get_identity_service, get_session
from hawiya.audit.writer import AuditWriter
from hawiya.main import create_app
from hawiya.matching.deterministic import DeterministicMatcher
from hawiya.services.extraction_service import ExtractionService
from hawiya.services.identity_service import IdentityService

from .test_identity_service import (
    JPEG_HEADER,
    FakeSession,
    StubIdentifierRepo,
    StubOCR,
    StubPersonRepo,
)
from .test_mrz import build_td3


def _build_app(line1: str, line2: str) -> tuple[Any, FakeSession, StubPersonRepo]:
    app = create_app()
    session = FakeSession()
    person_repo = StubPersonRepo()
    identifier_repo = StubIdentifierRepo()
    audit = AuditWriter(session)  # type: ignore[arg-type]
    matcher = DeterministicMatcher(
        identifier_repo=identifier_repo,  # type: ignore[arg-type]
        person_repo=person_repo,  # type: ignore[arg-type]
    )
    extraction = ExtractionService(
        session=session,  # type: ignore[arg-type]
        ocr=StubOCR(line1, line2),  # type: ignore[arg-type]
        audit=audit,
    )
    service = IdentityService(
        session=session,  # type: ignore[arg-type]
        extraction_service=extraction,
        matcher=matcher,
        person_repo=person_repo,  # type: ignore[arg-type]
        identifier_repo=identifier_repo,  # type: ignore[arg-type]
        audit=audit,
    )

    async def _fake_session():
        yield session

    async def _fake_identity_service():
        yield service

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_identity_service] = _fake_identity_service
    return app, session, person_repo


@pytest.fixture
def tenant_id() -> str:
    return str(uuid.uuid4())


def _auth_headers(tenant: str) -> dict[str, str]:
    return {"Authorization": "Bearer dev", "X-Tenant-ID": tenant}


async def test_resolve_creates_new_person_on_first_call(tenant_id: str) -> None:
    line1, line2 = build_td3(doc_number="P1234567", surname="ALMANSOORI", given="MOHAMED")
    app, _, person_repo = _build_app(line1, line2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/identity/resolve",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.jpg", JPEG_HEADER + b"x" * 200, "image/jpeg")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "new_record"
    assert body["person_uuid"] is not None
    assert body["fields"]["document_number"] == "P1234567"
    assert len(person_repo.created) == 1


async def test_resolve_with_create_false_returns_no_match(tenant_id: str) -> None:
    line1, line2 = build_td3()
    app, _, person_repo = _build_app(line1, line2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/identity/resolve",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.jpg", JPEG_HEADER + b"x" * 200, "image/jpeg")},
            data={"create_if_missing": "false"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "no_match_no_create"
    assert body["person_uuid"] is None
    assert person_repo.created == []


async def test_resolve_returns_415_for_non_image(tenant_id: str) -> None:
    line1, line2 = build_td3()
    app, _, _ = _build_app(line1, line2)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/identity/resolve",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT"


async def test_resolve_requires_tenant(tenant_id: str) -> None:
    line1, line2 = build_td3()
    app, _, _ = _build_app(line1, line2)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/identity/resolve",
            headers={"Authorization": "Bearer dev"},
            files={"file": ("p.jpg", JPEG_HEADER, "image/jpeg")},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TENANT_REQUIRED"
