"""Smoke tests for the Pi-style footer component."""

from __future__ import annotations

from pythinker_code.ui.shell.components import (
    FooterState,
    FooterUsage,
    format_tokens,
    render_footer,
    render_plain,
)


def test_format_tokens_compact():
    assert format_tokens(42) == "42"
    assert format_tokens(1234) == "1.2k"
    assert format_tokens(15_000) == "15k"
    assert format_tokens(2_500_000) == "2.5M"


def test_render_footer_basic_two_lines():
    state = FooterState(
        cwd="/home/dev/proj",
        git_branch="main",
        usage=FooterUsage(input_tokens=12_000, output_tokens=3_400, cost_total=0.012),
        context_percent=42.5,
        context_window=200_000,
        model_id="claude-opus-4-7",
    )
    out = render_plain(render_footer(state, width=80), width=80)
    lines = [ln for ln in out.split("\n") if ln.strip()]
    assert any("(main)" in ln for ln in lines)
    assert any("↑12k" in ln for ln in lines)
    assert any("↓3.4k" in ln for ln in lines)
    assert any("$0.012" in ln for ln in lines)
    assert any("42.5%/200k" in ln for ln in lines)
    assert any("claude-opus-4-7" in ln for ln in lines)


def test_render_footer_extension_status_third_line():
    state = FooterState(
        cwd="/repo",
        extension_statuses={"linter": "ok", "deploy": "queued"},
    )
    out = render_plain(render_footer(state, width=60), width=60)
    lines = [ln for ln in out.split("\n") if ln.strip()]
    assert any("ok" in ln and "queued" in ln for ln in lines)


def test_render_footer_provider_only_when_room():
    state = FooterState(
        cwd="/repo",
        model_id="claude-opus-4-7",
        model_provider="anthropic",
        show_provider=True,
    )
    out = render_plain(render_footer(state, width=120), width=120)
    assert "(anthropic)" in out


def test_render_footer_session_name_appended():
    state = FooterState(cwd="/repo", git_branch="dev", session_name="auth refactor")
    out = render_plain(render_footer(state, width=80), width=80)
    assert "auth refactor" in out
    assert "(dev)" in out


def test_render_footer_unknown_context_shows_question_mark():
    state = FooterState(cwd="/repo", context_percent=None, context_window=200_000)
    out = render_plain(render_footer(state, width=80), width=80)
    assert "?/200k" in out
