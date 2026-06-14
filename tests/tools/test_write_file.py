"""Tests for the write_file tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from pythinker_host.path import HostPath

from pythinker_code.tools.file.read import Params as ReadParams
from pythinker_code.tools.file.read import ReadFile
from pythinker_code.tools.file.write import Params, WriteFile
from pythinker_code.wire.types import DiffDisplayBlock


async def test_write_new_file(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing a new file."""
    file_path = temp_work_dir / "new_file.txt"
    content = "Hello, World!"

    result = await write_file_tool(Params(path=str(file_path), content=content))

    assert not result.is_error
    assert "successfully overwritten" in result.message
    diff_block = next(block for block in result.display if block.type == "diff")
    assert isinstance(diff_block, DiffDisplayBlock)
    assert diff_block.path == str(file_path)
    assert diff_block.old_text == ""
    assert diff_block.new_text == content
    assert await file_path.exists()
    assert await file_path.read_text() == content


async def test_overwrite_existing_file(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test overwriting an existing file."""
    file_path = temp_work_dir / "existing.txt"
    original_content = "Original content"
    await file_path.write_text(original_content)

    new_content = "New content"
    result = await write_file_tool(Params(path=str(file_path), content=new_content))

    assert not result.is_error
    assert "successfully overwritten" in result.message
    assert await file_path.read_text() == new_content


async def test_overwrite_blocked_when_file_changed_since_read(
    read_file_tool: ReadFile, write_file_tool: WriteFile, temp_work_dir: HostPath
) -> None:
    """Stale-overwrite guard: if the agent read a file and it then changed on disk, an
    overwrite is rejected so the external change is not clobbered. Read and Write share the
    runtime's file_read_cache."""
    import os

    file_path = temp_work_dir / "tracked.txt"
    await file_path.write_text("v1 content\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    # External change: new content + a strictly-newer mtime (deterministic, no sleep).
    await file_path.write_text("v2 external change\n")
    st = os.stat(str(file_path))
    os.utime(str(file_path), (st.st_atime, st.st_mtime + 10))

    result = await write_file_tool(Params(path=str(file_path), content="v3 agent overwrite\n"))
    assert result.is_error
    assert "modified since" in result.message
    assert "v2 external change" in await file_path.read_text()  # external change survived


async def test_overwrite_blocked_when_file_changed_during_approval(
    read_file_tool: ReadFile, write_file_tool: WriteFile, temp_work_dir: HostPath
) -> None:
    """Stale-overwrite guard re-checks AFTER approval: the file can change on disk during the
    (unbounded) approval window, and the overwrite writes params.content wholesale, so the
    pre-approval check alone would clobber the external edit. The post-approval re-check must
    block it.

    The approval `request` is patched to mutate the file (new size + strictly-newer mtime) then
    approve — exercising only the second check (the first ran before the prompt, when the file
    was still original)."""
    import os
    from unittest.mock import AsyncMock

    from pythinker_code.soul.approval import ApprovalResult

    file_path = temp_work_dir / "tracked.txt"
    await file_path.write_text("v1 content\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    external_content = "v2 external change during approval\n"

    async def mutate_then_approve(tool_name, action, description, **kwargs):  # type: ignore[no-untyped-def]
        # External change DURING the approval window: different size + strictly-newer mtime.
        await file_path.write_text(external_content)
        st = os.stat(str(file_path))
        os.utime(str(file_path), (st.st_atime, st.st_mtime + 10))
        return ApprovalResult(approved=True)

    write_file_tool._approval.request = AsyncMock(side_effect=mutate_then_approve)  # type: ignore[method-assign]

    result = await write_file_tool(Params(path=str(file_path), content="v3 agent overwrite\n"))
    assert result.is_error
    assert "modified since" in result.message
    # The external change survived; the agent's overwrite was NOT applied (no clobber).
    assert await file_path.read_text() == external_content
    assert "v3 agent overwrite" not in await file_path.read_text()


async def test_overwrite_allowed_after_read(
    read_file_tool: ReadFile, write_file_tool: WriteFile, temp_work_dir: HostPath
) -> None:
    """A read followed by an overwrite (no external change) is allowed."""
    file_path = temp_work_dir / "ok.txt"
    await file_path.write_text("original\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    result = await write_file_tool(Params(path=str(file_path), content="updated\n"))
    assert not result.is_error
    assert await file_path.read_text() == "updated\n"


async def test_consecutive_overwrites_not_flagged_stale(
    read_file_tool: ReadFile, write_file_tool: WriteFile, temp_work_dir: HostPath
) -> None:
    """The tool's own write refreshes the read-state, so an immediate second overwrite is
    not falsely flagged as stale."""
    file_path = temp_work_dir / "iter.txt"
    await file_path.write_text("v0\n")
    assert not (await read_file_tool(ReadParams(path=str(file_path)))).is_error

    assert not (await write_file_tool(Params(path=str(file_path), content="v1\n"))).is_error
    assert not (await write_file_tool(Params(path=str(file_path), content="v2\n"))).is_error
    assert await file_path.read_text() == "v2\n"


async def test_append_to_file(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test appending to an existing file."""
    file_path = temp_work_dir / "append_test.txt"
    original_content = "First line\n"
    await file_path.write_text(original_content)

    append_content = "Second line\n"
    result = await write_file_tool(
        Params(path=str(file_path), content=append_content, mode="append")
    )

    assert not result.is_error
    assert "successfully appended to" in result.message
    expected_content = original_content + append_content
    assert await file_path.read_text() == expected_content


async def test_write_unicode_content(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing unicode content."""
    file_path = temp_work_dir / "unicode.txt"
    content = "Hello world 🌍\nUnicode: café, naïve, résumé"

    result = await write_file_tool(Params(path=str(file_path), content=content))

    assert not result.is_error
    assert await file_path.exists()
    assert await file_path.read_text(encoding="utf-8") == content


async def test_write_empty_content(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing empty content."""
    file_path = temp_work_dir / "empty.txt"
    content = ""

    result = await write_file_tool(Params(path=str(file_path), content=content))

    assert not result.is_error
    assert await file_path.exists()
    assert await file_path.read_text() == content


async def test_write_multiline_content(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing multiline content."""
    file_path = temp_work_dir / "multiline.txt"
    content = "Line 1\nLine 2\nLine 3\n"

    result = await write_file_tool(Params(path=str(file_path), content=content))

    assert not result.is_error
    assert await file_path.read_text() == content


async def test_write_with_relative_path(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing with a relative path inside the work directory."""
    relative_dir = temp_work_dir / "relative" / "path"
    await relative_dir.mkdir(parents=True, exist_ok=True)

    result = await write_file_tool(Params(path="relative/path/file.txt", content="content"))

    assert not result.is_error
    assert await (temp_work_dir / "relative" / "path" / "file.txt").read_text() == "content"


async def test_write_outside_work_directory(write_file_tool: WriteFile, outside_file: Path):
    """Test writing outside the working directory with an absolute path."""
    result = await write_file_tool(Params(path=str(outside_file), content="content"))

    assert not result.is_error
    assert outside_file.read_text() == "content"


async def test_write_outside_work_directory_with_prefix(
    write_file_tool: WriteFile, temp_work_dir: HostPath
):
    """Paths sharing the same prefix as work dir should still be writable with absolute paths."""
    base = Path(str(temp_work_dir))
    sneaky_dir = base.parent / f"{base.name}-sneaky"
    sneaky_dir.mkdir(parents=True, exist_ok=True)
    sneaky_file = sneaky_dir / "file.txt"

    result = await write_file_tool(Params(path=str(sneaky_file), content="content"))

    assert not result.is_error
    assert sneaky_file.read_text() == "content"


async def test_write_to_nonexistent_directory(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing to a non-existent directory."""
    file_path = temp_work_dir / "nonexistent" / "file.txt"

    result = await write_file_tool(Params(path=str(file_path), content="content"))

    assert result.is_error
    assert "parent directory does not exist" in result.message


async def test_write_with_invalid_mode(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing with an invalid mode."""
    file_path = temp_work_dir / "test.txt"

    with pytest.raises(ValidationError):
        await write_file_tool(Params(path=str(file_path), content="content", mode="invalid"))  # type: ignore[reportArgumentType]


async def test_append_to_nonexistent_file(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test appending to a non-existent file (should create it)."""
    file_path = temp_work_dir / "new_append.txt"
    content = "New content\n"

    result = await write_file_tool(Params(path=str(file_path), content=content, mode="append"))

    assert not result.is_error
    assert "successfully appended to" in result.message
    assert await file_path.exists()
    assert await file_path.read_text() == content


async def test_write_large_content(write_file_tool: WriteFile, temp_work_dir: HostPath):
    """Test writing large content."""
    file_path = temp_work_dir / "large.txt"
    content = "Large content line\n" * 1000

    result = await write_file_tool(Params(path=str(file_path), content=content))

    assert not result.is_error
    assert await file_path.exists()
    assert await file_path.read_text() == content


async def test_write_symlink_escaping_workspace_classified_outside(
    write_file_tool: WriteFile, temp_work_dir: HostPath, tmp_path: Path
):
    """Writing through an in-workspace symlink whose real target is outside the workspace
    must be classified as EDIT_OUTSIDE (i.e. require outside-workspace approval), not as a
    normal in-workspace edit.

    Before the fix classify_edit_action sees the canonical (non-symlink-resolved) path that
    still appears inside the workspace, so it returns EDIT — the symlink escapes undetected.
    After the fix the real target is resolved first, so EDIT_OUTSIDE is returned.
    """
    from unittest.mock import AsyncMock, MagicMock

    from pythinker_code.tools.file import FileActions

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_target = outside_dir / "real_file.txt"
    outside_target.write_text("original")

    # Create an in-workspace symlink pointing at the outside file
    symlink_path = temp_work_dir / "escape_link.txt"
    symlink_path.unsafe_to_local_path().symlink_to(outside_target)

    # Intercept the approval call to capture the action that was passed
    captured_actions: list[FileActions] = []
    original_request = write_file_tool._approval.request

    async def capture_request(tool_name, action, description, **kwargs):  # type: ignore[no-untyped-def]
        captured_actions.append(action)
        # Auto-approve so the write proceeds and we just check the action
        mock_result = MagicMock()
        mock_result.__bool__ = lambda s: True
        return mock_result

    write_file_tool._approval.request = AsyncMock(side_effect=capture_request)  # type: ignore[method-assign]
    try:
        await write_file_tool(Params(path=str(symlink_path), content="new content"))
    finally:
        write_file_tool._approval.request = original_request  # type: ignore[method-assign]

    assert captured_actions, "Approval was never requested"
    assert captured_actions[0] == FileActions.EDIT_OUTSIDE, (
        f"Expected EDIT_OUTSIDE for symlink escaping workspace, got {captured_actions[0]}"
    )


async def test_relative_path_resolves_against_work_dir(
    write_file_tool: WriteFile, temp_work_dir: HostPath, tmp_path: Path
):
    """An isolated child's relative write must land in its (overridden) work
    dir, not wherever the process cwd happens to be."""
    import os

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    previous_cwd = os.getcwd()
    os.chdir(elsewhere)
    try:
        result = await write_file_tool(Params(path="rel_note.txt", content="hi"))
    finally:
        os.chdir(previous_cwd)

    assert not result.is_error
    assert (Path(str(temp_work_dir)) / "rel_note.txt").read_text() == "hi"
    assert not (elsewhere / "rel_note.txt").exists()
