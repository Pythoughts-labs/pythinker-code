"""mode-1 + skills-2: the agent-creator and customize-pythinker builtin skills load.

These are content-only builtin skills; the regression risk is malformed frontmatter that
silently drops the skill from discovery. Assert both are discovered and parse cleanly.
"""

from __future__ import annotations

import pytest
from pythinker_host.path import HostPath

from pythinker_code.skill import discover_skills, get_builtin_skills_dir


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["agent-creator", "customize-pythinker", "designer-skill"])
async def test_authoring_skill_is_discovered_builtin(name: str) -> None:
    skills = await discover_skills(
        HostPath.unsafe_from_local_path(get_builtin_skills_dir()), scope="builtin"
    )
    by_name = {s.name: s for s in skills}

    assert name in by_name, f"{name} not discovered among builtin skills"
    skill = by_name[name]
    assert skill.scope == "builtin"
    assert skill.type == "standard"
    # Frontmatter description must be present (it is the skill's trigger) and bounded.
    assert skill.description.strip()
    assert len(skill.description) <= 1024
