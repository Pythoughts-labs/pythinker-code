from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Generator
from hashlib import md5
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pythinker_host import get_current_host
from pythinker_host.local import local_host
from pythinker_host.path import HostPath

from pythinker_code.share import get_share_dir
from pythinker_code.utils.io import atomic_json_write
from pythinker_code.utils.logging import logger


def get_metadata_file() -> Path:
    return get_share_dir() / "pythinker.json"


class WorkDirMeta(BaseModel):
    """Metadata for a work directory."""

    path: str
    """The full path of the work directory."""

    host: str = local_host.name
    """The name of the host backend where the work directory is located."""

    last_session_id: str | None = None
    """Last session ID of this work directory."""

    @property
    def sessions_dir(self) -> Path:
        """The directory to store sessions for this work directory."""
        path_md5 = md5(self.path.encode(encoding="utf-8"), usedforsecurity=False).hexdigest()
        dir_basename = path_md5 if self.host == local_host.name else f"{self.host}_{path_md5}"
        session_dir = get_share_dir() / "sessions" / dir_basename
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir


class Metadata(BaseModel):
    """Pythinker metadata structure."""

    model_config = ConfigDict(extra="ignore")

    work_dirs: list[WorkDirMeta] = Field(default_factory=list[WorkDirMeta])
    """Work directory list."""

    def get_work_dir_meta(self, path: HostPath) -> WorkDirMeta | None:
        """Get the metadata for a work directory."""
        for wd in self.work_dirs:
            if wd.path == str(path) and wd.host == get_current_host().name:
                return wd
        return None

    def new_work_dir_meta(self, path: HostPath) -> WorkDirMeta:
        """Create a new work directory metadata."""
        wd_meta = WorkDirMeta(path=str(path), host=get_current_host().name)
        self.work_dirs.append(wd_meta)
        return wd_meta


def load_metadata() -> Metadata:
    metadata_file = get_metadata_file()
    logger.debug("Loading metadata from file: {file}", file=metadata_file)
    if not metadata_file.exists():
        logger.debug("No metadata file found, creating empty metadata")
        return Metadata()
    with open(metadata_file, encoding="utf-8") as f:
        data = json.load(f)
        return Metadata(**data)


def save_metadata(metadata: Metadata):
    metadata_file = get_metadata_file()
    logger.debug("Saving metadata to file: {file}", file=metadata_file)
    atomic_json_write(metadata.model_dump(), metadata_file)


@contextlib.contextmanager
def _metadata_lock() -> Generator[None]:
    """Cross-process lock for read-modify-write cycles on pythinker.json.

    atomic_json_write prevents torn files but not lost updates: two processes
    that both load before either saves drop each other's changes — e.g. a
    freshly registered work_dir vanishing, making its sessions unreachable.
    The lock file is kept on disk (unlinking would split the lock across
    inodes; see scratchpad._exclude_lock).
    """
    lock_file = get_metadata_file().with_name("pythinker.json.lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_file.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl
        except ImportError:
            yield
        else:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                with contextlib.suppress(OSError):
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def mutate_metadata[MutateResult](mutate: Callable[[Metadata], MutateResult]) -> MutateResult:
    """Atomically load → mutate → save the shared metadata index.

    *mutate* runs under a cross-process lock; whatever it returns is passed
    through. Blocking (flock + small JSON I/O) — call via asyncio.to_thread
    from event-loop code.
    """
    with _metadata_lock():
        metadata = load_metadata()
        result = mutate(metadata)
        save_metadata(metadata)
        return result
