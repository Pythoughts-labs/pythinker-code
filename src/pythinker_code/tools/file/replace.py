import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast, override

from pydantic import BaseModel, Field, model_validator
from pythinker_core.tooling import CallableTool2, ToolError, ToolReturnValue
from pythinker_host.path import HostPath

from pythinker_code.file_restore import create_file_restore_point
from pythinker_code.soul.agent import Runtime
from pythinker_code.soul.approval import Approval
from pythinker_code.soul.permission import check_file_mutation_allowed
from pythinker_code.tools.display import DisplayBlock
from pythinker_code.tools.file import FileActions
from pythinker_code.tools.file.plan_mode import inspect_plan_edit_target
from pythinker_code.tools.utils import load_desc
from pythinker_code.utils.diff import build_diff_blocks
from pythinker_code.utils.logging import logger
from pythinker_code.utils.path import is_within_workspace

_BASE_DESCRIPTION = load_desc(Path(__file__).parent / "replace.md")


class Edit(BaseModel):
    old: str = Field(description="The old string to replace. Can be multi-line.")
    new: str = Field(description="The new string to replace with. Can be multi-line.")
    replace_all: bool = Field(description="Whether to replace all occurrences.", default=False)


class Params(BaseModel):
    path: str = Field(
        description=(
            "The path to the file to edit. Absolute paths are required when editing files "
            "outside the working directory."
        )
    )
    edit: Edit | list[Edit] = Field(
        description=(
            "The edit(s) to apply to the file. "
            "You can provide a single edit or a list of edits here."
        )
    )

    @staticmethod
    def _json_string_to_edit(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            parsed: Any = json.loads(value)
        except json.JSONDecodeError:
            return value
        return (
            cast(dict[str, Any] | list[Any], parsed) if isinstance(parsed, (dict, list)) else value
        )

    @classmethod
    def _normalize_edit_aliases(cls, value: Any) -> Any:
        value = cls._json_string_to_edit(value)
        if isinstance(value, list):
            return [cls._normalize_edit_aliases(item) for item in cast(list[Any], value)]
        if not isinstance(value, dict):
            return value

        normalized: dict[str, Any] = dict(cast(dict[str, Any], value))
        if "old" not in normalized and "oldText" in normalized:
            normalized["old"] = normalized["oldText"]
        if "new" not in normalized and "newText" in normalized:
            normalized["new"] = normalized["newText"]
        if "replace_all" not in normalized and "replaceAll" in normalized:
            normalized["replace_all"] = normalized["replaceAll"]
        return normalized

    @model_validator(mode="before")
    @classmethod
    def _normalize_common_edit_shapes(cls, data: Any) -> Any:
        """Accept common model-generated StrReplaceFile argument shapes.

        Agents occasionally pass the nested ``edit`` payload as a JSON string, or
        flatten ``old``/``new`` at the top level after seeing the UI label this
        tool as "Update". Normalize those shapes before Pydantic validates the
        canonical schema.
        """
        if not isinstance(data, dict):
            return data

        values: dict[str, Any] = dict(cast(dict[str, Any], data))
        if "edit" in values:
            values["edit"] = cls._normalize_edit_aliases(values["edit"])
            return values
        if "edits" in values:
            values["edit"] = cls._normalize_edit_aliases(values["edits"])
            return values

        old_key = "old" if "old" in values else "oldText" if "oldText" in values else None
        new_key = "new" if "new" in values else "newText" if "newText" in values else None
        if old_key is not None and new_key is not None:
            edit: dict[str, Any] = {"old": values[old_key], "new": values[new_key]}
            if "replace_all" in values:
                edit["replace_all"] = values["replace_all"]
            elif "replaceAll" in values:
                edit["replace_all"] = values["replaceAll"]
            values["edit"] = edit
            return values

        return values


class StrReplaceFile(CallableTool2[Params]):
    name: str = "StrReplaceFile"
    description: str = _BASE_DESCRIPTION
    params: type[Params] = Params

    def __init__(self, runtime: Runtime, approval: Approval):
        super().__init__()
        self._runtime = runtime
        self._work_dir = runtime.builtin_args.PYTHINKER_WORK_DIR
        self._additional_dirs = runtime.additional_dirs
        self._approval = approval
        self._plan_mode_checker: Callable[[], bool] | None = None
        self._plan_file_path_getter: Callable[[], Path | None] | None = None

    def bind_plan_mode(
        self, checker: Callable[[], bool], path_getter: Callable[[], Path | None]
    ) -> None:
        """Bind plan mode state checker and plan file path getter."""
        self._plan_mode_checker = checker
        self._plan_file_path_getter = path_getter

    async def _validate_path(self, path: HostPath) -> ToolError | None:
        """Validate that the path is safe to edit."""
        resolved_path = path.canonical()

        if (
            not is_within_workspace(resolved_path, self._work_dir, self._additional_dirs)
            and not path.is_absolute()
        ):
            return ToolError(
                message=(
                    f"`{path}` is not an absolute path. "
                    "You must provide an absolute path to edit a file "
                    "outside the working directory."
                ),
                brief="Invalid path",
            )
        return None

    def _apply_edit(self, content: str, edit: Edit) -> str:
        """Apply a single edit to the content."""
        if edit.replace_all:
            return content.replace(edit.old, edit.new)
        else:
            return content.replace(edit.old, edit.new, 1)

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        if not params.path:
            return ToolError(
                message="File path cannot be empty.",
                brief="Empty file path",
            )

        try:
            p = HostPath(params.path).expanduser()
            if err := await self._validate_path(p):
                return err
            p = p.canonical()

            plan_target = inspect_plan_edit_target(
                p,
                plan_mode_checker=self._plan_mode_checker,
                plan_file_path_getter=self._plan_file_path_getter,
            )
            if isinstance(plan_target, ToolError):
                return plan_target

            is_plan_file_edit = plan_target.is_plan_target
            if err := check_file_mutation_allowed(
                self._runtime, is_plan_artifact=is_plan_file_edit
            ):
                return err

            if not await p.exists():
                if is_plan_file_edit:
                    return ToolError(
                        message=(
                            "The current plan file does not exist yet. "
                            "Use WriteFile to create it before calling StrReplaceFile."
                        ),
                        brief="Plan file not created",
                    )
                return ToolError(
                    message=f"`{params.path}` does not exist.",
                    brief="File not found",
                )
            if not await p.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.",
                    brief="Invalid path",
                )

            # Read the file content
            content = await p.read_text(encoding="utf-8", errors="replace")

            original_content = content
            edits = [params.edit] if isinstance(params.edit, Edit) else params.edit
            if not edits:
                return ToolError(
                    message="At least one edit is required.",
                    brief="No edits provided",
                )

            # Validate and apply the batch in memory first. If any edit is
            # missing or ambiguous, return before writing so the file stays
            # unchanged.
            per_edit_counts: list[int] = []
            for index, edit in enumerate(edits, start=1):
                if not edit.old:
                    return ToolError(
                        message=f"Edit {index}: old string cannot be empty.",
                        brief="Empty old string",
                    )
                if edit.old == edit.new:
                    return ToolError(
                        message=f"Edit {index}: old and new strings are identical.",
                        brief="No-op edit",
                    )

                match_count = content.count(edit.old)
                if match_count == 0:
                    return ToolError(
                        message=(
                            f"No replacements were made for edit {index}: "
                            f"old string {edit.old!r} was not found in the file."
                        ),
                        brief="No replacements made",
                    )
                if match_count > 1 and not edit.replace_all:
                    return ToolError(
                        message=(
                            f"Edit {index}: old string {edit.old!r} occurs {match_count} times. "
                            "Add surrounding context to make it unique, or set replace_all=true."
                        ),
                        brief="Ambiguous replacement",
                    )

                per_edit_counts.append(match_count if edit.replace_all else 1)
                content = self._apply_edit(content, edit)

            if content == original_content:
                return ToolError(
                    message="Edits resulted in no file changes.",
                    brief="No changes",
                )

            diff_blocks: list[DisplayBlock] = await build_diff_blocks(
                str(p), original_content, content
            )

            action = (
                FileActions.EDIT
                if is_within_workspace(p, self._work_dir, self._additional_dirs)
                else FileActions.EDIT_OUTSIDE
            )

            # Plan file edits are auto-approved; all other edits need approval.
            if not is_plan_file_edit:
                result = await self._approval.request(
                    self.name,
                    action,
                    f"Edit file `{p}`",
                    display=diff_blocks,
                )
                if not result:
                    return result.rejection_error()

            from pythinker_code.soul.toolset import emit_current_tool_execution_started

            emit_current_tool_execution_started()
            create_file_restore_point(self._runtime.session, tool_name=self.name, path=str(p))

            # Write the modified content back to the file
            await p.write_text(content, encoding="utf-8", errors="replace")

            # Count changes for success message (tallied per-edit during application).
            total_replacements = sum(per_edit_counts)

            return ToolReturnValue(
                is_error=False,
                output="",
                message=(
                    f"File successfully edited. "
                    f"Applied {len(edits)} edit(s) with {total_replacements} total replacement(s)."
                ),
                display=diff_blocks,
            )

        except Exception as e:
            from pythinker_code.telemetry.errors import report_handled_error

            report_handled_error(e, site="tool.replace", tool="StrReplaceFile")
            logger.warning("StrReplaceFile failed: {path}: {error}", path=params.path, error=e)
            return ToolError(
                message=f"Failed to edit. Error: {e}",
                brief="Failed to edit file",
            )
