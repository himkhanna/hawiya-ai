"""End-to-end demo of the production identity-resolve flow.

Generates synthetic passport JPEGs, posts them to a running Hawiya AI
service, and walks the BUILD_PLAN week-3 definition-of-done:

    1. Submit a passport for the first time            -> new_record
    2. Submit the same passport again                  -> auto_matched
    3. Submit a different passport                     -> new_record
    4. Submit a 4th with mismatched DOB but same number-> suggested_match
    5. Search by name                                  -> ranked candidates

Every call exercises the real production code path: classify -> OCR
(PassportEye + Tesseract) -> ICAO 9303 checksums -> deterministic
matcher -> Person Registry -> audit log.

Two output modes:

    --verbose  (default): full HTTP status / raw extraction dump.
                          Use this to debug or to validate after a code
                          change.

    --clean    Customer-facing demo output. Hides HTTP plumbing, cleans
               OCR artifacts on the name field, prints one tidy block
               per step.

Usage:
    python -m scripts.demo_flow --base-url http://localhost:8010 \\
        --tenant-id <uuid> --clean
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

import httpx

from scripts.generate_passport_image import build_passport_image

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hdrs(tenant: str, *, idem: str | None = None) -> dict[str, str]:
    h = {"Authorization": "Bearer dev", "X-Tenant-ID": tenant}
    if idem:
        h["Idempotency-Key"] = idem
    return h


def _short(d: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: d.get(k) for k in keys}


def _clean_ocr_name(s: str | None) -> str | None:
    """Strip trailing 1-2 char OCR junk (e.g. ``MOHAMED            KK`` -> ``MOHAMED``)."""
    if not s:
        return s
    parts = [p for p in s.strip().split() if p]
    while len(parts) > 1 and len(parts[-1]) <= 2 and parts[-1].isalpha():
        parts.pop()
    return " ".join(parts)


def _verbose_section(title: str) -> None:
    print()
    print(f"=== {title} " + "=" * max(0, 60 - len(title)))


def _clean_banner(title: str) -> None:
    bar = "=" * 72
    print()
    print(bar)
    print(f" {title}")
    print(bar)


# ---------------------------------------------------------------------------
# A single resolve call, rendered in either mode.
# ---------------------------------------------------------------------------


async def _resolve_verbose(
    client: httpx.AsyncClient,
    tenant: str,
    *,
    label: str,
    image: bytes,
) -> dict[str, Any] | None:
    print(f"\n>> {label} ({len(image):,} bytes)")
    r = await client.post(
        "/v1/identity/resolve",
        headers=_hdrs(tenant),
        files={"file": ("passport.jpg", image, "image/jpeg")},
    )
    print(f"   HTTP {r.status_code}")
    try:
        body = r.json()
    except json.JSONDecodeError:
        print(f"   non-JSON body: {r.text[:200]!r}")
        return None
    if r.status_code >= 400:
        print(f"   error: {body.get('error', body)}")
        return None
    print(
        f"   action          = {body.get('action')!r}"
        f" (conf={body.get('confidence')})"
    )
    print(f"   person_uuid     = {body.get('person_uuid')}")
    print(f"   method          = {body.get('method')!r}")
    fields = body.get("fields", {})
    if fields:
        print(
            "   extracted       = "
            + json.dumps(
                _short(
                    fields,
                    (
                        "document_number",
                        "surname",
                        "given_names",
                        "nationality",
                        "date_of_birth",
                        "date_of_expiry",
                        "sex",
                    ),
                ),
                ensure_ascii=False,
            )
        )
    return body


_ACTION_LABEL = {
    "new_record": "NEW RECORD created",
    "auto_matched": "AUTO-MATCHED to existing record",
    "suggested_match": "SUGGESTED MATCH - HUMAN REVIEW REQUIRED",
    "manual_review": "MANUAL REVIEW (Phase 2)",
    "no_match_no_create": "NO MATCH (no record created)",
}


async def _resolve_clean(
    client: httpx.AsyncClient,
    tenant: str,
    *,
    presented_name: str,
    presented_country: str,
    presented_passport: str,
    presented_dob: str,
    image: bytes,
    notes: list[tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Customer-facing rendering of one /v1/identity/resolve call."""
    print(f"  Officer scans:    {presented_name}  ({presented_country})")
    print(f"  Passport number:  {presented_passport}")
    print(f"  Date of birth:    {presented_dob}")
    if notes:
        for k, v in notes:
            print(f"  {k:<17} {v}")
    print()

    r = await client.post(
        "/v1/identity/resolve",
        headers=_hdrs(tenant),
        files={"file": ("passport.jpg", image, "image/jpeg")},
    )
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {})
        except json.JSONDecodeError:
            err = {"code": r.status_code, "message": r.text[:120]}
        print(f"  >> ERROR: {err.get('code')} - {err.get('message')}")
        return None
    body = r.json()

    action = body.get("action", "?")
    label = _ACTION_LABEL.get(action, action.upper())
    conf_pct = round(float(body.get("confidence", 0)) * 100)
    print(f"  >> Hawiya AI decision:  {label}")
    print(f"     Person UUID:         {body.get('person_uuid')}")
    print(f"     Confidence:          {conf_pct}%")
    print(f"     Method:              {body.get('method')}")
    return body


# ---------------------------------------------------------------------------
# Demo flow
# ---------------------------------------------------------------------------


async def run_verbose(base_url: str, tenant: str) -> int:
    failures: list[str] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        _verbose_section("Step 1: first submission of P1234567 (expect NEW_RECORD)")
        img_a = build_passport_image(
            passport_number="P1234567",
            surname="ALMANSOORI",
            given="MOHAMED",
            nationality="ARE",
            issuing="ARE",
            dob="900112",
            expiry="300101",
            sex="M",
        )
        r1 = await _resolve_verbose(client, tenant, label="Mohamed Almansoori (UAE)", image=img_a)
        if not r1:
            return 1
        if r1.get("action") != "new_record":
            failures.append(f"Step 1 expected new_record, got {r1.get('action')}")
        person_uuid_a = r1.get("person_uuid")

        _verbose_section("Step 2: resubmit the same passport (expect AUTO_MATCHED)")
        r2 = await _resolve_verbose(client, tenant, label="Mohamed again", image=img_a)
        if not r2:
            return 1
        if r2.get("action") != "auto_matched":
            failures.append(f"Step 2 expected auto_matched, got {r2.get('action')}")
        if r2.get("person_uuid") != person_uuid_a:
            failures.append(
                f"Step 2 returned a DIFFERENT person_uuid "
                f"({r2.get('person_uuid')} != {person_uuid_a})"
            )

        _verbose_section("Step 3: a different passport (expect NEW_RECORD)")
        img_b = build_passport_image(
            passport_number="X9876543",
            surname="ALSHAMSI",
            given="FATIMA AISHA",
            nationality="ARE",
            issuing="ARE",
            dob="850606",
            expiry="290815",
            sex="F",
        )
        r3 = await _resolve_verbose(client, tenant, label="Fatima Alshamsi (UAE)", image=img_b)
        if not r3:
            return 1
        if r3.get("action") != "new_record":
            failures.append(f"Step 3 expected new_record, got {r3.get('action')}")
        if r3.get("person_uuid") == person_uuid_a:
            failures.append("Step 3 reused person_uuid_a — bad")

        _verbose_section(
            "Step 4: same passport number P1234567 but DOB tampered "
            "(expect SUGGESTED_MATCH)"
        )
        img_c = build_passport_image(
            passport_number="P1234567",
            surname="ALMANSOORI",
            given="MOHAMED",
            nationality="ARE",
            issuing="ARE",
            dob="850606",
            expiry="300101",
            sex="M",
        )
        r4 = await _resolve_verbose(client, tenant, label="Mohamed with tampered DOB", image=img_c)
        if not r4:
            return 1
        if r4.get("action") != "suggested_match":
            failures.append(f"Step 4 expected suggested_match, got {r4.get('action')}")
        if r4.get("person_uuid") != person_uuid_a:
            failures.append(
                "Step 4 should have suggested the existing person_uuid; "
                f"got {r4.get('person_uuid')} vs {person_uuid_a}"
            )

        _verbose_section("Step 5: search by name (expect ranked candidates)")
        r = await client.post(
            "/v1/persons/search",
            headers=_hdrs(tenant),
            json={"query": "MOHAMED ALMANSOORI"},
        )
        print(f"\n>> POST /v1/persons/search  HTTP {r.status_code}")
        if r.status_code != 200:
            failures.append(f"Step 5: search returned {r.status_code}")
        else:
            cands = r.json().get("candidates", [])
            print(f"   {len(cands)} candidate(s):")
            for c in cands[:5]:
                print(
                    f"     - {c.get('person_uuid')[:8]}...  "
                    f"{c.get('canonical_name_en')!r:<35} "
                    f"{c.get('nationality')}"
                )

        _verbose_section("Summary")
        if failures:
            print("FAIL")
            for f in failures:
                print(f"  - {f}")
            return 1
        print("All five steps behaved as expected.")
        return 0


async def run_clean(base_url: str, tenant: str) -> int:
    failures: list[str] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # ---------- Step 1 ----------------------------------------------
        _clean_banner("Step 1 - First-time submission")
        print()
        img_a = build_passport_image(
            passport_number="P1234567",
            surname="ALMANSOORI",
            given="MOHAMED",
            nationality="ARE",
            issuing="ARE",
            dob="900112",
            expiry="300101",
            sex="M",
        )
        r1 = await _resolve_clean(
            client, tenant,
            presented_name="Mohamed Almansoori",
            presented_country="UAE",
            presented_passport="P1234567",
            presented_dob="1990-01-12",
            image=img_a,
        )
        if not r1:
            return 1
        if r1.get("action") != "new_record":
            failures.append("Step 1 should have created a new record")
        person_uuid_a = r1.get("person_uuid")

        # ---------- Step 2 ----------------------------------------------
        _clean_banner("Step 2 - Same passport submitted again")
        print()
        r2 = await _resolve_clean(
            client, tenant,
            presented_name="Mohamed Almansoori",
            presented_country="UAE",
            presented_passport="P1234567",
            presented_dob="1990-01-12",
            image=img_a,
            notes=[("Note:", "the system has seen this passport before")],
        )
        if not r2:
            return 1
        if r2.get("action") != "auto_matched":
            failures.append("Step 2 should have auto-matched")
        if r2.get("person_uuid") == person_uuid_a:
            print("     >> No duplicate created. Same person UUID as Step 1.")
        else:
            failures.append("Step 2 returned a different person UUID")

        # ---------- Step 3 ----------------------------------------------
        _clean_banner("Step 3 - A different person")
        print()
        img_b = build_passport_image(
            passport_number="X9876543",
            surname="ALSHAMSI",
            given="FATIMA AISHA",
            nationality="ARE",
            issuing="ARE",
            dob="850606",
            expiry="290815",
            sex="F",
        )
        r3 = await _resolve_clean(
            client, tenant,
            presented_name="Fatima Alshamsi",
            presented_country="UAE",
            presented_passport="X9876543",
            presented_dob="1985-06-06",
            image=img_b,
        )
        if not r3:
            return 1
        if r3.get("action") != "new_record":
            failures.append("Step 3 should have created a new record")
        if r3.get("person_uuid") == person_uuid_a:
            failures.append("Step 3 reused Mohamed's UUID")

        # ---------- Step 4 ----------------------------------------------
        _clean_banner("Step 4 - Same passport number, tampered date of birth")
        print()
        img_c = build_passport_image(
            passport_number="P1234567",
            surname="ALMANSOORI",
            given="MOHAMED",
            nationality="ARE",
            issuing="ARE",
            dob="850606",
            expiry="300101",
            sex="M",
        )
        r4 = await _resolve_clean(
            client, tenant,
            presented_name="Mohamed Almansoori",
            presented_country="UAE",
            presented_passport="P1234567 (matches existing)",
            presented_dob="1985-06-06 (Step 1 record had 1990-01-12)",
            image=img_c,
            notes=[("Note:", "this is the kind of mismatch a fraudster might try")],
        )
        if not r4:
            return 1
        if r4.get("action") != "suggested_match":
            failures.append("Step 4 should have suggested a match")
        if r4.get("person_uuid") != person_uuid_a:
            failures.append("Step 4 didn't surface Step 1's record")
        else:
            print("     >> System refused to auto-match. Routed to human review.")

        # ---------- Step 5 ----------------------------------------------
        _clean_banner("Step 5 - Officer searches by name")
        print()
        # Surname query: hits Mohamed Almansoori (just extracted in Step 1)
        # plus the Ahmed and Sara Almansoori personas seeded by
        # scripts.seed_demo_persons. Trigram similarity ranks them.
        r = await client.post(
            "/v1/persons/search",
            headers=_hdrs(tenant),
            json={"query": "Almansoori", "limit": 10},
        )
        print('  Query: "Almansoori"')
        print()
        if r.status_code != 200:
            failures.append(f"Search returned {r.status_code}")
        else:
            cands = r.json().get("candidates", [])
            print(f"  {len(cands)} candidate(s) returned, ranked by similarity:")
            for c in cands[:10]:
                name = _clean_ocr_name(c.get("canonical_name_en")) or "(no Latin name)"
                uid = (c.get("person_uuid") or "")[:8]
                print(
                    f"    - {uid}...  {name:<32}  "
                    f"{c.get('nationality') or '???':<3}  "
                    f"DOB {c.get('date_of_birth') or '?'}"
                )

        # ---------- Summary ---------------------------------------------
        _clean_banner("Summary")
        if failures:
            print()
            print("  Demo did NOT match expectations:")
            for f in failures:
                print(f"   - {f}")
            return 1
        print()
        print("  All four scenarios behaved exactly as the BUILD_PLAN specifies:")
        print("    Step 1 (first submission)        -> NEW RECORD created")
        print("    Step 2 (same passport again)     -> AUTO MATCHED, no duplicate")
        print("    Step 3 (different person)        -> NEW RECORD")
        print("    Step 4 (tampered DOB)            -> SUGGESTED MATCH (human review)")
        print()
        print("  Every decision above was written to the audit_log table with")
        print("  its inputs, confidence, and method. Nothing is unrecoverable.")
        print()
        return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://localhost:8010")
    p.add_argument(
        "--tenant-id",
        help="Tenant UUID to use. If omitted, prints how to seed one.",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Demo-grade output (cleaner, customer-facing). "
        "Default is --verbose for debugging.",
    )
    args = p.parse_args()

    if not args.tenant_id:
        print(
            "Need --tenant-id. Seed one with:\n"
            '  docker compose -f deploy/docker-compose.yml '
            "-f deploy/docker-compose.override.yml exec api "
            "python -m scripts.seed_dev_tenant",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        uuid.UUID(args.tenant_id)
    except ValueError:
        print(f"--tenant-id is not a valid UUID: {args.tenant_id}", file=sys.stderr)
        sys.exit(2)

    runner = run_clean if args.clean else run_verbose
    sys.exit(asyncio.run(runner(args.base_url, args.tenant_id)))


if __name__ == "__main__":
    main()
