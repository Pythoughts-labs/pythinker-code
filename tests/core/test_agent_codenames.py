"""Unit tests for subagent instance codename generation."""

from __future__ import annotations

from pythinker_code.subagents.codenames import (
    _ADJECTIVES,
    _NOUNS,
    generate_codename,
    is_generic_agent_name,
)


def test_generate_codename_shape_and_charset() -> None:
    codename = generate_codename()
    adjective, sep, noun = codename.partition("-")
    assert sep == "-"
    assert adjective in _ADJECTIVES
    assert noun in _NOUNS


def test_generate_codename_avoids_used_names() -> None:
    used: set[str] = set()
    for _ in range(50):
        codename = generate_codename(used)
        assert codename.lower() not in used
        used.add(codename.lower())


def test_generate_codename_exhaustion_falls_back_to_suffix() -> None:
    """When every combination is taken, a numeric suffix still yields a unique name."""
    all_names = {f"{a}-{n}" for a in _ADJECTIVES for n in _NOUNS}
    codename = generate_codename(all_names)
    assert codename not in all_names
    assert codename.rsplit("-", 1)[1].isdigit()


def test_is_generic_agent_name() -> None:
    # Generic: empty, role fillers, the type itself (any separator style/case).
    assert is_generic_agent_name("", "explore")
    assert is_generic_agent_name("agent", "explore")
    assert is_generic_agent_name("explore", "explore")
    assert is_generic_agent_name("Code Reviewer", "code-reviewer")
    assert is_generic_agent_name("code_reviewer", "code-reviewer")
    # Distinctive caller names are kept.
    assert not is_generic_agent_name("api-scout", "explore")
    assert not is_generic_agent_name("payments-auditor", "code-reviewer")
