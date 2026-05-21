from pythinker_review.engine.token_budget import clip_text


def test_clip_text_preserves_line_boundaries() -> None:
    text = "line1\nline2\nline3\nline4\nline5"
    clipped = clip_text(text, 24)
    assert clipped == "line1\n... [truncated]"


def test_clip_text_handles_tiny_budget() -> None:
    assert clip_text("abcdef", 3) == "\n.."


def test_clip_text_returns_original_when_under_budget() -> None:
    assert clip_text("abc", 10) == "abc"
