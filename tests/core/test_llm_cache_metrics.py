"""obs-eval-2 backfill: prompt-cache token usage must reach the metric backend.

Pythinker freezes the system prompt per session to maximize prompt-cache hits, yet
without a server-side counter a regression that silently breaks cache-keying (a stable
prompt becoming non-stable) is invisible except as an aggregate cost spike. These tests
lock the cache_read / cache_creation counters to ``record_llm_call`` so the telemetry
signal cannot be dropped without a failing test.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry import metrics as _otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint

from pythinker_code.telemetry import metrics

_CACHE_READ = "pythinker.llm.cache_read_tokens"
_CACHE_CREATION = "pythinker.llm.cache_creation_tokens"


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    """Bind the module instruments to an isolated in-memory meter for one test."""
    rdr = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[rdr])
    metrics.bind(provider.get_meter("pythinker-code-test"))
    try:
        yield rdr
    finally:
        # Restore the (no-op in tests) global meter so instruments don't leak.
        metrics.bind(_otel_metrics.get_meter("pythinker-code"))


def _counter_total(rdr: InMemoryMetricReader, name: str) -> float | None:
    """Sum all data points for a counter, or None if it was never recorded."""
    data = rdr.get_metrics_data()
    if data is None:
        return None
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return sum(
                        point.value
                        for point in metric.data.data_points
                        if isinstance(point, NumberDataPoint)
                    )
    return None


def test_cache_read_tokens_reach_the_counter(reader: InMemoryMetricReader) -> None:
    metrics.record_llm_call(
        duration_seconds=0.1,
        system="anthropic",
        model="claude",
        cache_read_tokens=100,
    )
    assert _counter_total(reader, _CACHE_READ) == 100


def test_cache_creation_tokens_reach_the_counter(reader: InMemoryMetricReader) -> None:
    metrics.record_llm_call(
        duration_seconds=0.1,
        system="anthropic",
        model="claude",
        cache_creation_tokens=50,
    )
    assert _counter_total(reader, _CACHE_CREATION) == 50


def test_zero_and_missing_cache_tokens_are_not_recorded(reader: InMemoryMetricReader) -> None:
    # The ``> 0`` guard keeps empty/absent cache usage from polluting the series.
    metrics.record_llm_call(
        duration_seconds=0.1,
        system="anthropic",
        model="claude",
        cache_read_tokens=0,
    )
    assert _counter_total(reader, _CACHE_READ) is None
    assert _counter_total(reader, _CACHE_CREATION) is None
