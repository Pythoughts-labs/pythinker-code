from __future__ import annotations

import base64
import re
import time
import uuid
from json import JSONDecodeError
from pathlib import Path

from pydantic import BaseModel, ValidationError

from pythinker_code.session import Session
from pythinker_code.utils.io import atomic_json_write

_RESTORE_ID_RE = re.compile(r"^\d+-[0-9a-f]{8}$")

_RESTORE_DIR = "file_restore_points"


class FileRestorePoint(BaseModel):
    id: str
    created_at: float
    tool_name: str
    path: Path
    existed: bool
    content_b64: str | None = None


def _restore_dir(session: Session) -> Path:
    path = session.dir / _RESTORE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _restore_file(session: Session, restore_id: str) -> Path:
    if not _RESTORE_ID_RE.fullmatch(restore_id):
        raise FileNotFoundError(f"Invalid restore id: {restore_id}")
    base = _restore_dir(session)
    candidate = (base / f"{restore_id}.json").resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise FileNotFoundError(f"Restore id escapes restore dir: {restore_id}")
    return candidate


def create_file_restore_point(
    session: Session,
    *,
    tool_name: str,
    path: str | Path,
) -> FileRestorePoint:
    target = Path(path)
    existed = target.exists()
    content_b64 = None
    if existed and target.is_file():
        content_b64 = base64.b64encode(target.read_bytes()).decode("utf-8")

    point = FileRestorePoint(
        id=f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
        created_at=time.time(),
        tool_name=tool_name,
        path=target,
        existed=existed,
        content_b64=content_b64,
    )
    atomic_json_write(point.model_dump(mode="json"), _restore_file(session, point.id))
    return point


def list_file_restore_points(
    session: Session, *, limit: int | None = None
) -> list[FileRestorePoint]:
    points: list[FileRestorePoint] = []
    for path in _restore_dir(session).glob("*.json"):
        try:
            points.append(FileRestorePoint.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    points.sort(key=lambda point: (point.created_at, point.id), reverse=True)
    return points[:limit] if limit is not None else points


def restore_file_restore_point(session: Session, restore_id: str) -> FileRestorePoint:
    restore_path = _restore_file(session, restore_id)
    try:
        point = FileRestorePoint.model_validate_json(restore_path.read_text(encoding="utf-8"))
    except (ValidationError, JSONDecodeError) as exc:
        raise FileNotFoundError(f"Corrupt restore point: {restore_id}") from exc
    work_dir = Path(str(session.work_dir)).resolve()
    target = point.path.resolve()
    if not target.is_relative_to(work_dir):
        raise ValueError(f"Restore target outside workspace: {point.path}")
    if not point.existed:
        point.path.unlink(missing_ok=True)
        return point
    point.path.parent.mkdir(parents=True, exist_ok=True)
    point.path.write_bytes(base64.b64decode(point.content_b64 or ""))
    return point
