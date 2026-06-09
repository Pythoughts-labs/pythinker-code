"""obs-eval-4 (offline core): eval-case schema + efficiency scoring."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry import metrics as _otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from pythinker_code.telemetry import metrics
from tests_e2e.eval_schema import (
    EVAL_CASE_SCHEMA_VERSION,
    EfficiencyBudget,
    EvalCase,
    ObservedMetrics,
    observed_from_metric_reader,
    score_eval_case,
)


def _case(**budget: int) -> EvalCase:
    return EvalCase(
        name="search the codebase",
        query="find the auth module",
        expected_tools=("Grep", "ReadFile"),
        budget=EfficiencyBudget(**budget),
    )


def test_schema_is_versioned() -> None:
    assert EvalCase(name="x", query="y").schema_version == EVAL_CASE_SCHEMA_VERSION


def test_passes_within_budget_and_with_expected_tools() -> None:
    case = _case(max_tool_calls=5, max_total_tokens=1000)
    observed = ObservedMetrics(
        tool_calls=3, input_tokens=400, output_tokens=200, tools_used=("Grep", "ReadFile")
    )
    verdict = score_eval_case(case, observed)
    assert verdict.passed
    assert verdict.breaches == []
    assert verdict.missing_expected_tools == ()


def test_flags_budget_breach() -> None:
    case = _case(max_tool_calls=2, max_total_tokens=500)
    observed = ObservedMetrics(
        tool_calls=4, input_tokens=400, output_tokens=300, tools_used=("Grep", "ReadFile")
    )
    verdict = score_eval_case(case, observed)
    assert not verdict.passed
    metrics_breached = {b.metric for b in verdict.breaches}
    assert metrics_breached == {"tool_calls", "total_tokens"}


def test_flags_missing_expected_tool() -> None:
    case = _case(max_tool_calls=5)
    observed = ObservedMetrics(tool_calls=1, tools_used=("Grep",))  # ReadFile never used
    verdict = score_eval_case(case, observed)
    assert not verdict.passed
    assert verdict.missing_expected_tools == ("ReadFile",)


def test_none_budget_does_not_gate() -> None:
    case = _case()  # no budgets set
    observed = ObservedMetrics(tool_calls=999, input_tokens=10**6, tools_used=("Grep", "ReadFile"))
    assert score_eval_case(case, observed).passed


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    rdr = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[rdr])
    metrics.bind(provider.get_meter("eval-test"))
    try:
        yield rdr
    finally:
        metrics.bind(_otel_metrics.get_meter("pythinker-code"))


def test_observed_from_metric_reader_reads_the_efficiency_triple(
    reader: InMemoryMetricReader,
) -> None:
    metrics.record_tool_call(tool_name="Grep", duration_seconds=0.1, success=True)
    metrics.record_tool_call(tool_name="ReadFile", duration_seconds=0.1, success=True)
    metrics.record_llm_call(
        duration_seconds=0.2, system="anthropic", model="m", input_tokens=120, output_tokens=40
    )
    metrics.record_error(kind="tool_error", error_type="ValueError")
    metrics.record_turn(duration_seconds=1.0, step_count=3, stop_reason="no_tool_calls")

    observed = observed_from_metric_reader(reader, tools_used=("Grep", "ReadFile"))

    assert observed.tool_calls == 2
    assert observed.input_tokens == 120
    assert observed.output_tokens == 40
    assert observed.total_tokens == 160
    assert observed.tool_errors == 1
    assert observed.step_count == 3
    assert observed.tools_used == ("Grep", "ReadFile")
