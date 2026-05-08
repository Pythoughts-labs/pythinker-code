"""Tests for the Pythinker tool renderer registry."""

from __future__ import annotations

import pytest
from rich.text import Text

from pythinker_code.ui.shell.components import render_plain
from pythinker_code.ui.shell.tool_renderers import (
    ToolRenderContext,
    ToolRenderDefinition,
    ToolResultPayload,
    clear_tool_renderers,
    get_tool_renderer,
    register_builtin_renderers,
    register_tool_renderer,
    registered_tool_names,
)
from pythinker_code.ui.shell.tool_renderers.generic import (
    GENERIC_RENDERER,
    generic_renderer,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Each test starts with an empty registry and tears down after."""
    clear_tool_renderers()
    yield
    clear_tool_renderers()


# ---------------------------------------------------------------------------
# register / get / clear
# ---------------------------------------------------------------------------


def test_register_and_lookup():
    defn = ToolRenderDefinition(name="MyTool", label="MyTool")
    register_tool_renderer(defn)
    assert get_tool_renderer("MyTool") is defn


def test_lookup_unknown_returns_none():
    assert get_tool_renderer("UnknownTool") is None


def test_register_overwrites_existing():
    register_tool_renderer(ToolRenderDefinition(name="X", label="A"))
    register_tool_renderer(ToolRenderDefinition(name="X", label="B"))
    found = get_tool_renderer("X")
    assert found is not None
    assert found.label == "B"


def test_registered_tool_names_snapshot():
    register_tool_renderer(ToolRenderDefinition(name="A", label="A"))
    register_tool_renderer(ToolRenderDefinition(name="B", label="B"))
    names = registered_tool_names()
    assert set(names) == {"A", "B"}


# ---------------------------------------------------------------------------
# ToolRenderContext defaults
# ---------------------------------------------------------------------------


def test_context_defaults():
    ctx = ToolRenderContext(args={"foo": 1}, tool_call_id="t1")
    assert ctx.cwd == ""
    assert ctx.execution_started is False
    assert ctx.args_complete is False
    assert ctx.is_partial is False
    assert ctx.expanded is False
    assert ctx.is_error is False
    assert ctx.state == {}


def test_context_state_is_per_instance():
    a = ToolRenderContext(args={}, tool_call_id="a")
    b = ToolRenderContext(args={}, tool_call_id="b")
    a.state["x"] = 1
    assert "x" not in b.state


def test_render_definition_is_frozen():
    defn = ToolRenderDefinition(name="X", label="X")
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass error type varies
        defn.label = "Y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Built-in (generic) renderer
# ---------------------------------------------------------------------------


def test_register_builtin_registers_generic():
    register_builtin_renderers()
    assert get_tool_renderer("__generic__") is GENERIC_RENDERER


def test_generic_render_call_with_args():
    ctx = ToolRenderContext(args={"path": "src/foo.py"}, tool_call_id="t1")
    ctx.state["__tool_name__"] = "ReadFile"
    assert GENERIC_RENDERER.render_call is not None
    out = GENERIC_RENDERER.render_call(ctx)
    assert out is not None
    rendered = render_plain(out, width=60)
    assert "ReadFile" in rendered
    assert "src/foo.py" in rendered


def test_generic_render_call_without_args():
    ctx = ToolRenderContext(args={}, tool_call_id="t1")
    ctx.state["__tool_name__"] = "Bare"
    assert GENERIC_RENDERER.render_call is not None
    out = GENERIC_RENDERER.render_call(ctx)
    assert out is not None
    rendered = render_plain(out, width=20)
    assert "Bare" in rendered


def test_generic_render_result_with_text():
    ctx = ToolRenderContext(args={}, tool_call_id="t1")
    payload = ToolResultPayload(text="hello world", is_error=False)
    assert GENERIC_RENDERER.render_result is not None
    out = GENERIC_RENDERER.render_result(ctx, payload)
    assert out is not None
    assert "hello world" in render_plain(out, width=40)


def test_generic_render_result_strips_ansi():
    ctx = ToolRenderContext(args={}, tool_call_id="t1")
    payload = ToolResultPayload(text="\x1b[31mred\x1b[0m text")
    assert GENERIC_RENDERER.render_result is not None
    out = GENERIC_RENDERER.render_result(ctx, payload)
    assert out is not None
    assert "red text" in render_plain(out, width=40)


def test_generic_render_result_empty_returns_none():
    ctx = ToolRenderContext(args={}, tool_call_id="t1")
    payload = ToolResultPayload(text="", is_error=False)
    assert GENERIC_RENDERER.render_result is not None
    assert GENERIC_RENDERER.render_result(ctx, payload) is None


def test_generic_render_result_handles_unjsonable_args():
    # Ensures render_call doesn't raise on non-JSON-serializable args.
    class Sentinel:
        def __repr__(self) -> str:
            return "<sentinel>"

    ctx = ToolRenderContext(args={"obj": Sentinel()}, tool_call_id="t1")  # type: ignore[dict-item]
    ctx.state["__tool_name__"] = "X"
    assert GENERIC_RENDERER.render_call is not None
    out = GENERIC_RENDERER.render_call(ctx)
    assert out is not None
    rendered = render_plain(out, width=40)
    assert "<sentinel>" in rendered


def test_generic_renderer_function_returns_singleton():
    assert generic_renderer() is GENERIC_RENDERER


# ---------------------------------------------------------------------------
# Renderer can be a closure with custom logic
# ---------------------------------------------------------------------------


def test_custom_renderer_can_be_registered():
    def render_call(ctx: ToolRenderContext):
        return Text(f"called with {ctx.args.get('q', '?')}")

    register_tool_renderer(
        ToolRenderDefinition(
            name="Search",
            label="Search",
            render_call=render_call,
        )
    )
    found = get_tool_renderer("Search")
    assert found is not None
    assert found.render_call is not None
    out = found.render_call(ToolRenderContext(args={"q": "foo"}, tool_call_id="t1"))
    assert out is not None
    assert "called with foo" in render_plain(out, width=40)
