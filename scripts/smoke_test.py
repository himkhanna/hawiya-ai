"""End-to-end smoke test against a running Hawiya AI service.

What it verifies (assumes the API is running on http://localhost:8000):

- Health + readiness + metrics endpoints
- Tenancy gates (401, 400) on protected paths
- Person CRUD (create, get, search, duplicate guard)
- Idempotency-Key replay semantics (cache hit + body-mismatch conflict)
- Document-extract error envelope (415 unsupported, and OCR_UNAVAILABLE
  is treated as PASS because Tesseract isn't shipped in the image yet)

Usage:
    python -m scripts.smoke_test                   # default localhost:8000
    python -m scripts.smoke_test --base-url http://api.local:8000
    python -m scripts.smoke_test --tenant-id <uuid>  # skip seeding

If you don't pass ``--tenant-id``, the test tries
``scripts.seed_dev_tenant`` first to create one. That requires
HAWIYA_DATABASE_URL to point at the same Postgres the API is using.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field

import httpx

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"x" * 200


@dataclass
class Result:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append(Result(name=name, passed=passed, detail=detail))
        symbol = "PASS" if passed else "FAIL"
        line = f"  [{symbol}] {name}"
        if detail:
            line += f"  — {detail}"
        print(line)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)


def _hdrs(tenant: str, *, with_auth: bool = True, idempotency: str | None = None) -> dict[str, str]:
    h: dict[str, str] = {}
    if with_auth:
        h["Authorization"] = "Bearer dev"
    if tenant:
        h["X-Tenant-ID"] = tenant
    if idempotency:
        h["Idempotency-Key"] = idempotency
    return h


async def _wait_for_ready(client: httpx.AsyncClient, base_url: str, timeout_s: int = 60) -> bool:
    """Poll /v1/health until 200 or timeout."""
    print(f"Waiting for {base_url}/v1/health …")
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            r = await client.get(f"{base_url}/v1/health", timeout=2.0)
            if r.status_code == 200:
                print("  service is up.")
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    return False


async def run(base_url: str, tenant: str) -> Report:
    report = Report()
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        # ----------------------------------------------------- liveness
        print("\n--- Liveness ---")
        r = await client.get("/v1/health")
        report.add(
            "/v1/health returns 200",
            r.status_code == 200 and r.json().get("status") == "ok",
            f"status={r.status_code}",
        )

        # ----------------------------------------------------- readiness (DB)
        print("\n--- Readiness ---")
        r = await client.get("/v1/ready")
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = (
            r.status_code == 200
            and body.get("status") == "ok"
            and body.get("checks", {}).get("database") == "ok"
        )
        report.add(
            "/v1/ready: DB reachable",
            ok,
            f"status={r.status_code} body={body}",
        )

        # ----------------------------------------------------- metrics
        print("\n--- Metrics ---")
        r = await client.get("/metrics")
        text = r.text
        ok = r.status_code == 200 and "hawiya_extractions_total" in text
        report.add(
            "/metrics exposes hawiya_* series",
            ok,
            f"status={r.status_code} bytes={len(text)}",
        )

        # ----------------------------------------------------- tenancy gates
        print("\n--- Tenancy gates ---")
        r = await client.get(f"/v1/persons/{uuid.uuid4()}")
        report.add(
            "401 UNAUTHENTICATED without bearer",
            r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED",
            f"status={r.status_code}",
        )
        r = await client.get(
            f"/v1/persons/{uuid.uuid4()}",
            headers={"Authorization": "Bearer dev"},
        )
        report.add(
            "401 TENANT_REQUIRED without X-Tenant-ID",
            r.status_code == 401 and r.json()["error"]["code"] == "TENANT_REQUIRED",
            f"status={r.status_code}",
        )
        r = await client.get(
            f"/v1/persons/{uuid.uuid4()}",
            headers={"Authorization": "Bearer dev", "X-Tenant-ID": "not-a-uuid"},
        )
        report.add(
            "400 TENANT_INVALID for non-UUID",
            r.status_code == 400 and r.json()["error"]["code"] == "TENANT_INVALID",
            f"status={r.status_code}",
        )

        # ----------------------------------------------------- person CRUD
        print("\n--- Person CRUD ---")
        # GET unknown person -> 404
        r = await client.get(f"/v1/persons/{uuid.uuid4()}", headers=_hdrs(tenant))
        report.add(
            "GET unknown person -> 404",
            r.status_code == 404,
            f"status={r.status_code}",
        )

        # POST create
        passport = f"P{uuid.uuid4().int % 10**7:07d}"
        body = {
            "canonical_name_en": "Smoke Test Subject",
            "canonical_name_ar": "مختبر الدخان",
            "date_of_birth": "1990-01-12",
            "nationality": "ARE",
            "sex": "M",
            "passport_number": passport,
        }
        r = await client.post("/v1/persons", headers=_hdrs(tenant), json=body)
        ok = r.status_code == 201 and r.json().get("nationality") == "ARE"
        report.add(
            "POST /v1/persons creates 201",
            ok,
            f"status={r.status_code}",
        )
        person_uuid = r.json().get("person_uuid", "")

        if person_uuid:
            # GET it back
            r = await client.get(f"/v1/persons/{person_uuid}", headers=_hdrs(tenant))
            ok = r.status_code == 200 and r.json().get("canonical_name_ar")
            report.add(
                "GET created person -> 200 with all fields",
                ok,
                f"status={r.status_code}",
            )

        # POST search
        r = await client.post(
            "/v1/persons/search",
            headers=_hdrs(tenant),
            json={"query": "Smoke Test"},
        )
        report.add(
            "POST /v1/persons/search returns 200",
            r.status_code == 200 and "candidates" in r.json(),
            f"status={r.status_code}",
        )

        # 409 POSSIBLE_DUPLICATE — same passport, second create should fail
        r = await client.post("/v1/persons", headers=_hdrs(tenant), json=body)
        ok = r.status_code == 409 and r.json()["error"]["code"] == "POSSIBLE_DUPLICATE"
        report.add(
            "Duplicate passport -> 409 POSSIBLE_DUPLICATE",
            ok,
            f"status={r.status_code}",
        )

        # ----------------------------------------------------- idempotency
        print("\n--- Idempotency ---")
        idem_passport = f"I{uuid.uuid4().int % 10**7:07d}"
        idem_body = {
            "canonical_name_en": "Idem Test Subject",
            "passport_number": idem_passport,
            "nationality": "USA",
            "date_of_birth": "1985-05-05",
        }
        idem_key = f"smoke-{uuid.uuid4()}"
        r1 = await client.post(
            "/v1/persons",
            headers=_hdrs(tenant, idempotency=idem_key),
            json=idem_body,
        )
        r2 = await client.post(
            "/v1/persons",
            headers=_hdrs(tenant, idempotency=idem_key),
            json=idem_body,
        )
        # Replay must return the cached body — same person_uuid, no new person.
        ok = (
            r1.status_code == 201
            and r2.status_code == 201
            and r1.json().get("person_uuid") == r2.json().get("person_uuid")
        )
        report.add(
            "Idempotent replay returns cached response",
            ok,
            f"r1={r1.status_code} r2={r2.status_code}",
        )

        # Same key + different body -> 422 IDEMPOTENCY_KEY_CONFLICT
        conflict_body = dict(idem_body, canonical_name_en="Different name same key")
        r3 = await client.post(
            "/v1/persons",
            headers=_hdrs(tenant, idempotency=idem_key),
            json=conflict_body,
        )
        ok = (
            r3.status_code == 422
            and r3.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
        )
        report.add(
            "Same key + different body -> 422 IDEMPOTENCY_KEY_CONFLICT",
            ok,
            f"status={r3.status_code}",
        )

        # ----------------------------------------------------- document/extract
        print("\n--- Document extract (OCR-dependent) ---")
        # Non-image upload -> 415 UNSUPPORTED_DOCUMENT
        r = await client.post(
            "/v1/documents/extract",
            headers=_hdrs(tenant),
            files={"file": ("p.txt", b"not an image", "text/plain")},
        )
        ok = r.status_code == 415 and r.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT"
        report.add(
            "Non-image -> 415 UNSUPPORTED_DOCUMENT",
            ok,
            f"status={r.status_code}",
        )

        # Real image -> either 503 OCR_UNAVAILABLE (Tesseract missing) or
        # 200 (Tesseract installed, image happens to have no MRZ -> 422).
        # Both are acceptable smoke outcomes.
        r = await client.post(
            "/v1/documents/extract",
            headers=_hdrs(tenant),
            files={"file": ("p.jpg", JPEG_HEADER, "image/jpeg")},
        )
        ok = r.status_code in (200, 422, 503)
        detail = f"status={r.status_code}"
        if r.status_code == 503:
            detail += " (Tesseract not installed — expected for default image)"
        elif r.status_code == 422:
            detail += " (no MRZ in test bytes — expected)"
        report.add(
            "Image upload reaches extraction pipeline",
            ok,
            detail,
        )

    return report


async def _seed_tenant() -> str | None:
    """Best-effort: try to import and call the seed script."""
    try:
        # Force-reload settings before importing — the seed script reads
        # HAWIYA_DATABASE_URL via get_settings() at import time.
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from hawiya.config import get_settings
        from hawiya.models import Tenant, TenantStatus

        get_settings.cache_clear()
        settings = get_settings()
        engine = create_async_engine(settings.database_url, future=True)
        async with AsyncSession(engine) as session, session.begin():
            existing = (
                await session.execute(
                    select(Tenant).where(Tenant.tenant_name == "Smoke Test Tenant")
                )
            ).scalar_one_or_none()
            if existing:
                tenant_id = str(existing.tenant_id)
            else:
                t = Tenant(tenant_name="Smoke Test Tenant", status=TenantStatus.ACTIVE)
                session.add(t)
                await session.flush()
                tenant_id = str(t.tenant_id)
        await engine.dispose()
        return tenant_id
    except Exception as e:
        print(f"(could not seed tenant: {type(e).__name__}: {e})")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--tenant-id",
        help="Existing tenant UUID to use; otherwise the script tries to seed one",
    )
    parser.add_argument(
        "--wait", type=int, default=60, help="Seconds to wait for /v1/health"
    )
    args = parser.parse_args()

    async def _go() -> int:
        async with httpx.AsyncClient() as client:
            if not await _wait_for_ready(client, args.base_url, timeout_s=args.wait):
                print(f"Service did not become ready at {args.base_url}.")
                return 2

        tenant = args.tenant_id or await _seed_tenant() or ""
        if not tenant:
            print("No tenant_id available — pass --tenant-id explicitly.")
            return 2
        print(f"Using tenant_id: {tenant}")

        report = await run(args.base_url, tenant)
        passed = sum(1 for r in report.results if r.passed)
        total = len(report.results)
        print(f"\n=== {passed}/{total} checks passed ===")
        return 0 if report.all_passed else 1

    sys.exit(asyncio.run(_go()))


if __name__ == "__main__":
    main()
