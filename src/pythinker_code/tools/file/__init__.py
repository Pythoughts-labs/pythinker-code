from collections.abc import Sequence
from enum import StrEnum

from pythinker_host.path import HostPath

from pythinker_code.utils.path import is_config_surface_path, is_within_workspace


class FileOpsWindow:
    """Maintains a window of file operations."""

    pass


class FileActions(StrEnum):
    READ = "read file"
    EDIT = "edit file"
    EDIT_OUTSIDE = "edit file outside of working directory"
    EDIT_CONFIG = "edit pythinker config file"


def classify_edit_action(
    path: HostPath,
    work_dir: HostPath,
    additional_dirs: Sequence[HostPath],
) -> FileActions:
    """Map a write/edit target to its approval action.

    Shared by :class:`WriteFile` and :class:`StrReplaceFile` so the
    outside-workspace / config-surface / ordinary-edit distinction stays
    identical across both tools. Order matters: an outside-workspace path is
    classified before the config-surface check so ``is_config_surface_path``
    only ever sees in-workspace paths.
    """
    if not is_within_workspace(path, work_dir, additional_dirs):
        return FileActions.EDIT_OUTSIDE
    if is_config_surface_path(path, work_dir):
        return FileActions.EDIT_CONFIG
    return FileActions.EDIT


from .glob import Glob  # noqa: E402
from .grep_local import Grep, SmartSearch  # noqa: E402
from .read import ReadFile  # noqa: E402
from .read_media import ReadMediaFile  # noqa: E402
from .replace import StrReplaceFile  # noqa: E402
from .write import WriteFile  # noqa: E402

__all__ = (
    "ReadFile",
    "ReadMediaFile",
    "Glob",
    "Grep",
    "SmartSearch",
    "WriteFile",
    "StrReplaceFile",
)
