import json
from collections.abc import Callable
from dataclasses import dataclass
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
from pythinker_code.tools.file import classify_edit_action
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


def _crlf_translated_edit(content: str, edit: Edit) -> Edit | None:
    """CRLF-translated variant of *edit* when the file is CRLF and the LF needle missed.

    Files are read with newline='' so CRLF joints survive verbatim, while models
    overwhelmingly echo multi-line old strings LF-joined (the \\r is invisible in
    the numbered ReadFile output). Translating the needle — and the replacement,
    unless it already carries CRLF — keeps multi-line edits working without
    silently rewriting the file's line endings.
    """
    if "\r\n" not in content or "\n" not in edit.old or "\r" in edit.old:
        return None
    old = edit.old.replace("\n", "\r\n")
    if old not in content:
        return None
    new = edit.new if "\r" in edit.new else edit.new.replace("\n", "\r\n")
    return Edit(old=old, new=new, replace_all=edit.replace_all)


_SMART_PUNCTUATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
)

# Graduated relaxations for edit-location recovery, in strictness order.
# Each tier normalizes one drift class the model cannot see in numbered
# ReadFile output; the first tier with hits wins.
_FUZZY_TIERS: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("trailing-whitespace", str.rstrip),
    ("indentation", str.strip),
    ("unicode-punctuation", lambda line: line.translate(_SMART_PUNCTUATION).strip()),
)


@dataclass(frozen=True)
class _FuzzyResult:
    content: str
    tier: str
    count: int


def _line_body(line: str) -> str:
    return line.rstrip("\r\n")


def _find_fuzzy_windows(
    file_lines: list[str], needle_lines: list[str], normalize: Callable[[str], str]
) -> list[int]:
    targets = [normalize(line) for line in needle_lines]
    width = len(targets)
    hits: list[int] = []
    index = 0
    while index <= len(file_lines) - width:
        if all(
            normalize(_line_body(file_lines[index + offset])) == targets[offset]
            for offset in range(width)
        ):
            hits.append(index)
            index += width  # non-overlapping
        else:
            index += 1
    return hits


def apply_fuzzy_edit(content: str, edit: Edit) -> _FuzzyResult | ToolError | None:
    """Line-window relaxation ladder once exact (and CRLF) matching missed.

    Replaces the ACTUAL matched file slice, never the needle text; the
    replacement adopts the slice's line-ending style (CRLF preserved) and
    its trailing newline so the following line never glues on. Multiple
    hits at the firing tier without replace_all keep the ambiguity-error
    contract. Returns None when no tier matches.
    """
    needle_lines = edit.old.splitlines()
    if not needle_lines:
        return None
    file_lines = content.splitlines(keepends=True)
    for tier, normalize in _FUZZY_TIERS:
        hits = _find_fuzzy_windows(file_lines, needle_lines, normalize)
        if not hits:
            continue
        if len(hits) > 1 and not edit.replace_all:
            return ToolError(
                message=(
                    f"old string {edit.old!r} occurs {len(hits)} times under "
                    f"{tier}-relaxed matching. Add surrounding context to make it "
                    "unique, or set replace_all=true."
                ),
                brief="Ambiguous replacement",
            )
        width = len(needle_lines)
        rebuilt: list[str] = []
        cursor = 0
        for start in hits:
            rebuilt.extend(file_lines[cursor:start])
            slice_lines = file_lines[start : start + width]
            replacement = edit.new
            if any("\r\n" in line for line in slice_lines) and "\r" not in replacement:
                replacement = replacement.replace("\n", "\r\n")
            last = slice_lines[-1]
            ending = "\r\n" if last.endswith("\r\n") else "\n" if last.endswith("\n") else ""
            if ending and not replacement.endswith(("\n", "\r\n")):
                replacement += ending
            rebuilt.append(replacement)
            cursor = start + width
        rebuilt.extend(file_lines[cursor:])
        return _FuzzyResult(content="".join(rebuilt), tier=tier, count=len(hits))
    return None


class StrReplaceFile(CallableTool2[Params]):
    name: str = "StrReplaceFile"
    description: str = _BASE_DESCRIPTION
    params: type[Params] = Params
    emits_tool_execution_started_after_approval = True

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

    def _validate_path(
        self,
        path: HostPath,
        real_p: HostPath,
        real_work: HostPath,
        real_add: list[HostPath],
    ) -> ToolError | None:
        """Validate that the path is safe to edit.

        Uses `real_p` (symlink-resolved) for workspace checks while `path` is kept for
        user-facing messages so reported paths remain unchanged. The resolved
        workspace roots come from the caller so they are realpath'd only once.
        """
        if not is_within_workspace(real_p, real_work, real_add) and not path.is_absolute():
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
            raw = HostPath(params.path).expanduser()
            # Relative tool paths resolve against the runtime work dir
            # (override-aware), NOT the process cwd — an isolated child's
            # relative write must land in its worktree. `raw` keeps the
            # original form: the workspace-escape rule for relative paths
            # checks (and reports) what the caller actually passed.
            base_joined = raw if raw.is_absolute() else self._work_dir.joinpath(str(raw))
            p = base_joined.canonical()

            # Resolve the real (symlink-followed) path for security checks only.
            # os.path.realpath follows symlinks at every component including the leaf.
            real_p = await p.realpath()
            real_work = await self._work_dir.realpath()
            real_add = [await d.realpath() for d in self._additional_dirs]

            if err := self._validate_path(raw, real_p, real_work, real_add):
                return err

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
            fuzzy_notes: list[str] = []
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
                if match_count == 0 and (crlf_edit := _crlf_translated_edit(content, edit)):
                    edit = crlf_edit
                    match_count = content.count(edit.old)
                if match_count == 0:
                    fuzzy = apply_fuzzy_edit(content, edit)
                    if isinstance(fuzzy, ToolError):
                        return ToolError(
                            message=f"Edit {index}: {fuzzy.message}",
                            brief=fuzzy.brief or "Ambiguous replacement",
                        )
                    if fuzzy is not None:
                        content = fuzzy.content
                        per_edit_counts.append(fuzzy.count if edit.replace_all else 1)
                        fuzzy_notes.append(
                            f"edit {index} matched with {fuzzy.tier}-relaxed matching"
                        )
                        continue
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

            action = classify_edit_action(real_p, real_work, real_add)

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
                    + (f" ({'; '.join(fuzzy_notes)})" if fuzzy_notes else "")
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
