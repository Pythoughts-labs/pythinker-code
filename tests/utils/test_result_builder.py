"""Tests for ToolResultBuilder."""

from __future__ import annotations

from pythinker_code.tools.utils import ToolResultBuilder


def test_basic_functionality():
    """Test basic functionality without limits."""
    builder = ToolResultBuilder(max_chars=50)

    written1 = builder.write("Hello")
    written2 = builder.write(" world")

    assert written1 == 5
    assert written2 == 6

    result = builder.ok("Operation completed")
    assert result.output == "Hello world"
    assert result.message == "Operation completed."
    assert not builder.is_full


def test_char_limit_truncation():
    """Test character limit truncation."""
    builder = ToolResultBuilder(max_chars=10)

    written1 = builder.write("Hello")
    written2 = builder.write(" world!")  # This should trigger truncation

    assert written1 == 5
    assert written2 == 14  # "[...truncated]" marker was added
    assert builder.is_full

    result = builder.ok("Operation completed")
    assert result.output == "Hello[...truncated]"
    assert "Operation completed." in result.message
    assert "Output is truncated" in result.message


def test_line_length_limit():
    """Test line length limit functionality."""
    builder = ToolResultBuilder(max_chars=100, max_line_length=20)

    written = builder.write("This is a very long line that should be truncated\n")

    assert written == 20  # Line was truncated to fit marker

    result = builder.ok()
    assert isinstance(result.output, str)
    assert "[...truncated]" in result.output
    assert "Output is truncated" in result.message


def test_both_limits():
    """Test both character and line limits together."""
    builder = ToolResultBuilder(max_chars=40, max_line_length=20)

    w1 = builder.write("Line 1\n")  # 7 chars
    w2 = builder.write("This is a very long line that exceeds limit\n")  # 20 chars (truncated)
    w3 = builder.write("This would exceed char limit")  # 14 chars (truncated)

    assert w1 == 7
    assert w2 == 20  # Line truncated to fit limit
    assert w3 == 14  # Line truncated due to char limit
    assert builder.is_full
    # Total might exceed 40 due to truncation markers

    result = builder.ok()
    assert isinstance(result.output, str)
    assert "[...truncated]" in result.output
    assert "Output is truncated" in result.message


def test_error_result():
    """Test error result creation."""
    builder = ToolResultBuilder(max_chars=20)

    builder.write("Some output")
    result = builder.error("Something went wrong", brief="Error occurred")

    assert result.output == "Some output"
    assert result.message == "Something went wrong"
    assert result.brief == "Error occurred"


def test_error_with_truncation():
    """Test error result with truncated output."""
    builder = ToolResultBuilder(max_chars=10)

    builder.write("Very long output that exceeds limit")
    result = builder.error("Command failed", brief="Failed")

    assert isinstance(result.output, str)
    assert "[...truncated]" in result.output
    assert "Command failed" in result.message
    assert "Output is truncated" in result.message
    assert result.brief == "Failed"


def test_properties():
    """Test builder properties."""
    builder = ToolResultBuilder(max_chars=20, max_line_length=30)

    assert builder.n_chars == 0
    assert builder.n_lines == 0
    assert not builder.is_full

    builder.write("Short\n")
    assert builder.n_chars == 6
    assert builder.n_lines == 1

    builder.write("1\n2\n")
    assert builder.n_chars == 10
    assert builder.n_lines == 3

    builder.write("More text that exceeds")  # Will trigger char truncation
    assert builder.is_full


def test_write_when_full():
    """Test writing when buffer is already full."""
    builder = ToolResultBuilder(max_chars=5)

    written1 = builder.write("Hello")  # Fills buffer exactly
    written2 = builder.write(" world")  # Should write nothing

    assert written1 == 5
    assert written2 == 0
    assert builder.is_full

    result = builder.ok()
    assert result.output == "Hello"


def test_multiline_handling():
    """Test proper multiline text handling."""
    builder = ToolResultBuilder(max_chars=100)

    written = builder.write("Line 1\nLine 2\nLine 3")

    assert written == 20
    assert builder.n_lines == 2  # Two newlines

    result = builder.ok()
    assert result.output == "Line 1\nLine 2\nLine 3"


def test_empty_write():
    """Test writing empty string."""
    builder = ToolResultBuilder(max_chars=50)

    written = builder.write("")

    assert written == 0
    assert builder.n_chars == 0
    assert not builder.is_full


def test_tail_empty():
    """tail() on an empty buffer returns an empty string."""
    builder = ToolResultBuilder()
    assert builder.tail() == ""


def test_tail_basic():
    """tail() returns the trailing lines, oldest-to-newest, no trailing newline."""
    builder = ToolResultBuilder()
    builder.write("first line\nsecond line\nthird line\n")
    assert builder.tail() == "first line\nsecond line\nthird line"


def test_tail_skips_blank_lines():
    """Blank/whitespace-only lines are skipped so the tail carries real context."""
    builder = ToolResultBuilder()
    builder.write("real error\n\n   \n")
    assert builder.tail() == "real error"


def test_tail_respects_max_lines():
    """tail() returns at most max_lines lines, taken from the end."""
    builder = ToolResultBuilder()
    builder.write("\n".join(f"line {i}" for i in range(10)) + "\n")
    assert builder.tail(max_lines=3) == "line 7\nline 8\nline 9"


def test_tail_truncates_long_line():
    """Over-long lines are clipped to max_line_len and suffixed with an ellipsis."""
    builder = ToolResultBuilder()
    builder.write("x" * 500 + "\n")
    tail = builder.tail(max_line_len=100)
    assert tail.endswith("...")
    assert len(tail) == 103


def test_tail_handles_multiple_writes():
    """tail() spans separate write() calls (e.g. interleaved stdout/stderr)."""
    builder = ToolResultBuilder()
    builder.write("stdout chunk\n")
    builder.write("stderr: permission denied\n")
    assert builder.tail(max_lines=2) == "stdout chunk\nstderr: permission denied"


def test_spill_on_truncation_saves_full_output_and_hints(tmp_path):
    """tooldesc-2/ctxmgmt-1: truncated foreground output spills to disk with a
    recovery hint instead of being silently discarded."""
    spill_dir = tmp_path / "tool-output"
    builder = ToolResultBuilder(max_chars=10)
    builder.enable_spill(spill_dir, "bash")

    builder.write("Hello")
    builder.write(" world! this is a long tail that gets truncated")
    result = builder.ok("Done")

    assert builder.is_full
    # The in-context output is still truncated.
    assert isinstance(result.output, str)
    assert "[...truncated]" in result.output
    # The message carries an actionable recovery hint pointing at the saved file.
    assert "ReadFile(" in result.message
    # The spilled file holds the COMPLETE untruncated output.
    files = list(spill_dir.glob("bash-*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == (
        "Hello world! this is a long tail that gets truncated"
    )
    assert str(files[0]) in result.message


async def test_spill_to_disk_offloads_and_is_idempotent(tmp_path):
    """ctxmgmt-1: spill_to_disk performs the (potentially multi-MB) write off the event
    loop and is idempotent — pre-spilling then calling ok() writes the file exactly once,
    with no partial/temp residue from the atomic write, and the cached hint is reused."""
    spill_dir = tmp_path / "tool-output"
    builder = ToolResultBuilder(max_chars=10)
    builder.enable_spill(spill_dir, "bash")
    builder.write("Hello")
    builder.write(" world! this is a long tail that gets truncated")

    await builder.spill_to_disk()

    files = list(spill_dir.glob("bash-*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == (
        "Hello world! this is a long tail that gets truncated"
    )
    # Atomic temp+replace leaves no partial residue.
    assert list(spill_dir.glob("*.tmp")) == []

    # ok() reuses the already-written hint and does not write a second file.
    result = builder.ok("Done")
    assert len(list(spill_dir.glob("bash-*.txt"))) == 1
    assert str(files[0]) in result.message


def test_no_spill_when_disabled(tmp_path):
    builder = ToolResultBuilder(max_chars=10)
    builder.write("Hello world!")  # truncates
    result = builder.ok()

    assert "Output is truncated" in result.message
    assert not (tmp_path / "tool-output").exists()


def test_no_spill_when_no_truncation(tmp_path):
    spill_dir = tmp_path / "tool-output"
    builder = ToolResultBuilder(max_chars=1000)
    builder.enable_spill(spill_dir, "bash")
    builder.write("short output")
    result = builder.ok("ok")

    assert "truncated" not in result.message.lower()
    assert not spill_dir.exists()


def test_spill_is_idempotent(tmp_path):
    """ok() and error() must not each write a separate spill file."""
    spill_dir = tmp_path / "tool-output"
    builder = ToolResultBuilder(max_chars=10)
    builder.enable_spill(spill_dir, "bash")
    builder.write("Hello world! tail that truncates")

    first = builder.ok("Done").message
    second = builder.error("boom", brief="b").message

    files = list(spill_dir.glob("bash-*.txt"))
    assert len(files) == 1
    # Same cached hint (same path) on both.
    assert str(files[0]) in first
    assert str(files[0]) in second


def test_spill_sanitizes_tool_name_against_traversal(tmp_path):
    spill_dir = tmp_path / "tool-output"
    builder = ToolResultBuilder(max_chars=10)
    builder.enable_spill(spill_dir, "../../evil")
    builder.write("Hello world! tail that truncates")
    builder.ok("Done")

    # No file escaped spill_dir; the unsafe stem was neutralized.
    assert not (tmp_path / "evil").exists()
    files = list(spill_dir.iterdir())
    assert len(files) == 1
    assert files[0].parent == spill_dir
    assert ".." not in files[0].name


def test_spill_buffer_is_memory_capped(tmp_path, monkeypatch):
    import pythinker_code.tools.utils as utils_mod

    monkeypatch.setattr(utils_mod, "SPILL_MAX_CHARS", 20)
    spill_dir = tmp_path / "tool-output"
    builder = ToolResultBuilder(max_chars=5)
    builder.enable_spill(spill_dir, "bash")
    for _ in range(10):
        builder.write("0123456789")  # 100 chars total, well over the 20 cap
    result = builder.ok("Done")

    files = list(spill_dir.glob("bash-*.txt"))
    assert len(files) == 1
    saved = files[0].read_text(encoding="utf-8")
    assert len(saved) <= 30  # capped near SPILL_MAX_CHARS, not the full 100
    assert "capped" in result.message
