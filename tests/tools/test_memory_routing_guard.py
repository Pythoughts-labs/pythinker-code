"""Tests for the memory routing guard's structural signal detector.

The detector is a pure, deterministic function: given an entry's content it
reports which structural signals suggest the entry may belong in an
authoritative project file rather than memory. It never blocks — the tool layer
only uses it to append an advisory — so the bar is "would a human glance and say
'that looks like a file edit'", not airtight classification.
"""

from __future__ import annotations

import pytest

from pythinker_code.tools.memory.routing_guard import routing_signals


@pytest.mark.parametrize(
    "content",
    [
        # The exact evasion case: a correction rephrased as a preference still
        # trips because "limit ... 100" is a value-assignment, not a plain fact.
        "user prefers a conclusion limit of 100",
        "set the conclusion word limit to 100",
        "change the max scholars to 4",
        "raise the threshold to 12",
    ],
)
def test_directive_grammar_trips(content: str) -> None:
    assert "directive" in routing_signals(content)


@pytest.mark.parametrize(
    "content",
    [
        "always cite at least two classical scholars",
        "never include a preamble in the conclusion",
        "the response must end with a citation",
    ],
)
def test_imperative_grammar_trips(content: str) -> None:
    assert "directive" in routing_signals(content)


@pytest.mark.parametrize(
    "content",
    [
        "POST_PROTOCOL.md governs the conclusion length",
        "limits live in config.yaml",
        "see AGENTS.md for the workflow rules",
    ],
)
def test_file_reference_trips(content: str) -> None:
    assert "file_ref" in routing_signals(content)


@pytest.mark.parametrize(
    "content",
    [
        "Project uses pytest with xdist",
        "User prefers concise answers",
        "The web and dashboard frontends are gitignored",
        "Sessions are stored under the share directory",
    ],
)
def test_plain_facts_are_quiet(content: str) -> None:
    assert routing_signals(content) == []


def test_legit_locational_fact_trips_file_ref_but_is_only_a_signal() -> None:
    """A genuine durable fact that names a file (this SHOULD be allowed to save —
    the tool only advises, never blocks) still reports the file_ref signal."""
    assert routing_signals("MCP servers load only from mcp.json") == ["file_ref"]


def test_signals_are_deduped_and_stable_order() -> None:
    """file_ref before directive; each reported at most once."""
    signals = routing_signals("update the limit to 100 in POST_PROTOCOL.md")
    assert signals == ["file_ref", "directive"]


def test_empty_content_is_quiet() -> None:
    assert routing_signals("") == []
