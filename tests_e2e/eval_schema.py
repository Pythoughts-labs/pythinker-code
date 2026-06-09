"""Versioned eval-case schema + efficiency scoring (obs-eval-4, offline core).

Behavioral evals answer "did the task pass?" but never "did the agent take a sane,
efficient path?". A prompt or tool-description change could double the tool calls,
blow up tokens, or pick the wrong subagent while still passing the smoke reward.

This module is the offline-testable core of obs-eval-4:
  * ``EvalCase`` — a versioned scenario (query + expected tool trajectory + reference
    outcome + per-scenario efficiency budgets).
  * ``ObservedMetrics`` — the efficiency triple the agent loop already emits as OTel
    metrics (tool calls, tokens, tool errors, step count, tools used).
  * ``score_eval_case`` — compares observed vs budget and the expected trajectory.
  * ``observed_from_metric_reader`` — reads the metrics back out of an in-process
    OTel ``InMemoryMetricReader``, the zero-extra-plumbing tap the gap calls for.

Deferred (the live-run slice): wiring this per-scenario into the scripted-echo e2e
suite and extending the accuracy_smoke / Harbor ``result.json`` parser — those need
a real run and a curated corpus; the schema + scorer here are their foundation.
"""

from __future__ import annotations

from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
    NumberDataPoint,
)
from pydantic import BaseModel, Field

EVAL_CASE_SCHEMA_VERSION = 1


class EfficiencyBudget(BaseModel):
    """Per-scenario ceilings; ``None`` means "do not gate on this metric"."""

    max_tool_calls: int | None = None
    max_total_tokens: int | None = None
    max_tool_errors: int | None = None
    max_steps: int | None = None


class EvalCase(BaseModel):
    """A versioned behavioral eval scenario."""

    schema_version: int = EVAL_CASE_SCHEMA_VERSION
    name: str
    query: str
    expected_tools: tuple[str, ...] = ()
    """Trajectory hint: tools the agent is expected to use (subset, order-agnostic)."""
    reference_outcome: str = ""
    budget: EfficiencyBudget = Field(default_factory=EfficiencyBudget)


class ObservedMetrics(BaseModel):
    """The efficiency triple observed for one scenario run."""

    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_errors: int = 0
    step_count: int = 0
    tools_used: tuple[str, ...] = ()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BudgetBreach(BaseModel):
    metric: str
    budget: int
    observed: int


class EvalVerdict(BaseModel):
    name: str
    passed: bool
    breaches: list[BudgetBreach] = Field(default_factory=list)
    missing_expected_tools: tuple[str, ...] = ()


def score_eval_case(case: EvalCase, observed: ObservedMetrics) -> EvalVerdict:
    """Score a scenario: within every set budget AND used every expected tool."""
    breaches: list[BudgetBreach] = []

    def _check(metric: str, budget: int | None, value: int) -> None:
        if budget is not None and value > budget:
            breaches.append(BudgetBreach(metric=metric, budget=budget, observed=value))

    _check("tool_calls", case.budget.max_tool_calls, observed.tool_calls)
    _check("total_tokens", case.budget.max_total_tokens, observed.total_tokens)
    _check("tool_errors", case.budget.max_tool_errors, observed.tool_errors)
    _check("step_count", case.budget.max_steps, observed.step_count)

    used = set(observed.tools_used)
    missing = tuple(tool for tool in case.expected_tools if tool not in used)
    return EvalVerdict(
        name=case.name,
        passed=not breaches and not missing,
        breaches=breaches,
        missing_expected_tools=missing,
    )


def _counter_total(reader: InMemoryMetricReader, name: str) -> int:
    data = reader.get_metrics_data()
    if data is None:
        return 0
    total = 0
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    if isinstance(point, NumberDataPoint):
                        total += int(point.value)
    return total


def _histogram_sum(reader: InMemoryMetricReader, name: str) -> int:
    data = reader.get_metrics_data()
    if data is None:
        return 0
    total = 0
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    if isinstance(point, HistogramDataPoint):
                        total += int(point.sum)
    return total


def observed_from_metric_reader(
    reader: InMemoryMetricReader, *, tools_used: tuple[str, ...] = ()
) -> ObservedMetrics:
    """Read the efficiency triple out of an in-process OTel metric reader.

    ``tools_used`` (the trajectory) is passed in by the harness since tool names
    live on metric attributes; everything else comes straight from the instruments
    the agent loop already records.
    """
    return ObservedMetrics(
        tool_calls=_counter_total(reader, "pythinker.tool.calls_total"),
        input_tokens=_counter_total(reader, "pythinker.llm.input_tokens"),
        output_tokens=_counter_total(reader, "pythinker.llm.output_tokens"),
        tool_errors=_counter_total(reader, "pythinker.errors_total"),
        step_count=_histogram_sum(reader, "pythinker.turn.step_count"),
        tools_used=tools_used,
    )
