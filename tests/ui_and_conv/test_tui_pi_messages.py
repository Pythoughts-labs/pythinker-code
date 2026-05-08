"""Smoke tests for the Pi-style message components."""

from __future__ import annotations

from pythinker_code.ui.shell.components import (
    AssistantContent,
    CustomMessageInput,
    render_assistant_message,
    render_custom_message,
    render_plain,
    render_user_message,
)


def test_render_user_message_includes_text():
    out = render_plain(render_user_message("Hello, world!"), width=40)
    assert "Hello, world!" in out


def test_render_assistant_message_text_only():
    rendered = render_assistant_message([AssistantContent(kind="text", text="The plan is...")])
    assert rendered is not None
    out = render_plain(rendered, width=40)
    assert "The plan" in out


def test_render_assistant_message_thinking_visible():
    rendered = render_assistant_message(
        [
            AssistantContent(kind="thinking", text="Considering the options"),
            AssistantContent(kind="text", text="Final answer"),
        ]
    )
    assert rendered is not None
    out = render_plain(rendered, width=60)
    assert "Considering the options" in out
    assert "Final answer" in out


def test_render_assistant_message_thinking_hidden_shows_label():
    rendered = render_assistant_message(
        [AssistantContent(kind="thinking", text="hidden thoughts")],
        hide_thinking=True,
        hidden_thinking_label="Thinking...",
    )
    assert rendered is not None
    out = render_plain(rendered, width=40)
    assert "Thinking..." in out
    assert "hidden thoughts" not in out


def test_render_assistant_message_returns_none_when_empty():
    rendered = render_assistant_message([AssistantContent(kind="text", text="   ")])
    assert rendered is None


def test_render_assistant_message_aborted_shows_error_line():
    rendered = render_assistant_message(
        [AssistantContent(kind="text", text="partial")],
        stop_reason="aborted",
        error_message="Request was aborted",
    )
    assert rendered is not None
    out = render_plain(rendered, width=40)
    assert "Operation aborted" in out


def test_render_custom_message_includes_label_and_body():
    msg = CustomMessageInput(custom_type="skill", text="ran /verify successfully")
    out = render_plain(render_custom_message(msg), width=60)
    assert "[skill]" in out
    assert "ran /verify successfully" in out
