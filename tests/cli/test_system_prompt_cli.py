"""Tests for `pythinker system-prompt` agent resolution."""

from __future__ import annotations

import pytest
import typer

from pythinker_code.agentspec import DEFAULT_AGENT_FILE
from pythinker_code.cli.system_prompt import _resolve_agent_file


def test_resolve_default_agent() -> None:
    assert _resolve_agent_file("default") == DEFAULT_AGENT_FILE


def test_resolve_builtin_role_agent() -> None:
    # Built-in role specs live alongside the default agent as default/<name>.yaml.
    resolved = _resolve_agent_file("coder")
    assert resolved == DEFAULT_AGENT_FILE.parent / "coder.yaml"
    assert resolved.exists()


def test_resolve_unknown_agent_raises() -> None:
    with pytest.raises(typer.BadParameter):
        _resolve_agent_file("does-not-exist-xyz")
