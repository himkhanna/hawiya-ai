"""Reset the per-demo state so the UI's scenarios behave deterministically.

Run before each customer demo to clear the records that Scenario A and
the live-clicking around will have created on previous runs. Leaves the
seeded personas (Ahmed, Sara, Mohammed Bin Rashid, etc.) intact —
Scenario B depends on Ahmed.

What it deletes:
- Any Person whose primary passport is P1234567 (Mohamed Almansoori
  from Scenario A)
- Any Person whose primary passport is X9876543 (Fatima Alshamsi from
  the broader demo_flow.py)

The seeded Ahmed Almansoori (passport S0100100) is intentionally
preserved — Scenario B matches against him.

Usage:
    python -m scripts.reset_demo_session --tenant-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import httpx

# Passport numbers that the demo creates ad-hoc and should be wiped
# before each session.
DEMO_AD_HOC_PASSPORTS = ("P1234567", "X9876543")


async def _delete_demo_records(
    base_url: str, tenant_id: str
) -> tuple[int, list[str]]:
    """Find people created by the demo flow and DELETE them via direct DB.

    Uses the API's existing endpoints to look up; for the actual delete
    we call the postgres exec directly via docker (the API doesn't ship
    a DELETE endpoint by design — every record should be reversible by
    a human in production, not bulk-wiped).

    For Phase 1 demo convenience we wrap a docker exec; production
    deployments would never call this.
    """
    deleted: list[str] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        for passport in DEMO_AD_HOC_PASSPORTS:
            r = await client.post(
                "/v1/persons/search",
                headers={
                    "Authorization": "Bearer dev",
                    "X-Tenant-ID": tenant_id,
                },
                json={"query": passport, "limit": 5},
            )
            # If the API knows about it, mark for deletion.
            if r.status_code == 200:
                for c in r.json().get("candidates", []):
                    deleted.append(c["person_uuid"])

    if not deleted:
        return 0, []

    # We don't have a DELETE endpoint by design — call psql via docker
    # exec. This is dev-only.
    import subprocess

    placeholders = ",".join(f"'{p}'" for p in DEMO_AD_HOC_PASSPORTS)
    sql = f"""
        SET LOCAL app.current_tenant = '{tenant_id}';
        DELETE FROM persons WHERE person_uuid IN (
          SELECT person_uuid FROM person_identifiers
          WHERE identifier_value IN ({placeholders})
        );
    """
    cmd = [
        "docker",
        "compose",
        "-f",
        "deploy/docker-compose.yml",
        "-f",
        "deploy/docker-compose.override.yml",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "hawiya",
        "-d",
        "hawiya",
        "-c",
        sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        print(f"WARN: psql delete failed: {result.stderr[:200]}", file=sys.stderr)
        return 0, []
    return len(deleted), deleted


async def run(base_url: str, tenant_id: str) -> int:
    print(f"Resetting demo state for tenant {tenant_id}")
    print(
        "  This deletes ad-hoc records created by the demo UI "
        f"(passports {', '.join(DEMO_AD_HOC_PASSPORTS)})."
    )
    print("  Seeded personas (Ahmed, Sara, etc.) are kept intact.")
    print()

    n, ids = await _delete_demo_records(base_url, tenant_id)
    if n == 0:
        print("Nothing to delete. Demo state is clean.")
    else:
        print(f"Deleted {n} ad-hoc person record(s):")
        for pid in ids:
            print(f"  - {pid}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://localhost:8010")
    p.add_argument("--tenant-id", required=True)
    args = p.parse_args()

    try:
        uuid.UUID(args.tenant_id)
    except ValueError:
        print(f"--tenant-id must be a UUID: {args.tenant_id}", file=sys.stderr)
        sys.exit(2)

    sys.exit(asyncio.run(run(args.base_url, args.tenant_id)))


if __name__ == "__main__":
    main()
