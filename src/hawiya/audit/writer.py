"""Audit log writer.

Every AI decision MUST go through here per CLAUDE.md §2. The writer pulls
``request_id`` from the per-request context so callers don't have to
thread it through every signature.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hawiya.models import AuditLog
from hawiya.tenancy.context import current_request_id


class AuditWriter:
    """Append-only writer for ``audit_log``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def write(
        self,
        *,
        tenant_id: UUID,
        endpoint: str,
        input_hash: str | None = None,
        output_summary: dict[str, Any] | None = None,
        model_versions: dict[str, Any] | None = None,
        confidence: float | None = None,
        processing_path: str | None = None,
        decision: str | None = None,
        user_id: str | None = None,
    ) -> None:
        request_id = current_request_id() or "no-request-id"
        log = AuditLog(
            tenant_id=tenant_id,
            request_id=request_id,
            user_id=user_id,
            endpoint=endpoint,
            input_hash=input_hash,
            output_summary=output_summary,
            model_versions=model_versions,
            confidence=confidence,
            processing_path=processing_path,
            decision=decision,
        )
        self.session.add(log)
