"""End-to-end tests for POST /v1/documents/extract.

Uses dependency overrides so the FastAPI app talks to a fake session and a
stub OCR adapter — no real Postgres or Tesseract required.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hawiya.api.dependencies import get_extraction_service, get_ocr_adapter
from hawiya.audit.writer import AuditWriter
from hawiya.db.session import get_session
from hawiya.extractors.ocr import NoMRZFoundError
from hawiya.main import create_app
from hawiya.services.extraction_service import ExtractionService

from .test_mrz import build_td3

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)


class StubOCR:
    def __init__(self, line1: str, line2: str) -> None:
        self._lines = (line1, line2)

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        return self._lines


class FailingOCR:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        raise self._exc


def _build_app(ocr: Any) -> tuple[Any, FakeSession]:
    app = create_app()
    session = FakeSession()

    async def _fake_session():
        yield session

    async def _fake_extraction_service():
        audit = AuditWriter(session)  # type: ignore[arg-type]
        yield ExtractionService(session=session, ocr=ocr, audit=audit)  # type: ignore[arg-type]

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_extraction_service] = _fake_extraction_service
    app.dependency_overrides[get_ocr_adapter] = lambda: ocr
    return app, session


@pytest.fixture
def tenant_id() -> str:
    return str(uuid.uuid4())


def _auth_headers(tenant: str) -> dict[str, str]:
    return {"Authorization": "Bearer dev", "X-Tenant-ID": tenant}


async def test_extract_returns_200_for_valid_passport(tenant_id: str) -> None:
    line1, line2 = build_td3(doc_number="P1234567")
    app, _ = _build_app(StubOCR(line1, line2))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/documents/extract",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.jpg", JPEG_HEADER + b"x" * 200, "image/jpeg")},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["document_type"] == "passport"
    assert body["checksum_status"] == "all_pass"
    assert body["fields"]["document_number"] == "P1234567"


async def test_extract_returns_415_for_non_image(tenant_id: str) -> None:
    app, _ = _build_app(StubOCR("x" * 44, "y" * 44))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/documents/extract",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT"


async def test_extract_returns_422_when_no_mrz_found(tenant_id: str) -> None:
    app, _ = _build_app(FailingOCR(NoMRZFoundError("could not locate MRZ")))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/documents/extract",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.jpg", JPEG_HEADER + b"x" * 200, "image/jpeg")},
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "DOCUMENT_UNREADABLE"


async def test_extract_returns_400_for_empty_upload(tenant_id: str) -> None:
    line1, line2 = build_td3()
    app, _ = _build_app(StubOCR(line1, line2))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/documents/extract",
            headers=_auth_headers(tenant_id),
            files={"file": ("p.jpg", b"", "image/jpeg")},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPTY_UPLOAD"


async def test_extract_requires_tenant(tenant_id: str) -> None:
    line1, line2 = build_td3()
    app, _ = _build_app(StubOCR(line1, line2))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Missing X-Tenant-ID — middleware blocks before reaching the route.
        resp = await ac.post(
            "/v1/documents/extract",
            headers={"Authorization": "Bearer dev"},
            files={"file": ("p.jpg", JPEG_HEADER, "image/jpeg")},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TENANT_REQUIRED"
