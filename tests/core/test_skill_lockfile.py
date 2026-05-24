from __future__ import annotations

from pathlib import Path

from pythinker_host.path import HostPath

from pythinker_code.skill import Skill
from pythinker_code.skill.lockfile import (
    build_skill_lock,
    load_skill_lock,
    verify_skill_lock,
    write_skill_lock,
)


def _skill(name: str, path: Path) -> Skill:
    return Skill(
        name=name,
        description=f"{name} description",
        type="standard",
        dir=HostPath.unsafe_from_local_path(path.parent),
        skill_md_file=HostPath.unsafe_from_local_path(path),
        scope="project",
    )


async def test_skill_lockfile_round_trip_and_verify(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "review-pr"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("Review instructions", encoding="utf-8")
    skills = {"review-pr": _skill("review-pr", skill_file)}

    lock = await build_skill_lock(skills, project_root=tmp_path)
    assert lock.skills["review-pr"].skill_path == "skills/review-pr/SKILL.md"
    lock_path = tmp_path / "skills-lock.json"
    write_skill_lock(lock_path, lock)

    loaded = load_skill_lock(lock_path)
    assert await verify_skill_lock(skills, loaded) == []

    skill_file.write_text("Changed instructions", encoding="utf-8")
    assert await verify_skill_lock(skills, loaded) == ["hash mismatch: review-pr"]


async def test_skill_lockfile_reports_missing_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "review-pr"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("Review instructions", encoding="utf-8")

    lock = await build_skill_lock({"review-pr": _skill("review-pr", skill_file)})

    assert await verify_skill_lock({}, lock) == ["missing skill: review-pr"]
