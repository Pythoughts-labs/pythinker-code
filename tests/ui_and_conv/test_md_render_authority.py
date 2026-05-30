# tests/ui_and_conv/test_md_render_authority.py
"""Screen-authority discipline (spec principle 1) for the lead-phase modules.

These renderers must return Rich renderables, never write to the terminal
directly. A bare print()/sys.stdout.write in a renderer bypasses the Live
screen model and causes the duplicate-scrollback / corruption bug classes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = (
    Path(__file__).resolve().parents[2] / "src" / "pythinker_code" / "ui" / "shell" / "components"
)
_GUARDED = ["report.py", "markdown.py"]


@pytest.mark.parametrize("filename", _GUARDED)
def test_no_direct_terminal_writes_in_renderer(filename):
    tree = ast.parse((_SRC / filename).read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                offenders.append(f"print() at line {node.lineno}")
            if isinstance(func, ast.Attribute) and func.attr == "write":
                target = func.value
                is_std_stream = (
                    isinstance(target, ast.Attribute) and target.attr in {"stdout", "stderr"}
                ) or (isinstance(target, ast.Name) and target.id in {"stdout", "stderr"})
                if is_std_stream:
                    offenders.append(f"std*.write at line {node.lineno}")
    assert not offenders, f"{filename} bypasses the screen model: {offenders}"
