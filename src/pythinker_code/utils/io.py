from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def ends_with_newline(path: Path) -> bool:
    """True if *path* is missing/empty or its last byte is a newline.

    A crash mid-append can leave a torn final line with no terminator; a JSONL
    appender that does not repair it glues its next record onto the torn line,
    and readers then skip BOTH records.
    """
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                return True
            f.seek(-1, os.SEEK_END)
            return f.read(1) == b"\n"
    except FileNotFoundError:
        return True


def atomic_json_write(data: Any, path: Path) -> None:
    """Write JSON data to a file atomically using tmp-file + os.replace.

    This prevents data corruption if the process crashes mid-write: either the
    old file is kept intact or the new file is fully committed.
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
