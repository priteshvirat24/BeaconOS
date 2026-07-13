"""Beacon Command — OpenTelemetry Tracing.

Configures OpenTelemetry with OTLP export when endpoint is provided.
Falls back to no-op tracing when OTEL is not configured.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from beacon.logging import get_logger

logger = get_logger(__name__)


def configure_tracing(
    service_name: str = "beacon-command",
    otlp_endpoint: str = "",
) -> None:
    """Configure OpenTelemetry tracing.

    Args:
        service_name: Name of the service for traces.
        otlp_endpoint: OTLP exporter endpoint. If empty, uses console exporter in debug.
    """
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("otel_configured", endpoint=otlp_endpoint)
        except ImportError:
            logger.warning("otel_otlp_unavailable", reason="OTLP exporter not installed")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        logger.info("otel_noop", reason="No OTLP endpoint configured")

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for the given module/component name."""
    return trace.get_tracer(name)
