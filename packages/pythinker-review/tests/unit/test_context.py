from pathlib import Path

from pythinker_review.engine.context import FileContext, gather_context


def test_full_current_file_when_under_budget(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
    ctx = gather_context(
        repo=tmp_path, file_path="a.py", hunks_post_lines=[1, 2], budget_chars=10_000, base_sha=None
    )
    assert isinstance(ctx, FileContext)
    assert ctx.current_full == "line1\nline2\nline3\n"
    assert ctx.current_windows == ()


def test_windowed_when_over_budget(tmp_path: Path) -> None:
    (tmp_path / "big.py").write_text(
        "\n".join(f"line{i}" for i in range(1, 401)) + "\n", encoding="utf-8"
    )
    ctx = gather_context(
        repo=tmp_path, file_path="big.py", hunks_post_lines=[100], budget_chars=500, base_sha=None
    )
    assert ctx.current_full is None
    assert ctx.current_windows
    assert ctx.current_windows[0].start_line <= 100 <= ctx.current_windows[0].end_line


def test_missing_file_returns_empty_context(tmp_path: Path) -> None:
    ctx = gather_context(
        repo=tmp_path,
        file_path="missing.py",
        hunks_post_lines=[1],
        budget_chars=10_000,
        base_sha=None,
    )
    assert ctx.current_full is None
    assert ctx.current_windows == ()
