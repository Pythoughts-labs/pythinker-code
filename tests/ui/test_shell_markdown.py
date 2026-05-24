from rich.console import Console

from pythinker_code.ui.shell.components.markdown import PythinkerMarkdown, PythinkerMarkdownStream
from pythinker_code.ui.shell.components.special_messages import (
    SkillInvocationInput,
    render_skill_invocation,
)


def _render_text(renderable: object, *, width: int = 72) -> str:
    console = Console(width=width, record=True, color_system=None)
    console.print(renderable)
    return console.export_text()


def test_shell_markdown_uses_pythinker_code_block_frame() -> None:
    output = _render_text(
        PythinkerMarkdown(
            "## Example\n\n```python\ndef review_target() -> str:\n    return 'ok'\n```\n"
        )
    )

    assert "python" in output
    assert "def review_target" in output
    assert "╭" in output
    assert "╰" in output


def test_shell_markdown_keeps_rich_fork_table_records() -> None:
    output = _render_text(
        PythinkerMarkdown(
            "| Area | Issue | Why it matters | Suggested improvement | Priority | Effort |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| Accessibility | Search input relies on placeholder text only. | "
            "Placeholder-only labels are weak for screen readers. | Add an aria-label. | "
            "High | XS |\n"
        )
    )

    assert "1. Accessibility" in output
    assert "Issue:" in output
    assert "Why it matters:" in output
    assert "Suggested improvement:" in output
    assert "Priority: High" in output
    assert "Effort: XS" in output


def test_markdown_stream_uses_parser_backed_block_boundaries() -> None:
    stream = PythinkerMarkdownStream()

    first = stream.push("Before.\n\n| A | B |\n|---|---|\n")
    ready = stream.push("| 1 | 2 |\n\nAfter.")

    assert first is not None
    assert "Before." in first
    assert "| A | B |" not in first
    assert ready is not None
    assert "| 1 | 2 |" in ready
    assert "After." not in ready


def test_markdown_stream_does_not_flush_incomplete_fence() -> None:
    stream = PythinkerMarkdownStream()

    assert stream.push("```python\nprint(1)\n") is None


def test_markdown_stream_flushes_single_line_sentence() -> None:
    stream = PythinkerMarkdownStream()

    assert stream.push("A short sentence.") == "A short sentence."


def test_expanded_special_messages_use_shell_markdown_renderer() -> None:
    output = _render_text(
        render_skill_invocation(
            SkillInvocationInput("demo", "```python\nprint('themed')\n```"),
            expanded=True,
        )
    )

    assert "[skill]" in output
    assert "python" in output
    assert "print('themed')" in output
    assert "╭" in output
    assert "╰" in output


def test_h2_has_heading_color_like_other_headings():
    """Regression: markdown.h2 previously had no color, unlike h1/h3/h4."""
    from pythinker_code.ui.shell.components.markdown import _markdown_style_overrides

    overrides = _markdown_style_overrides()
    assert overrides["markdown.h2"].color is not None
    assert overrides["markdown.h2"].color == overrides["markdown.h1"].color


def test_link_url_is_dimmed_relative_to_link_text():
    """The bracketed URL reads as secondary to the link text."""
    from pythinker_code.ui.shell.components.markdown import _markdown_style_overrides

    overrides = _markdown_style_overrides()
    assert overrides["markdown.link_url"].dim is True
    assert not overrides["markdown.link"].dim
