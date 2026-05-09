"""Unit tests for Pythinker TUI component foundation."""

from __future__ import annotations

from rich.text import Text

from pythinker_code.ui.shell.components import (
    TuiComponent,
    cell_width,
    dim,
    key_hint,
    raw_key_hint,
    render_plain,
    sanitize_ansi,
    truncate_to_width,
)

# ---------------------------------------------------------------------------
# truncate_to_width
# ---------------------------------------------------------------------------


def test_truncate_to_width_no_change_when_fits():
    assert truncate_to_width("hello", 10) == "hello"


def test_truncate_to_width_adds_ellipsis():
    out = truncate_to_width("hello world", 8)
    assert cell_width(out) <= 8
    assert out.endswith("…")


def test_truncate_to_width_zero_returns_empty():
    assert truncate_to_width("hello", 0) == ""


def test_truncate_to_width_below_ellipsis_falls_back_to_plain():
    # max_width=1 cannot fit ellipsis (1 cell) + any chars; returns leading chars.
    out = truncate_to_width("hello", 1)
    assert cell_width(out) <= 1
    assert "…" not in out


def test_truncate_to_width_handles_cjk():
    # CJK chars are 2 cells each.
    out = truncate_to_width("中文测试", 5)
    # 5 cells minus 1 ellipsis = 4 cells = up to 2 CJK chars + ellipsis = 5.
    assert cell_width(out) <= 5


# ---------------------------------------------------------------------------
# cell_width
# ---------------------------------------------------------------------------


def test_cell_width_ascii():
    assert cell_width("hello") == 5


def test_cell_width_cjk_double_width():
    assert cell_width("中") == 2


# ---------------------------------------------------------------------------
# sanitize_ansi
# ---------------------------------------------------------------------------


def test_sanitize_ansi_strips_csi():
    raw = "\x1b[31mred\x1b[0m text"
    assert sanitize_ansi(raw) == "red text"


def test_sanitize_ansi_strips_osc_with_bel():
    raw = "before\x1b]0;title\x07after"
    assert sanitize_ansi(raw) == "beforeafter"


def test_sanitize_ansi_strips_osc_with_st():
    raw = "before\x1b]8;;https://example.com\x1b\\link\x1b]8;;\x1b\\after"
    cleaned = sanitize_ansi(raw)
    assert "https://example.com" not in cleaned
    assert "linkafter" in cleaned


def test_sanitize_ansi_keeps_newlines_tabs():
    raw = "line 1\n\tline 2"
    assert sanitize_ansi(raw) == "line 1\n\tline 2"


def test_sanitize_ansi_strips_control_bytes():
    raw = "ok\x01\x02\x7f"
    assert sanitize_ansi(raw) == "ok"


# ---------------------------------------------------------------------------
# dim
# ---------------------------------------------------------------------------


def test_dim_string():
    out = dim("muted")
    assert isinstance(out, Text)
    assert out.plain == "muted"


def test_dim_text_preserves_existing_content():
    src = Text("hello", style="bold")
    out = dim(src)
    assert out.plain == "hello"
    # Should not mutate the input.
    assert src.style == "bold"


# ---------------------------------------------------------------------------
# key hints
# ---------------------------------------------------------------------------


def test_raw_key_hint_concatenates_key_and_description():
    out = raw_key_hint("Ctrl+E", "expand")
    assert "Ctrl+E" in out.plain
    assert "expand" in out.plain


def test_key_hint_currently_aliases_raw():
    a = key_hint("Esc", "cancel")
    b = raw_key_hint("Esc", "cancel")
    assert a.plain == b.plain


# ---------------------------------------------------------------------------
# render_plain snapshot helper
# ---------------------------------------------------------------------------


def test_render_plain_strips_color():
    coloured = Text("hello", style="bold red")
    out = render_plain(coloured, width=20)
    assert "hello" in out
    # No ANSI escapes in snapshot output.
    assert "\x1b[" not in out


def test_render_plain_respects_width():
    long = Text("x" * 200)
    out = render_plain(long, width=40)
    # Rich wraps at width; first line should be exactly 40 chars.
    first_line = out.splitlines()[0]
    assert len(first_line) == 40


# ---------------------------------------------------------------------------
# TuiComponent protocol
# ---------------------------------------------------------------------------


def test_tui_component_protocol_runtime_check():
    class _Stub:
        def render(self, width: int):
            return Text("stub")

        def invalidate(self) -> None:
            pass

    assert isinstance(_Stub(), TuiComponent)


def test_tui_component_protocol_rejects_missing_methods():
    class _Bad:
        def render(self, width: int):
            return Text("nope")

    assert not isinstance(_Bad(), TuiComponent)
