"""Create or look up a development tenant.

Idempotent: if a tenant named ``WizSM Dev`` already exists, prints its
existing UUID. Use only against dev databases.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from hawiya.config import Environment, get_settings
from hawiya.db.session import _get_factory
from hawiya.models import Tenant, TenantStatus

DEV_TENANT_NAME = "WizSM Dev"


async def _seed() -> None:
    settings = get_settings()
    if settings.env is Environment.PROD:
        print("Refusing to seed: HAWIYA_ENV=prod", file=sys.stderr)
        sys.exit(2)

    factory = _get_factory()
    async with factory() as session:  # type: AsyncSession
        async with session.begin():
            existing = (
                await session.execute(select(Tenant).where(Tenant.tenant_name == DEV_TENANT_NAME))
            ).scalar_one_or_none()
            if existing is not None:
                tenant = existing
                action = "exists"
            else:
                tenant = Tenant(
                    tenant_name=DEV_TENANT_NAME,
                    status=TenantStatus.ACTIVE,
                    config={
                        "matching": {
                            "auto_merge_threshold": 0.95,
                            "suggest_merge_threshold": 0.80,
                            "manual_review_threshold": 0.55,
                        },
                        "supported_documents": ["passport"],
                    },
                )
                session.add(tenant)
                action = "created"

    print(f"tenant {action}:")
    print(f"  tenant_id  : {tenant.tenant_id}")
    print(f"  tenant_name: {tenant.tenant_name}")
    print(f"  bearer     : {settings.dev_bearer_token}")
    print()
    print("Try:")
    print(
        f"  curl -H 'X-Tenant-ID: {tenant.tenant_id}' "
        f"-H 'Authorization: Bearer {settings.dev_bearer_token}' "
        "http://localhost:8000/v1/health"
    )


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
