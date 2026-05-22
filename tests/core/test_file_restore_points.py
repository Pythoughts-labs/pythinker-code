from __future__ import annotations

from pathlib import Path

from pythinker_code.file_restore import (
    create_file_restore_point,
    list_file_restore_points,
    restore_file_restore_point,
)
from pythinker_code.soul.agent import Runtime
from pythinker_code.soul.approval import Approval
from pythinker_code.tools.file.replace import Edit, StrReplaceFile
from pythinker_code.tools.file.replace import Params as ReplaceParams
from pythinker_code.tools.file.write import Params as WriteParams
from pythinker_code.tools.file.write import WriteFile
from tests.conftest import tool_call_context


def test_create_and_restore_existing_file(runtime: Runtime, temp_work_dir) -> None:
    target = Path(str(temp_work_dir)) / "app.py"
    target.write_text("before\n", encoding="utf-8")

    point = create_file_restore_point(runtime.session, tool_name="WriteFile", path=target)
    target.write_text("after\n", encoding="utf-8")

    restored = restore_file_restore_point(runtime.session, point.id)

    assert restored.path == target
    assert target.read_text(encoding="utf-8") == "before\n"


def test_restore_removes_file_that_did_not_exist(runtime: Runtime, temp_work_dir) -> None:
    target = Path(str(temp_work_dir)) / "new.py"

    point = create_file_restore_point(runtime.session, tool_name="WriteFile", path=target)
    target.write_text("created\n", encoding="utf-8")

    restore_file_restore_point(runtime.session, point.id)

    assert not target.exists()


def test_list_file_restore_points_newest_first(runtime: Runtime, temp_work_dir) -> None:
    first = Path(str(temp_work_dir)) / "first.py"
    second = Path(str(temp_work_dir)) / "second.py"

    older = create_file_restore_point(runtime.session, tool_name="WriteFile", path=first)
    newer = create_file_restore_point(runtime.session, tool_name="StrReplaceFile", path=second)

    points = list_file_restore_points(runtime.session)

    assert [point.id for point in points] == [newer.id, older.id]
    assert points[0].tool_name == "StrReplaceFile"


async def test_write_and_replace_tools_create_restore_points(
    runtime: Runtime, temp_work_dir
) -> None:
    target = Path(str(temp_work_dir)) / "app.py"
    target.write_text("one\n", encoding="utf-8")

    with tool_call_context("WriteFile"):
        write_tool = WriteFile(runtime, Approval(yolo=True))
        write_result = await write_tool(WriteParams(path=str(target), content="two\n"))

    with tool_call_context("StrReplaceFile"):
        replace_tool = StrReplaceFile(runtime, Approval(yolo=True))
        replace_result = await replace_tool(
            ReplaceParams(path=str(target), edit=Edit(old="two", new="three"))
        )

    points = list_file_restore_points(runtime.session)

    assert not write_result.is_error
    assert not replace_result.is_error
    assert [point.tool_name for point in points[:2]] == ["StrReplaceFile", "WriteFile"]
