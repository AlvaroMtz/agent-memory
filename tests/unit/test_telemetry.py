"""Unit tests for the telemetry modules (tracing.py and metrics.py)."""

from __future__ import annotations

import builtins
import contextlib
from unittest.mock import patch

import agent_memory.telemetry.tracing as tracing_module
from agent_memory.telemetry import redaction
from agent_memory.telemetry.metrics import (
    MetricsProvider,
    _NoopCounter,
    _NoopHistogram,
    _NoopMeter,
    record_memory_count,
    record_operation_duration,
    setup_metrics,
)
from agent_memory.telemetry.tracing import (
    TracingProvider,
    _NoopSpan,
    _NoopTracer,
    create_trace_context,
    setup_tracing,
    trace_operation,
)


class TestTracingProviderNoOp:
    """Tests for TracingProvider when OpenTelemetry is not installed."""

    def test_noop_span(self):
        """NoopSpan methods do nothing."""
        span = _NoopSpan()
        span.set_attribute("key", "value")
        span.end()
        # Should not raise

    def test_noop_tracer(self):
        """NoopTracer methods return NoopSpan."""
        tracer = _NoopTracer()
        span = tracer.start_span("test")
        assert isinstance(span, _NoopSpan)

        ctx = tracer.start_as_current_span("test")
        assert isinstance(ctx, contextlib.AbstractContextManager)
        with ctx as s:
            assert isinstance(s, _NoopSpan)

    def test_provider_no_otel(self):
        """Provider detects no OTel and falls back."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = TracingProvider()
            assert provider._otel_available is False
            assert isinstance(provider._tracer, _NoopTracer)

    def test_provider_setup_no_otel(self):
        """setup() on no-op provider returns self."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = TracingProvider()
            result = provider.setup("test-service")
            assert result is provider

    def test_trace_operation_no_otel(self):
        """trace_operation yields NoopSpan when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = TracingProvider()
            with provider.trace_operation("test-op") as span:
                assert isinstance(span, _NoopSpan)

    def test_create_trace_context_no_otel(self):
        """create_trace_context returns None when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = TracingProvider()
            ctx = provider.create_trace_context()
            assert ctx is None

    def test_trace_operation_uses_configured_tracer(self):
        """trace_operation starts a span, sets attributes, yields it, and ends it."""

        class Span:
            def __init__(self) -> None:
                self.attributes = {}
                self.ended = False

            def set_attribute(self, key, value) -> None:
                self.attributes[key] = value

            def end(self) -> None:
                self.ended = True

        class Tracer:
            def __init__(self) -> None:
                self.span = Span()
                self.names = []

            def start_span(self, name):
                self.names.append(name)
                return self.span

        tracer = Tracer()
        provider = TracingProvider()
        provider._otel_available = True
        provider._tracer = tracer

        with provider.trace_operation("remember", {"tenant": "t1", "count": "1"}) as span:
            assert span is tracer.span

        assert tracer.names == ["remember"]
        assert tracer.span.attributes == {"tenant": "t1", "count": "1"}
        assert tracer.span.ended is True

    def test_trace_operation_falls_back_on_tracer_error(self):
        """trace_operation yields a no-op span if the configured tracer fails."""

        class BrokenTracer:
            def start_span(self, name):
                raise RuntimeError("boom")

        provider = TracingProvider()
        provider._otel_available = True
        provider._tracer = BrokenTracer()

        with provider.trace_operation("broken") as span:
            assert isinstance(span, _NoopSpan)

    def test_create_trace_context_returns_otel_context_when_available(self):
        """create_trace_context returns an OTel context when context creation is available."""

        provider = TracingProvider()
        provider._otel_available = True

        assert provider.create_trace_context() is not None

    def test_setup_falls_back_when_otel_setup_fails(self):
        """setup falls back to no-op tracing if runtime OTel initialization fails."""

        real_import = builtins.__import__

        def fail_export_import(name, *args, **kwargs):
            if name == "opentelemetry.sdk.trace.export":
                raise RuntimeError("export setup failed")
            return real_import(name, *args, **kwargs)

        provider = TracingProvider()
        provider._otel_available = True

        with patch.object(builtins, "__import__", side_effect=fail_export_import):
            result = provider.setup("test-service")

        assert result is provider
        assert provider._otel_available is False
        assert isinstance(provider._tracer, _NoopTracer)


class TestMetricsProviderNoOp:
    """Tests for MetricsProvider when OpenTelemetry is not installed."""

    def test_noop_meter(self):
        """NoopMeter creates NoopCounter/NoopHistogram."""
        meter = _NoopMeter()
        counter = meter.counter("test")
        assert isinstance(counter, _NoopCounter)
        counter.add(1)  # should not raise

        histogram = meter.histogram("test")
        assert isinstance(histogram, _NoopHistogram)
        histogram.record(1.0)  # should not raise

    def test_noop_counter(self):
        """NoopCounter.add does nothing."""
        counter = _NoopCounter()
        counter.add(1)

    def test_noop_histogram(self):
        """NoopHistogram.record does nothing."""
        histogram = _NoopHistogram()
        histogram.record(1.0)

    def test_provider_no_otel(self):
        """Provider detects no OTel and falls back."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = MetricsProvider()
            assert provider._otel_available is False

    def test_record_duration_no_otel(self):
        """record_operation_duration does nothing when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = MetricsProvider()
            provider.record_operation_duration("test", 100.0)

    def test_record_memory_count_no_otel(self):
        """record_memory_count does nothing when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = MetricsProvider()
            provider.record_memory_count(5, "preference")

    def test_record_duration_uses_configured_meter(self):
        """record_operation_duration writes histogram observations when a meter exists."""

        class Histogram:
            def __init__(self) -> None:
                self.records = []

            def record(self, value, attributes):
                self.records.append((value, attributes))

        class Meter:
            def __init__(self) -> None:
                self.histogram = Histogram()
                self.args = None

            def create_histogram(self, **kwargs):
                self.args = kwargs
                return self.histogram

        meter = Meter()
        provider = MetricsProvider()
        provider._meter = meter

        provider.record_operation_duration("remember", 12.5, {"tenant": "t1"})

        assert meter.args["name"] == "remember.duration_ms"
        assert meter.histogram.records == [(12.5, {"tenant": "t1"})]

    def test_record_memory_count_uses_configured_meter(self):
        """record_memory_count writes counter observations and optional memory type."""

        class Counter:
            def __init__(self) -> None:
                self.adds = []

            def add(self, value, attributes):
                self.adds.append((value, attributes))

        class Meter:
            def __init__(self) -> None:
                self.counter = Counter()
                self.args = None

            def create_counter(self, **kwargs):
                self.args = kwargs
                return self.counter

        meter = Meter()
        provider = MetricsProvider()
        provider._meter = meter

        provider.record_memory_count(3, "semantic")
        provider.record_memory_count(2)

        assert meter.args["name"] == "agent_memory.count"
        assert meter.counter.adds == [(3, {"memory_type": "semantic"}), (2, None)]


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_setup_tracing(self):
        """setup_tracing returns a TracingProvider."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = setup_tracing("test")
            assert isinstance(provider, TracingProvider)

    def test_create_trace_context_no_otel(self):
        """create_trace_context returns None when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            ctx = create_trace_context()
            assert ctx is None

    def test_trace_operation_no_otel(self):
        """trace_operation yields NoopSpan when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            with trace_operation("test-op") as span:
                assert isinstance(span, _NoopSpan)

    def test_create_trace_context_uses_existing_global_provider(self, monkeypatch):
        """module-level create_trace_context uses the configured global provider state."""

        class Provider:
            _otel_available = True

        monkeypatch.setattr(tracing_module, "_default_provider", Provider())

        assert create_trace_context() is not None

    def test_setup_metrics(self):
        """setup_metrics returns a MetricsProvider."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            provider = setup_metrics("test")
            assert isinstance(provider, MetricsProvider)

    def test_record_operation_duration_no_otel(self):
        """record_operation_duration does nothing when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            record_operation_duration("test", 100.0)

    def test_record_memory_count_no_otel(self):
        """record_memory_count does nothing when no OTel."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            record_memory_count(5, "preference")


class TestRedaction:
    """Tests for telemetry log redaction."""

    def test_redacts_common_sensitive_values(self):
        text = (
            "email user@example.com phone +1 555-123-4567 "
            "api_key=abcdefghijklmnop token=abcdefghijklmnop "
            "Authorization: Bearer abc.def-ghi password=secret"
        )

        result = redaction.redact(text)

        assert "user@example.com" not in result
        assert "555-123-4567" not in result
        assert "abcdefghijklmnop" not in result
        assert "password=secret" not in result
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "[REDACTED]" in result

    def test_redacts_jwt_private_key_provider_tokens_and_base64(self):
        text = (
            "jwt eyJabc.def.ghi "
            "github ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ123456 "
            "slack xoxb-secret-token "
            "base64 QWxhZGRpbjpvcGVuIHNlc2FtZQAAAAAAAAAAAAAAAAAAAAAAAA== "
            "-----BEGIN RSA PRIVATE KEY-----secret-----END RSA PRIVATE KEY-----"
        )

        result = redaction.redact(text)

        assert "[JWT_REDACTED]" in result
        assert "ghp_[REDACTED]" in result
        assert "xoxb-[REDACTED]" in result
        assert "[BASE64_REDACTED]" in result
        assert "[PRIVATE_KEY_REDACTED]" in result

    def test_invalid_redaction_pattern_is_ignored(self, monkeypatch):
        monkeypatch.setattr(redaction, "PATTERNS", [("[", "x")])

        assert redaction.redact("keep me") == "keep me"
