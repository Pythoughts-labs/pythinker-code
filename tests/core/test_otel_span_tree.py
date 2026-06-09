"""obs-eval-1: start_span installs the span as current so the trace tree connects.

Before the fix, start_span created spans without attaching them to the OTel context,
so turn / llm / tool spans appeared as flat sibling roots. These tests lock the
nesting behavior, the GenAI-semconv attribute plumbing, and the narrow detach-
mismatch guard that lets the fix coexist with Ctrl-C interrupts.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import pythinker_code.telemetry.otel as otel_mod


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(otel_mod, "_tracer", provider.get_tracer("test"))
    yield exporter


def _by_name(exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    return {s.name: s for s in exporter.get_finished_spans()}


def test_child_span_nests_under_parent(span_exporter: InMemorySpanExporter) -> None:
    with otel_mod.start_span("parent"), otel_mod.start_span("child"):
        pass

    spans = _by_name(span_exporter)
    parent = spans["parent"]
    child = spans["child"]
    assert child.parent is not None, "child span should not be a flat root"
    assert parent.context is not None and child.context is not None
    assert child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id


def test_sibling_spans_share_no_parent(span_exporter: InMemorySpanExporter) -> None:
    # Two independent top-level spans must not accidentally nest into each other.
    with otel_mod.start_span("first"):
        pass
    with otel_mod.start_span("second"):
        pass
    spans = _by_name(span_exporter)
    assert spans["first"].parent is None
    assert spans["second"].parent is None


def test_start_span_records_gen_ai_attribute(span_exporter: InMemorySpanExporter) -> None:
    with otel_mod.start_span("pythinker.tool", {"gen_ai.operation.name": "execute_tool"}):
        pass
    span = span_exporter.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["gen_ai.operation.name"] == "execute_tool"


def test_exception_in_span_still_detaches_context(span_exporter: InMemorySpanExporter) -> None:
    # A raising body must record the error AND restore context so later spans
    # do not stay nested under the dead one.
    with pytest.raises(RuntimeError), otel_mod.start_span("boom"):
        raise RuntimeError("kaboom")
    with otel_mod.start_span("after"):
        pass
    assert _by_name(span_exporter)["after"].parent is None


def test_cancellation_in_span_detaches_context(span_exporter: InMemorySpanExporter) -> None:
    # CancelledError is a BaseException (not Exception); the context must still
    # detach so a Ctrl-C mid-span does not strand the token for later spans.
    import asyncio

    with pytest.raises(asyncio.CancelledError), otel_mod.start_span("cancelled"):
        raise asyncio.CancelledError()
    with otel_mod.start_span("after"):
        pass
    assert _by_name(span_exporter)["after"].parent is None
