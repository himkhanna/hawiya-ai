"""Structured JSON logging for Hawiya AI.

Every log record is JSON, with ``tenant_id`` and ``request_id`` automatically
attached from the current context. Never log raw PII at INFO — use
``hawiya.security.pii.redact_pii`` first.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

from hawiya.config import Environment, get_settings
from hawiya.tenancy.context import current_request_id, current_tenant_id

if TYPE_CHECKING:
    from structlog.types import EventDict, Processor

_configured = False


def _inject_context(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    tenant_id = current_tenant_id()
    if tenant_id is not None and "tenant_id" not in event_dict:
        event_dict["tenant_id"] = str(tenant_id)
    request_id = current_request_id()
    if request_id is not None and "request_id" not in event_dict:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging() -> None:
    """Configure structlog + stdlib logging. Idempotent."""
    global _configured  # noqa: PLW0603 — once-per-process flag
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.env is Environment.DEV:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> Any:
    """Return a configured bound logger.

    Typed as ``Any`` because we use structlog's PrintLoggerFactory rather
    than the stdlib factory, so the concrete bound-logger class isn't a
    public structlog type.
    """
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)
