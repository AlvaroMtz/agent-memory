"""OpenTelemetry tracing setup with no-op fallback.

Provides a ``TracingProvider`` protocol that works with or without
the ``opentelemetry-api`` package installed.  When the package is
absent, all operations become no-ops.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _Span(Protocol):
    """Minimal span interface."""

    def set_attribute(self, key: str, value: str | int | float | bool) -> None: ...

    def end(self) -> None: ...


class _NoopSpan:
    """No-op span when OpenTelemetry is not installed."""

    def set_attribute(self, *a: Any, **kw: Any) -> None:
        pass

    def end(self, *a: Any, **kw: Any) -> None:
        pass


class _NoopTracer:
    """No-op tracer."""

    def start_span(self, *a: Any, **kw: Any) -> _Span:
        return _NoopSpan()

    def start_as_current_span(self, *a: Any, **kw: Any) -> contextlib.AbstractContextManager[_Span]:
        return contextlib.nullcontext(_NoopSpan())


class TracingProvider:
    """Thin wrapper around OpenTelemetry with graceful degradation.

    When ``opentelemetry-api`` is not installed, all operations are no-ops.
    """

    def __init__(self) -> None:
        self._tracer: Any | None = None
        self._otel_available: bool = False

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider

            self._tracer_provider: TracerProvider | None = None
            self._otel_available = True
        except ImportError:
            self._tracer = _NoopTracer()
            self._otel_available = False

    def setup(
        self,
        service_name: str = "agent-memory",
        endpoint: str | None = None,
    ) -> TracingProvider:
        """Configure the underlying TracerProvider.

        Args:
            service_name: Name used in trace attributes.
            endpoint: Optional OTLP endpoint (unused in no-op mode).

        Returns:
            ``self`` for chaining.
        """
        if not self._otel_available:
            logger.info("OpenTelemetry not installed; tracing is a no-op")
            return self

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )

            provider = TracerProvider(service_name=service_name)
            processor = BatchSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)

            self._tracer = trace.get_tracer(service_name)
            self._tracer_provider = provider
        except Exception:
            logger.exception("Failed to initialize OpenTelemetry; falling back to no-op")
            self._tracer = _NoopTracer()
            self._otel_available = False

        return self

    def create_trace_context(self) -> Any:
        """Create a new trace context (OpenTelemetry Context object)."""
        if not self._otel_available:
            return None
        try:
            from opentelemetry import context as otel_context

            return otel_context.Context()
        except Exception:
            return {}

    @contextlib.contextmanager
    def trace_operation(
        self,
        name: str,
        attributes: dict[str, str] | None = None,
    ):
        """Context manager that starts and ends a span.

        Usage::

            with provider.trace_operation("my-operation", {"key": "value"}):
                do_work()
        """
        if not self._otel_available or self._tracer is None:
            yield _NoopSpan()
            return

        try:
            span = self._tracer.start_span(name)
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, str(v))
            yield span
            span.end()
        except Exception:
            logger.exception("Error in trace_operation '%s'", name)
            yield _NoopSpan()


# Module-level singleton
_default_provider: TracingProvider | None = None


def setup_tracing(
    service_name: str = "agent-memory",
    endpoint: str | None = None,
) -> TracingProvider:
    """Configure and return the global tracing provider.

    Args:
        service_name: Name used in trace attributes.
        endpoint: Optional OTLP endpoint.

    Returns:
        The configured ``TracingProvider`` instance.
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = TracingProvider()
    _default_provider.setup(service_name=service_name, endpoint=endpoint)
    return _default_provider


def create_trace_context() -> Any:
    """Create a new trace context using the global provider."""
    provider = _default_provider or TracingProvider()
    if not provider._otel_available:
        return None
    try:
        from opentelemetry import context as otel_context

        return otel_context.Context()
    except Exception:
        return {}


def trace_operation(
    name: str,
    attributes: dict[str, str] | None = None,
):
    """Context manager using the global provider."""
    provider = _default_provider or TracingProvider()
    return provider.trace_operation(name, attributes)
