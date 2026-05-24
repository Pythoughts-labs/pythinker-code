from __future__ import annotations

from rich.console import Console

from pythinker_code.ui.shell.tool_renderers import ToolRenderContext, ToolResultPayload
from pythinker_code.ui.shell.tool_renderers.generic import (
    _GENERIC_COLLAPSED_LINES,
    _render_result,
)


def _render(renderable) -> str:
    console = Console(width=80, record=True, highlight=False)
    console.print(renderable)
    return console.export_text()


_BIG = "\n".join(f"line {i}" for i in range(200))


def test_generic_result_collapses_large_output():
    """A huge unregistered-tool result (e.g. a Skill payload) must not dump in full."""
    ctx = ToolRenderContext(tool_call_id="t1", args={}, expanded=False, state={})
    out = _render(_render_result(ctx, ToolResultPayload(text=_BIG, is_error=False)))
    nonempty = [line for line in out.splitlines() if line.strip()]
    # Capped body + one expand-hint line.
    assert len(nonempty) <= _GENERIC_COLLAPSED_LINES + 1
    assert "to expand" in out
    # Renderer owns the hint, so the duplicate generic hint is suppressed.
    assert ctx.state.get("__suppress_generic_expand_hint__") is True


def test_generic_result_expanded_shows_everything():
    ctx = ToolRenderContext(tool_call_id="t2", args={}, expanded=True, state={})
    out = _render(_render_result(ctx, ToolResultPayload(text=_BIG, is_error=False)))
    assert "line 199" in out


def test_generic_result_short_output_no_hint():
    ctx = ToolRenderContext(tool_call_id="t3", args={}, expanded=False, state={})
    out = _render(_render_result(ctx, ToolResultPayload(text="just one line", is_error=False)))
    assert "to expand" not in out
    assert ctx.state.get("__suppress_generic_expand_hint__") is not True
