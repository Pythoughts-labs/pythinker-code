from __future__ import annotations

from pathlib import Path

from pythinker_host.path import HostPath

from pythinker_code.skill import Skill
from pythinker_code.tools.skill import ReadSkill


def _skill(name: str, path: Path, scope: str = "user") -> Skill:
    return Skill(
        name=name,
        description=f"{name} description",
        type="standard",
        dir=HostPath.unsafe_from_local_path(path.parent),
        skill_md_file=HostPath.unsafe_from_local_path(path),
        scope=scope,  # type: ignore[arg-type]
    )


async def test_read_skill_returns_core_and_local_specialization(runtime, tmp_path: Path) -> None:
    core_dir = tmp_path / "review-pr"
    core_dir.mkdir()
    core_path = core_dir / "SKILL.md"
    core_path.write_text("Core review workflow", encoding="utf-8")
    local_dir = tmp_path / "review-pr-local"
    local_dir.mkdir()
    local_path = local_dir / "SKILL.md"
    local_path.write_text("Local review rules", encoding="utf-8")
    runtime.skills = {
        "review-pr": _skill("review-pr", core_path, scope="builtin"),
        "review-pr-local": _skill("review-pr-local", local_path, scope="project"),
    }

    result = await ReadSkill(runtime)(ReadSkill.params(skill_name="review-pr"))

    assert not result.is_error
    assert isinstance(result.output, str)
    assert "skill: review-pr" in result.output
    assert "Core review workflow" in result.output
    assert "# Local specialization: review-pr-local" in result.output
    assert "Local review rules" in result.output


async def test_read_skill_reports_missing_skill(runtime) -> None:
    runtime.skills = {}

    result = await ReadSkill(runtime)(ReadSkill.params(skill_name="missing"))

    assert result.is_error
    assert result.brief == "Skill not found"
