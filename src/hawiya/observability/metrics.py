"""Prometheus metrics.

Two layers:

- HTTP basics (request count, latency, status) — auto-collected by
  ``prometheus-fastapi-instrumentator`` and exposed at ``/metrics``.

- Domain metrics — counters and histograms for the things ops actually
  pages on: extraction outcomes, match-action distribution, OCR backend
  failures. All carry a ``tenant_id`` label per CLAUDE.md §4 (per-tenant
  observability).

**Cardinality discipline:** ``tenant_id`` is bounded (one row per
customer environment). Don't add labels for high-cardinality fields like
``person_uuid`` or ``request_id`` — those go to traces, not metrics.
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# ---------------------------------------------------------------------------
# Domain metrics (declared at import time so they survive worker restarts).
# ---------------------------------------------------------------------------

EXTRACTIONS_TOTAL = Counter(
    "hawiya_extractions_total",
    "Document extractions by tenant and final checksum status.",
    labelnames=("tenant_id", "checksum_status", "processing_path"),
)

EXTRACTION_FAILURES_TOTAL = Counter(
    "hawiya_extraction_failures_total",
    "Document extractions that failed before producing a result.",
    labelnames=("tenant_id", "reason"),
)

EXTRACTION_DURATION_SECONDS = Histogram(
    "hawiya_extraction_duration_seconds",
    "End-to-end document extraction latency.",
    labelnames=("tenant_id",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

MATCH_ACTIONS_TOTAL = Counter(
    "hawiya_match_actions_total",
    "Identity-resolve outcomes by tenant.",
    labelnames=("tenant_id", "action"),
)

RATE_LIMITED_TOTAL = Counter(
    "hawiya_rate_limited_total",
    "Requests rejected by the rate limiter.",
    labelnames=("tenant_id", "endpoint_class"),
)


def configure_metrics(app: FastAPI) -> None:
    """Mount /metrics and the auto HTTP instrumentation on the app.

    Skips ``/v1/health``, ``/v1/ready``, and ``/metrics`` itself to avoid
    self-instrumentation noise.
    """
    Instrumentator(
        excluded_handlers=["/v1/health", "/v1/ready", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
