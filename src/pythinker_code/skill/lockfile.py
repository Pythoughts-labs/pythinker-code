from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pythinker_code.skill import Skill, normalize_skill_name, read_skill_text

LOCKFILE_NAME = "skills-lock.json"


class SkillLockEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill_path: str = Field(alias="skillPath")
    computed_hash: str = Field(alias="computedHash")
    source: str = "local"
    source_type: str = Field(default="local", alias="sourceType")


class SkillLockFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    skills: dict[str, SkillLockEntry] = Field(default_factory=dict)


def skill_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _display_skill_path(path: Path, project_root: Path | None) -> str:
    if project_root is None:
        return str(path)
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


async def lock_entry_for_skill(
    skill: Skill, *, project_root: Path | None = None
) -> SkillLockEntry | None:
    content = await read_skill_text(skill)
    if content is None:
        return None
    return SkillLockEntry(
        skillPath=_display_skill_path(Path(str(skill.skill_md_file)), project_root),
        computedHash=skill_content_hash(content),
        source=skill.scope,
        sourceType=skill.scope,
    )


async def build_skill_lock(
    skills: dict[str, Skill], *, project_root: Path | None = None
) -> SkillLockFile:
    entries: dict[str, SkillLockEntry] = {}
    for skill in sorted(skills.values(), key=lambda item: normalize_skill_name(item.name)):
        entry = await lock_entry_for_skill(skill, project_root=project_root)
        if entry is not None:
            entries[skill.name] = entry
    return SkillLockFile(skills=entries)


def load_skill_lock(path: Path) -> SkillLockFile:
    return SkillLockFile.model_validate_json(path.read_text(encoding="utf-8"))


def write_skill_lock(path: Path, lock: SkillLockFile) -> None:
    path.write_text(
        lock.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )


async def verify_skill_lock(skills: dict[str, Skill], lock: SkillLockFile) -> list[str]:
    errors: list[str] = []
    for name, entry in sorted(lock.skills.items()):
        skill = skills.get(normalize_skill_name(name))
        if skill is None:
            errors.append(f"missing skill: {name}")
            continue
        current = await lock_entry_for_skill(skill)
        if current is None:
            errors.append(f"unreadable skill: {name}")
            continue
        if current.computed_hash != entry.computed_hash:
            errors.append(f"hash mismatch: {name}")
    return errors
