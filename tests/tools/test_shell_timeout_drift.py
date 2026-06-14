"""Drift guards for the Shell tool description's timeout caps.

The model-facing description must state the foreground/background timeout caps
using the same ``MAX_FOREGROUND_TIMEOUT`` / ``MAX_BACKGROUND_TIMEOUT`` constants
that ``Params`` enforces, so the description can never silently drift from the
validator.
"""

from __future__ import annotations

from pathlib import Path

import pythinker_code.tools.shell as shell_mod
from pythinker_code.tools.utils import load_desc

_SHELL_DIR = Path(shell_mod.__file__).parent


def _render(md_name: str) -> str:
    # Render with sentinel values distinct from the real constants so a hardcoded
    # literal left in the markdown is detectable.
    return load_desc(
        _SHELL_DIR / md_name,
        {"SHELL": "test-shell", "MAX_FOREGROUND_TIMEOUT": 777, "MAX_BACKGROUND_TIMEOUT": 888},
    )


def test_bash_md_interpolates_timeout_caps() -> None:
    rendered = _render("bash.md")
    assert "timeout <= 777" in rendered
    assert "more than 777 seconds" in rendered
    assert "up to 888 seconds" in rendered
    # No hardcoded literal survived the interpolation.
    assert "300" not in rendered
    assert "86400" not in rendered


def test_powershell_md_interpolates_timeout_caps() -> None:
    rendered = _render("powershell.md")
    assert "timeout <= 777" in rendered
    assert "more than 777 seconds" in rendered
    assert "up to 888 seconds" in rendered
    assert "300" not in rendered
    assert "86400" not in rendered


def test_shell_tool_description_states_enforced_caps(shell_tool: shell_mod.Shell) -> None:
    """The live description the model sees states the enforced caps as numbers,
    never a raw ``${...}`` placeholder — guards the call site passing the constants."""
    desc = shell_tool.description
    assert f"timeout <= {shell_mod.MAX_FOREGROUND_TIMEOUT}" in desc
    assert f"up to {shell_mod.MAX_BACKGROUND_TIMEOUT} seconds" in desc
    assert "${MAX_FOREGROUND_TIMEOUT}" not in desc
    assert "${MAX_BACKGROUND_TIMEOUT}" not in desc
