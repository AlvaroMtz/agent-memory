"""OpenTelemetry metrics setup with no-op fallback.

Provides a ``MetricsProvider`` protocol that works with or without
the ``opentelemetry-api`` package installed.  When the package is
absent, all operations become no-ops.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _NoopMeter:
    """No-op meter when OpenTelemetry is not installed."""

    def counter(self, *a: Any, **kw: Any) -> Any:
        return _NoopCounter()

    def histogram(self, *a: Any, **kw: Any) -> Any:
        return _NoopHistogram()


class _NoopCounter:
    """No-op counter."""

    def add(self, *a: Any, **kw: Any) -> None:
        pass


class _NoopHistogram:
    """No-op histogram."""

    def record(self, *a: Any, **kw: Any) -> None:
        pass


class MetricsProvider:
    """Thin wrapper around OpenTelemetry metrics with graceful degradation.

    When ``opentelemetry-api`` is not installed, all operations are no-ops.
    """

    def __init__(self) -> None:
        self._meter: Any | None = None
        self._otel_available: bool = False

        try:
            from opentelemetry import metrics  # noqa: F401
            from opentelemetry.sdk.metrics import MeterProvider  # noqa: F401
            self._otel_available = True
        except ImportError:
            self._meter = _NoopMeter()
            self._otel_available = False

    def setup(
        self,
        service_name: str = "agent-memory",
        endpoint: str | None = None,
    ) -> "MetricsProvider":
        """Configure the underlying MeterProvider.

        Args:
            service_name: Name used in metric attributes.
            endpoint: Optional OTLP endpoint (unused in no-op mode).

        Returns:
            ``self`` for chaining.
        """
        if not self._otel_available:
            logger.info("OpenTelemetry not installed; metrics are no-ops")
            return self

        try:
            from opentelemetry import metrics as otel_metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                ConsoleMetricExporter,
                PeriodicExportingMetricReader,
            )

            reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
            provider = MeterProvider(metric_readers=[reader])
            otel_metrics.set_meter_provider(provider)

            self._meter = otel_metrics.get_meter(service_name)
        except Exception:
            logger.exception("Failed to initialize OpenTelemetry metrics; falling back to no-op")
            self._meter = _NoopMeter()
            self._otel_available = False

        return self

    def record_operation_duration(
        self,
        name: str,
        duration_ms: float,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """Record an operation duration histogram observation."""
        if self._meter is None:
            return

        try:
            histogram = self._meter.create_histogram(
                name=f"{name}.duration_ms",
                unit="ms",
                description=f"Duration of {name} in milliseconds",
            )
            histogram.record(duration_ms, attributes or {})
        except Exception:
            logger.exception("Failed to record operation duration '%s'", name)

    def record_memory_count(
        self,
        count: int,
        memory_type: str | None = None,
    ) -> None:
        """Record a memory count counter observation."""
        if self._meter is None:
            return

        try:
            counter = self._meter.create_counter(
                name=f"agent_memory.count",
                unit="1",
                description="Number of memory records",
            )
            attrs: dict[str, str] = {}
            if memory_type:
                attrs["memory_type"] = memory_type
            counter.add(count, attrs or None)
        except Exception:
            logger.exception("Failed to record memory count")


# Module-level singleton
_default_metrics: MetricsProvider | None = None


def setup_metrics(
    service_name: str = "agent-memory",
    endpoint: str | None = None,
) -> MetricsProvider:
    """Configure and return the global metrics provider.

    Args:
        service_name: Name used in metric attributes.
        endpoint: Optional OTLP endpoint.

    Returns:
        The configured ``MetricsProvider`` instance.
    """
    global _default_metrics
    if _default_metrics is None:
        _default_metrics = MetricsProvider()
    _default_metrics.setup(service_name=service_name, endpoint=endpoint)
    return _default_metrics


def record_operation_duration(
    name: str,
    duration_ms: float,
    attributes: dict[str, str] | None = None,
) -> None:
    """Record an operation duration using the global provider."""
    provider = _default_metrics or MetricsProvider()
    provider.record_operation_duration(name, duration_ms, attributes)


def record_memory_count(
    count: int,
    memory_type: str | None = None,
) -> None:
    """Record a memory count using the global provider."""
    provider = _default_metrics or MetricsProvider()
    provider.record_memory_count(count, memory_type)