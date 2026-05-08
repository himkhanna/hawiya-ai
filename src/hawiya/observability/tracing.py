"""OpenTelemetry tracing setup.

Wired in ``main.create_app`` and idempotent. The exporter is chosen from
settings:

- ``HAWIYA_OTEL_EXPORTER_OTLP_ENDPOINT`` set → OTLP/gRPC to that endpoint
  (Tempo, Jaeger, etc.).
- ``HAWIYA_OTEL_CONSOLE_EXPORTER`` true → console exporter (dev only).
- Neither set → no exporter; the SDK still attaches trace IDs but spans
  go to /dev/null. Cheaper than disabling tracing entirely and lets
  trace context propagate end-to-end if the consumer sends headers.

Auto-instrumentation: FastAPI only. SQLAlchemy auto-instrumentation
needs the engine reference at the moment of instrument(); we add it
in week 4 once the Postgres-backed idempotency store lands.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

from hawiya import __version__
from hawiya.config import get_settings

_configured = False


def configure_tracing(app: FastAPI) -> None:
    """Set up the global tracer provider and instrument the FastAPI app.

    Idempotent — safe to call from both ``create_app`` and the lifespan.
    """
    global _configured  # noqa: PLW0603 — once-per-process flag
    if _configured:
        return

    settings = get_settings()
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": __version__,
            "deployment.environment": settings.env.value,
        }
    )

    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    insecure=True,
                )
            )
        )
    if settings.otel_console_exporter:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        # Don't trace these — they're high-volume probes and would drown
        # signal in noise.
        excluded_urls="/v1/health,/v1/ready,/metrics",
    )
    _configured = True


def get_tracer(name: str = "hawiya") -> trace.Tracer:
    return trace.get_tracer(name, __version__)
