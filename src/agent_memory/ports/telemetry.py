"""TelemetryProvider port — abstract interface for observability."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TelemetryProvider(Protocol):
    """Port for distributed tracing and metrics.

    Implementations:
    - OpenTelemetrySpanProvider: production-grade telemetry
    - NoopTelemetryProvider: no-op for tests
    """

    # ── Spans ───────────────────────────────────────────────────────────────

    async def start_span(
        self,
        name: str,
        attributes: dict[str, str] | None = None,
    ) -> Any:
        """Start a new span.

        Returns a span context object to be used with end_span.
        """
        ...

    async def end_span(
        self,
        span: Any,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """End a span."""
        ...

    async def set_span_attribute(self, key: str, value: str) -> None:
        """Set an attribute on the current span."""
        ...

    # ── Metrics ─────────────────────────────────────────────────────────────

    async def increment_counter(
        self,
        name: str,
        value: int = 1,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric."""
        ...

    async def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram observation."""
        ...


class TelemetryProviderFactory(Protocol):
    """Factory for creating TelemetryProvider instances."""

    def create(self, **kwargs) -> TelemetryProvider: ...
