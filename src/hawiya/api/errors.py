"""Structured error envelope per API_SPEC.md / CLAUDE.md §5."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from hawiya.tenancy.context import current_request_id


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "trace_id": current_request_id() or "",
            }
        },
    )
