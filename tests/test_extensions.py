"""Tests for the in-process extension API."""

from __future__ import annotations

import pytest

from pythinker_code.extensions import (
    ExtensionContext,
    footer_statuses,
    register_extension,
    registered_extensions,
    run_pending_extensions,
    shared_event_bus,
)
from pythinker_code.ui.shell.keymap import all_keybindings, key_text, register_keybinding
from pythinker_code.ui.shell.tool_renderers import (
    ToolRenderDefinition,
    clear_tool_renderers,
    get_tool_renderer,
)


@pytest.fixture(autouse=True)
def _clean_state():
    # Reset everything between tests.
    clear_tool_renderers()
    keymap_snapshot = all_keybindings()
    fs = dict(footer_statuses())
    bus = shared_event_bus()
    yield
    clear_tool_renderers()
    bus.clear()
    for k in list(footer_statuses()):
        # Use the public API to clear; ExtensionContext.register_footer_status
        # with empty text removes.
        ExtensionContext(name="cleanup").register_footer_status(k, "")
    for k, v in fs.items():
        ExtensionContext(name="restore").register_footer_status(k, v)
    for name, keys in keymap_snapshot.items():
        register_keybinding(name, *keys)


def test_register_extension_runs_setup_and_records_name():
    seen = {}

    def setup(ctx: ExtensionContext) -> None:
        seen["name"] = ctx.name

    register_extension(name="test-ext", setup=setup)
    started = run_pending_extensions()
    assert started == ["test-ext"]
    assert seen == {"name": "test-ext"}
    assert "test-ext" in registered_extensions()


def test_extension_can_register_tool_renderer():
    def setup(ctx: ExtensionContext) -> None:
        ctx.register_tool_renderer(ToolRenderDefinition(name="MyTool", label="MyTool"))

    register_extension(name="custom", setup=setup)
    run_pending_extensions()
    assert get_tool_renderer("MyTool") is not None


def test_extension_can_register_keybinding_and_footer():
    def setup(ctx: ExtensionContext) -> None:
        ctx.register_keybinding("app.custom.action", "ctrl+m")
        ctx.register_footer_status("custom", "ok")

    register_extension(name="custom", setup=setup)
    run_pending_extensions()
    assert key_text("app.custom.action") == "ctrl+m"
    assert footer_statuses()["custom"] == "ok"


def test_extension_event_handler_subscribes_to_shared_bus():
    received: list[str] = []

    def setup(ctx: ExtensionContext) -> None:
        ctx.register_event_handler("ping", received.append)

    register_extension(name="custom", setup=setup)
    run_pending_extensions()
    shared_event_bus().emit("ping", "hello")
    assert received == ["hello"]


def test_setup_failure_does_not_break_other_extensions():
    received: list[str] = []

    def bad(_ctx: ExtensionContext) -> None:
        raise RuntimeError("boom")

    def good(_ctx: ExtensionContext) -> None:
        received.append("ran")

    register_extension(name="bad", setup=bad)
    register_extension(name="good", setup=good)
    started = run_pending_extensions()
    assert started == ["good"]
    assert received == ["ran"]


def test_register_footer_status_with_empty_text_clears():
    ExtensionContext(name="x").register_footer_status("custom", "ok")
    assert "custom" in footer_statuses()
    ExtensionContext(name="x").register_footer_status("custom", "")
    assert "custom" not in footer_statuses()
