"""Child-agent token/cost roll-up helpers (subagent-2).

A fan-out of N subagents (or an explore -> plan -> implement -> review chain) can
spend 10-15x a single turn, but that spend was invisible to the orchestrating
parent model until the provider bill landed. These helpers surface each child's
cumulative LLM usage in the tool-result envelope (and a batch total for
RunAgents), giving the orchestrator the in-context signal it needs to budget
effort. They reuse the existing pricing table rather than re-implementing cost
math, and never raise — cost degrades to omitted when a model is unpriced.
"""

from __future__ import annotations

from collections.abc import Iterable

from pythinker_core.chat_provider import TokenUsage
from pythinker_core.tooling import ToolReturnValue
from pythinker_core.utils.typing import JsonType

# Keys used to carry structured per-child spend on a ToolReturnValue.extras so
# RunAgents can aggregate without parsing the text envelope.
EXTRA_INPUT_TOKENS = "child_input_tokens"
EXTRA_OUTPUT_TOKENS = "child_output_tokens"
EXTRA_COST_USD = "child_cost_usd"


def accumulate_usage(running: TokenUsage, new: TokenUsage) -> TokenUsage:
    """Return the field-wise sum of two ``TokenUsage`` records."""
    return TokenUsage(
        input_other=running.input_other + new.input_other,
        output=running.output + new.output,
        input_cache_read=running.input_cache_read + new.input_cache_read,
        input_cache_creation=running.input_cache_creation + new.input_cache_creation,
    )


def estimate_cost_usd(usage: TokenUsage, model: str) -> float:
    """Best-effort USD cost for *usage* at *model* pricing; 0.0 if unpriced/unknown."""
    try:
        from pythinker_code.ui.shell.stats_pricing import get_cost_usd

        return get_cost_usd(model, usage)
    except Exception as exc:
        from pythinker_code.utils.logging import logger

        logger.debug(
            "Child cost estimation failed for model {model}: {error}", model=model, error=exc
        )
        return 0.0


def format_usage_lines(prefix: str, usage: TokenUsage, model: str) -> list[str]:
    """Render ``<prefix>_tokens`` (+ optional ``<prefix>_cost_usd``) envelope lines."""
    lines = [f"{prefix}_tokens: {usage.input} in / {usage.output} out"]
    cost = estimate_cost_usd(usage, model)
    if cost > 0:
        lines.append(f"{prefix}_cost_usd: {cost:.4f}")
    return lines


def usage_extras(usage: TokenUsage, model: str) -> dict[str, JsonType]:
    """Structured per-child spend for ``ToolReturnValue.extras``."""
    return {
        EXTRA_INPUT_TOKENS: usage.input,
        EXTRA_OUTPUT_TOKENS: usage.output,
        EXTRA_COST_USD: estimate_cost_usd(usage, model),
    }


def _as_number(value: JsonType | None) -> float:
    """Coerce a JSON extras value to a number, treating non-numbers as 0.0."""
    if isinstance(value, bool):  # bool is an int subclass; a bool count is nonsense
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def summarize_batch(results: Iterable[ToolReturnValue]) -> list[str]:
    """Sum child spend from each result's extras into ``total_child_*`` lines.

    Returns ``[]`` when no child reported usage, so the batch line only appears
    when there is something to total.
    """
    total_in = 0
    total_out = 0
    total_cost = 0.0
    seen = False
    for result in results:
        extras = result.extras or {}
        if EXTRA_INPUT_TOKENS not in extras and EXTRA_OUTPUT_TOKENS not in extras:
            continue
        seen = True
        total_in += int(_as_number(extras.get(EXTRA_INPUT_TOKENS)))
        total_out += int(_as_number(extras.get(EXTRA_OUTPUT_TOKENS)))
        total_cost += _as_number(extras.get(EXTRA_COST_USD))
    if not seen:
        return []
    lines = [f"total_child_tokens: {total_in} in / {total_out} out"]
    if total_cost > 0:
        lines.append(f"total_child_cost_usd: {total_cost:.4f}")
    return lines


# ---------------------------------------------------------------------------
# Batch findings roll-up
# ---------------------------------------------------------------------------

_FINDING_SECTIONS = ("RISKS", "BLOCKERS")
_NONE_PLACEHOLDERS = frozenset({"none", "none.", "n/a", "-", "(none)"})


def _extract_section(output: str, section: str) -> list[str]:
    """Collect non-empty content lines under a ``### <section>`` style header."""
    collected: list[str] = []
    in_section = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        header = line.lstrip("#").strip().upper()
        if line.startswith("#"):
            in_section = header == section
            continue
        if not in_section or not line:
            continue
        if line.lower() in _NONE_PLACEHOLDERS:
            continue
        collected.append(line.lstrip("-*").strip())
    return collected


def aggregate_findings(named_outputs: Iterable[tuple[str, str]]) -> list[str]:
    """Roll RISKS/BLOCKERS sections from child reports into one envelope block.

    Children follow the structured report contract (### SUMMARY / EVIDENCE /
    CHANGES / RISKS / BLOCKERS). Free-text children simply contribute nothing;
    identical findings raised by several children are listed once with every
    reporter attributed. Returns [] when no child raised anything.
    """
    findings: dict[str, dict[str, list[str]]] = {section: {} for section in _FINDING_SECTIONS}
    for name, output in named_outputs:
        for section in _FINDING_SECTIONS:
            for finding in _extract_section(output, section):
                findings[section].setdefault(finding, []).append(name)
    lines: list[str] = []
    for section in _FINDING_SECTIONS:
        if not findings[section]:
            continue
        lines.append(f"batch_{section.lower()}:")
        for finding, reporters in findings[section].items():
            lines.append(f"- {finding} [{', '.join(reporters)}]")
    return lines
