"""Tests for the str_replace_file tool."""

from __future__ import annotations

from pathlib import Path

from pythinker_host.path import HostPath

from pythinker_code.tools.file.read import Params as ReadParams
from pythinker_code.tools.file.read import ReadFile
from pythinker_code.tools.file.replace import Edit, Params, StrReplaceFile
from pythinker_code.wire.types import DiffDisplayBlock


async def test_replace_single_occurrence(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing a single occurrence."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Hello world! This is a test."
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="world", new="universe"))
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    diff_block = next(block for block in result.display if block.type == "diff")
    assert isinstance(diff_block, DiffDisplayBlock)
    assert diff_block.path == str(file_path)
    assert diff_block.old_text == original_content
    assert diff_block.new_text == "Hello universe! This is a test."
    assert await file_path.read_text() == "Hello universe! This is a test."


async def test_replace_all_occurrences(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing all occurrences."""
    file_path = temp_work_dir / "test.txt"
    original_content = "apple banana apple cherry apple"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(
            path=str(file_path),
            edit=Edit(old="apple", new="fruit", replace_all=True),
        )
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert await file_path.read_text() == "fruit banana fruit cherry fruit"


async def test_replace_multiple_edits(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test applying multiple edits."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Hello world! Goodbye world!"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(
            path=str(file_path),
            edit=[
                Edit(old="Hello", new="Hi"),
                Edit(old="Goodbye", new="See you"),
            ],
        )
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert await file_path.read_text() == "Hi world! See you world!"


async def test_replace_accepts_json_string_edit(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Accept the edit object when a model passes it as a JSON string."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("old content")

    result = await str_replace_file_tool.call(
        {
            "path": str(file_path),
            "edit": '{"old": "old", "new": "new"}',
        }
    )

    assert not result.is_error
    assert await file_path.read_text() == "new content"


async def test_replace_accepts_json_string_edit_list(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Accept multiple edits when a model passes the list as a JSON string."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("alpha beta gamma")

    result = await str_replace_file_tool.call(
        {
            "path": str(file_path),
            "edit": '[{"old": "alpha", "new": "one"}, {"old": "beta", "new": "two"}]',
        }
    )

    assert not result.is_error
    assert await file_path.read_text() == "one two gamma"


async def test_replace_accepts_flattened_edit_fields(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Accept top-level old/new fields from malformed model tool calls."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("old content")

    result = await str_replace_file_tool.call({"path": str(file_path), "old": "old", "new": "new"})

    assert not result.is_error
    assert await file_path.read_text() == "new content"


async def test_replace_accepts_edit_aliases(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Accept oldText/newText aliases from edit-tool-shaped calls."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("old content")

    result = await str_replace_file_tool.call(
        {"path": str(file_path), "edits": [{"oldText": "old", "newText": "new"}]}
    )

    assert not result.is_error
    assert await file_path.read_text() == "new content"


async def test_malformed_edit_batch_returns_actionable_error(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """A list batch with collapsed entries gets a clear resend-as-singles error.

    Mirrors a streaming glitch where edit entries degrade to ``{"$text": ...}``
    instead of ``{old, new}``. The file must be left untouched.
    """
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("alpha beta gamma")

    result = await str_replace_file_tool.call(
        {
            "path": str(file_path),
            "edit": [
                {"old": "alpha", "new": "one"},
                {"$text": "beta"},
                {"$text": "false"},
            ],
        }
    )

    assert result.is_error
    assert "Malformed `edit` batch" in result.message
    assert "entries 2, 3" in result.message
    assert "its own StrReplaceFile call" in result.message
    # No partial application: the one valid entry must NOT have been applied.
    assert await file_path.read_text() == "alpha beta gamma"


async def test_valid_edit_batch_is_unaffected_by_malformed_guard(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """The malformed-batch guard never trips on a fully valid list batch."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("alpha beta gamma")

    result = await str_replace_file_tool.call(
        {
            "path": str(file_path),
            "edit": [{"old": "alpha", "new": "one"}, {"old": "beta", "new": "two"}],
        }
    )

    assert not result.is_error
    assert await file_path.read_text() == "one two gamma"


async def test_replace_multiline_content(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing multi-line content."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Line 1\nLine 2\nLine 3\n"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(
            path=str(file_path),
            edit=Edit(old="Line 2\nLine 3", new="Modified line 2\nModified line 3"),
        )
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert await file_path.read_text() == "Line 1\nModified line 2\nModified line 3\n"


async def test_replace_unicode_content(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing unicode content."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Hello world! café"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="world", new="earth"))
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert await file_path.read_text() == "Hello earth! café"


async def test_replace_no_match(str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath):
    """Test replacing when the old string is not found."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Hello world!"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="notfound", new="replacement"))
    )

    assert result.is_error
    assert "No replacements were made" in result.message
    assert await file_path.read_text() == original_content  # Content unchanged


async def test_replace_with_relative_path(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing with a relative path inside the work directory."""
    relative_dir = temp_work_dir / "relative" / "path"
    await relative_dir.mkdir(parents=True, exist_ok=True)
    file_path = relative_dir / "file.txt"
    await file_path.write_text("old content")

    result = await str_replace_file_tool(
        Params(path="relative/path/file.txt", edit=Edit(old="old", new="new"))
    )

    assert not result.is_error
    assert await file_path.read_text() == "new content"


async def test_replace_outside_work_directory(
    str_replace_file_tool: StrReplaceFile, outside_file: Path
):
    """Test replacing outside the working directory with an absolute path."""
    outside_file.write_text("old content", encoding="utf-8")

    result = await str_replace_file_tool(
        Params(path=str(outside_file), edit=Edit(old="old", new="new"))
    )

    assert not result.is_error
    assert outside_file.read_text(encoding="utf-8") == "new content"


async def test_replace_outside_work_directory_with_prefix(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Paths sharing the work dir prefix but outside should still be editable
    with absolute paths."""
    base = Path(str(temp_work_dir))
    sneaky_dir = base.parent / f"{base.name}-sneaky"
    sneaky_dir.mkdir(parents=True, exist_ok=True)
    sneaky_file = sneaky_dir / "test.txt"
    sneaky_file.write_text("content", encoding="utf-8")

    result = await str_replace_file_tool(
        Params(path=str(sneaky_file), edit=Edit(old="content", new="new"))
    )

    assert not result.is_error
    assert sneaky_file.read_text() == "new"


async def test_replace_nonexistent_file(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing in a non-existent file."""
    file_path = temp_work_dir / "nonexistent.txt"

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="old", new="new"))
    )

    assert result.is_error
    assert "does not exist" in result.message


async def test_replace_directory_instead_of_file(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing in a directory instead of a file."""
    dir_path = temp_work_dir / "directory"
    await dir_path.mkdir()

    result = await str_replace_file_tool(
        Params(path=str(dir_path), edit=Edit(old="old", new="new"))
    )

    assert result.is_error
    assert "is not a file" in result.message


async def test_replace_mixed_multiple_edits(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test multiple edits with different replace_all settings."""
    file_path = temp_work_dir / "test.txt"
    original_content = "apple apple banana apple cherry"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(
            path=str(file_path),
            edit=[
                Edit(old="apple apple", new="fruit apple", replace_all=False),
                Edit(old="banana", new="tasty", replace_all=True),
            ],
        )
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert await file_path.read_text() == "fruit apple tasty apple cherry"


async def test_multi_edit_reports_missing_old_string(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """A non-matching edit in a multi-edit list must error, not silently no-op.

    Regression: previously the file was written with only the matching edits
    applied and the missing edit was swallowed because the no-change check ran
    once over the whole batch.
    """
    file_path = temp_work_dir / "test.txt"
    original_content = "apple banana cherry"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(
            path=str(file_path),
            edit=[
                Edit(old="apple", new="fruit"),
                Edit(old="not-present", new="x"),
            ],
        )
    )

    assert result.is_error
    assert "No replacements were made" in result.message
    assert "not-present" in result.message
    # The file must be left untouched when any edit fails to match.
    assert await file_path.read_text() == original_content


async def test_multi_edit_count_handles_chained_edits(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Replacement count is tallied against progressively-edited content.

    The second edit targets text produced by the first; the success message
    must still count it (the old code counted against the original content and
    reported zero for chained edits).
    """
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("alpha")

    result = await str_replace_file_tool(
        Params(
            path=str(file_path),
            edit=[
                Edit(old="alpha", new="beta"),
                Edit(old="beta", new="gamma"),
            ],
        )
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert "2 total replacement(s)" in result.message
    assert await file_path.read_text() == "gamma"


async def test_single_edit_requires_unique_old_string(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """A non-replace_all edit must not silently choose the first match."""
    file_path = temp_work_dir / "test.txt"
    original_content = "apple banana apple"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="apple", new="fruit"))
    )

    assert result.is_error
    assert "occurs 2 times" in result.message
    assert "replace_all=true" in result.message
    assert await file_path.read_text() == original_content


async def test_replace_rejects_empty_old_string(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """An empty old string would otherwise insert text instead of replacing."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Hello world!"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="", new="prefix"))
    )

    assert result.is_error
    assert "old string cannot be empty" in result.message
    assert await file_path.read_text() == original_content


async def test_replace_rejects_empty_edit_list(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "test.txt"
    await file_path.write_text("Hello world!")

    result = await str_replace_file_tool(Params(path=str(file_path), edit=[]))

    assert result.is_error
    assert "At least one edit" in result.message


async def test_replace_empty_strings(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Test replacing with empty strings."""
    file_path = temp_work_dir / "test.txt"
    original_content = "Hello world!"
    await file_path.write_text(original_content)

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="world", new=""))
    )

    assert not result.is_error
    assert "successfully edited" in result.message
    assert await file_path.read_text() == "Hello !"


async def test_replace_preserves_crlf_line_endings(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """StrReplaceFile must round-trip CRLF line endings unchanged.

    Write a CRLF file via write_bytes (bypassing newline normalization), apply
    a replacement, and assert that every \\r\\n survives intact — only the
    edited token changes.
    """
    file_path = temp_work_dir / "test.txt"
    await file_path.write_bytes(b"a\r\nworld\r\nc\r\n")

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="world", new="universe"))
    )

    assert not result.is_error
    assert await file_path.read_bytes() == b"a\r\nuniverse\r\nc\r\n"


async def test_replace_multiline_lf_old_on_crlf_file(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """A multi-line LF-joined old string must still match a CRLF file.

    Files are read with newline='' (CRLF preserved) while models echo old
    strings LF-joined, so without the CRLF fallback every multi-line edit on a
    CRLF file failed with 'not found'. The replacement must gain CRLF joints
    too, so the file does not end up with mixed line endings.
    """
    file_path = temp_work_dir / "test.txt"
    await file_path.write_bytes(b"a\r\nb\r\nc\r\n")

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="a\nb", new="a\nB"))
    )

    assert not result.is_error
    assert await file_path.read_bytes() == b"a\r\nB\r\nc\r\n"


async def test_replace_multiline_lf_old_on_crlf_file_replace_all(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """replace_all applies the CRLF-translated needle to every occurrence."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_bytes(b"x\r\ny\r\nz\r\nx\r\ny\r\n")

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="x\ny", new="x\nY", replace_all=True))
    )

    assert not result.is_error
    assert await file_path.read_bytes() == b"x\r\nY\r\nz\r\nx\r\nY\r\n"


async def test_replace_multiline_crlf_ambiguity_still_detected(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    """Uniqueness is re-checked against the CRLF-translated needle."""
    file_path = temp_work_dir / "test.txt"
    await file_path.write_bytes(b"x\r\ny\r\nz\r\nx\r\ny\r\n")

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="x\ny", new="x\nY"))
    )

    assert result.is_error
    assert "occurs 2 times" in result.message


async def test_replace_blocked_when_file_changed_since_read(
    read_file_tool: ReadFile, str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
) -> None:
    """Stale-edit guard: a read then an external change (mtime bump) that leaves the old
    string intact must still block the edit — exact-string matching alone cannot catch it.
    Read and StrReplace share the runtime's file_read_cache."""
    import os

    file_path = temp_work_dir / "tracked.txt"
    await file_path.write_text("keep ME here\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    # External change preserving the old string `ME`, with a strictly-newer mtime.
    await file_path.write_text("keep ME here\nexternal append\n")
    st = os.stat(str(file_path))
    os.utime(str(file_path), (st.st_atime, st.st_mtime + 10))

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="ME", new="YOU"))
    )
    assert result.is_error
    assert "modified since" in result.message
    assert "external append" in await file_path.read_text()  # external change survived


async def test_replace_allowed_after_read(
    read_file_tool: ReadFile, str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
) -> None:
    """A read followed by an edit (no external change) is allowed."""
    file_path = temp_work_dir / "ok.txt"
    await file_path.write_text("alpha beta\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="beta", new="gamma"))
    )
    assert not result.is_error
    assert await file_path.read_text() == "alpha gamma\n"


async def test_replace_without_prior_read_allowed(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
) -> None:
    """The guard is stale-detection only: a file the agent never read is not gated."""
    file_path = temp_work_dir / "unread.txt"
    await file_path.write_text("one two\n")

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=Edit(old="two", new="three"))
    )
    assert not result.is_error
    assert await file_path.read_text() == "one three\n"


async def test_consecutive_edits_not_flagged_stale(
    read_file_tool: ReadFile, str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
) -> None:
    """The tool's own edit refreshes the read-state, so an immediate second edit is not
    falsely flagged as stale."""
    file_path = temp_work_dir / "iter.txt"
    await file_path.write_text("v0\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    assert not (
        await str_replace_file_tool(Params(path=str(file_path), edit=Edit(old="v0", new="v1")))
    ).is_error
    assert not (
        await str_replace_file_tool(Params(path=str(file_path), edit=Edit(old="v1", new="v2")))
    ).is_error
    assert await file_path.read_text() == "v2\n"
