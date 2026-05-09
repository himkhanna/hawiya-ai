"""Pre-load a demo tenant with a believable set of persons.

Run before a customer demo so ``POST /v1/persons/search`` returns ranked
candidates instead of an empty list, and so the Person Registry has
realistic-looking volume.

Each POST uses an Idempotency-Key derived from the passport number, so
re-running the seeder is a no-op (returns the same person UUIDs) and
won't 409 on a redeploy. If a row already exists with that passport
number, the duplicate guard returns 409 — we treat that as "already
seeded" and move on.

All names are fully synthetic. None of these match real people.

Usage:
    python -m scripts.seed_demo_persons \\
        --base-url http://localhost:8010 \\
        --tenant-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import Any

import httpx

PERSONAS: list[dict[str, Any]] = [
    # ---- UAE / Gulf -----------------------------------------------------
    # Almansoori variants make /v1/persons/search a richer demo: trigram
    # similarity ranks them against the "Mohamed Almansoori" extracted in
    # the demo flow, so the customer sees three ranked candidates instead
    # of one.
    {
        "canonical_name_en": "Ahmed Almansoori",
        "canonical_name_ar": "أحمد المنصوري",
        "passport_number": "S0100100",
        "nationality": "ARE",
        "date_of_birth": "1982-09-04",
        "sex": "M",
        "issuing_country": "ARE",
    },
    {
        "canonical_name_en": "Sara Almansoori",
        "canonical_name_ar": "سارة المنصوري",
        "passport_number": "S0100101",
        "nationality": "ARE",
        "date_of_birth": "1994-12-22",
        "sex": "F",
        "issuing_country": "ARE",
    },
    {
        "canonical_name_en": "Mohammed Bin Rashid",
        "canonical_name_ar": "محمد بن راشد",
        "passport_number": "S0100001",
        "nationality": "ARE",
        "date_of_birth": "1949-07-15",
        "sex": "M",
        "issuing_country": "ARE",
    },
    {
        "canonical_name_en": "Fatima Alshamsi",
        "canonical_name_ar": "فاطمة الشامسي",
        "passport_number": "S0100002",
        "nationality": "ARE",
        "date_of_birth": "1985-06-06",
        "sex": "F",
        "issuing_country": "ARE",
    },
    {
        "canonical_name_en": "Khalid Alkhalifa",
        "canonical_name_ar": "خالد الخليفة",
        "passport_number": "S0100003",
        "nationality": "BHR",
        "date_of_birth": "1972-11-20",
        "sex": "M",
        "issuing_country": "BHR",
    },
    {
        "canonical_name_en": "Aisha Almaktoum",
        "canonical_name_ar": "عائشة المكتوم",
        "passport_number": "S0100004",
        "nationality": "ARE",
        "date_of_birth": "1991-03-12",
        "sex": "F",
        "issuing_country": "ARE",
    },
    {
        "canonical_name_en": "Hamad Althani",
        "canonical_name_ar": "حمد آل ثاني",
        "passport_number": "S0100005",
        "nationality": "QAT",
        "date_of_birth": "1968-04-30",
        "sex": "M",
        "issuing_country": "QAT",
    },
    {
        "canonical_name_en": "Noura Alsabah",
        "canonical_name_ar": "نورة الصباح",
        "passport_number": "S0100006",
        "nationality": "KWT",
        "date_of_birth": "1988-09-09",
        "sex": "F",
        "issuing_country": "KWT",
    },
    {
        "canonical_name_en": "Layla Hariri",
        "canonical_name_ar": "ليلى الحريري",
        "passport_number": "S0100007",
        "nationality": "LBN",
        "date_of_birth": "1995-02-28",
        "sex": "F",
        "issuing_country": "LBN",
    },
    # ---- International --------------------------------------------------
    {
        "canonical_name_en": "John Smith",
        "passport_number": "S0100008",
        "nationality": "USA",
        "date_of_birth": "1978-04-04",
        "sex": "M",
        "issuing_country": "USA",
    },
    {
        "canonical_name_en": "Elizabeth Windsor",
        "passport_number": "S0100009",
        "nationality": "GBR",
        "date_of_birth": "1985-04-21",
        "sex": "F",
        "issuing_country": "GBR",
    },
    {
        "canonical_name_en": "Ravi Patel",
        "passport_number": "S0100010",
        "nationality": "IND",
        "date_of_birth": "1976-03-15",
        "sex": "M",
        "issuing_country": "IND",
    },
    {
        "canonical_name_en": "Yuki Tanaka",
        "passport_number": "S0100011",
        "nationality": "JPN",
        "date_of_birth": "1988-11-11",
        "sex": "F",
        "issuing_country": "JPN",
    },
]


async def _seed_one(
    client: httpx.AsyncClient, tenant_id: str, persona: dict[str, Any]
) -> tuple[str, str]:
    """Returns (status, label). status ∈ {created, exists, error}."""
    label = f"{persona['canonical_name_en']:<28} ({persona['nationality']} {persona['passport_number']})"
    try:
        resp = await client.post(
            "/v1/persons",
            headers={
                "Authorization": "Bearer dev",
                "X-Tenant-ID": tenant_id,
                "Idempotency-Key": f"seed-{persona['passport_number']}",
            },
            json=persona,
        )
    except httpx.HTTPError as e:
        return "error", f"{label} -- {type(e).__name__}: {e}"

    if resp.status_code == 201:
        return "created", label
    if resp.status_code == 409:
        # Duplicate guard fired — already seeded.
        return "exists", label
    return "error", f"{label} -- HTTP {resp.status_code}: {resp.text[:120]}"


async def run(base_url: str, tenant_id: str) -> int:
    print(f"Seeding {len(PERSONAS)} demo persons into tenant {tenant_id}")
    print(f"  via {base_url}\n")

    counts = {"created": 0, "exists": 0, "error": 0}
    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        for persona in PERSONAS:
            status, label = await _seed_one(client, tenant_id, persona)
            counts[status] += 1
            tag = {"created": "CREATED", "exists": "EXISTS ", "error": "FAILED "}[status]
            print(f"  [{tag}] {label}")

    print()
    print(
        f"Done. created={counts['created']} "
        f"exists={counts['exists']} "
        f"failed={counts['error']}"
    )
    return 0 if counts["error"] == 0 else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://localhost:8010")
    p.add_argument("--tenant-id", required=True, help="Demo tenant UUID")
    args = p.parse_args()

    try:
        uuid.UUID(args.tenant_id)
    except ValueError:
        print(f"--tenant-id must be a UUID: {args.tenant_id}", file=sys.stderr)
        sys.exit(2)

    sys.exit(asyncio.run(run(args.base_url, args.tenant_id)))


if __name__ == "__main__":
    main()
