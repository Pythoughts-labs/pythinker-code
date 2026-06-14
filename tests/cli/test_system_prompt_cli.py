"""Tests for `pythinker system-prompt` agent resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer

from pythinker_code.agentspec import DEFAULT_AGENT_FILE
from pythinker_code.cli.system_prompt import _resolve_agent_file


def test_resolve_default_agent() -> None:
    assert _resolve_agent_file("default") == DEFAULT_AGENT_FILE


def test_resolve_builtin_role_agent() -> None:
    # Built-in role specs live alongside the default agent as default/<name>.yaml.
    resolved = _resolve_agent_file("coder")
    assert resolved == DEFAULT_AGENT_FILE.parent / "coder.yaml"
    assert resolved.exists()


def test_resolve_unknown_agent_raises() -> None:
    with pytest.raises(typer.BadParameter):
        _resolve_agent_file("does-not-exist-xyz")


def test_system_prompt_uses_project_config_without_user_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: system-prompt must merge project-scoped config even when no
    user config file exists, and must not create the user config as a side effect.

    Old behaviour: fell back to a bare ``Config()`` when ``~/.pythinker/config.toml``
    was absent, so project-scoped values (e.g. ``extra_skill_dirs``) were silently
    dropped.  Fix: calls ``load_config(persist=False)`` which runs the full
    user+project+local merge pipeline read-only.
    """
    # ── project dir with a .git marker so find_project_root() resolves ──────
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    pythinker_dir = project / ".pythinker"
    pythinker_dir.mkdir()
    (pythinker_dir / "config.toml").write_text(
        'extra_skill_dirs = ["/tmp/proj-only-skill-dir"]\n', encoding="utf-8"
    )

    # ── chdir into the project so load_config() picks up the project scope ──
    monkeypatch.chdir(project)

    # ── the autouse _isolate_share_dir fixture points PYTHINKER_SHARE_DIR at
    #    a fresh empty tmp dir, so no user config.toml exists there ──────────

    # ── spy: replace render_agent_system_prompt with an async stub that
    #    records the config arg.  Patch the source module because the CLI
    #    imports it lazily inside the callback. ────────────────────────────────
    captured: dict[str, Any] = {}

    async def _spy_render(agent_file: Path, work_dir: Any, config: Any) -> str:
        captured["config"] = config
        return "STUBBED PROMPT"

    monkeypatch.setattr(
        "pythinker_code.soul.agent.render_agent_system_prompt",
        _spy_render,
    )

    # ── invoke the CLI callback directly (matches existing file style) ───────
    from pythinker_code.cli.system_prompt import system_prompt

    system_prompt(agent_file=DEFAULT_AGENT_FILE, work_dir=project)

    # ── the spy must have been called ────────────────────────────────────────
    assert "config" in captured, "render_agent_system_prompt was never called"

    # ── project-scoped value must be present in the resolved config ──────────
    # On the old Config() fallback extra_skill_dirs == [] (default), so this fails.
    assert captured["config"].extra_skill_dirs == ["/tmp/proj-only-skill-dir"]

    # ── project scope must appear in source_scopes (further proof of merge) ──
    assert "project" in captured["config"].source_scopes

    # ── no user config.toml must have been seeded as a side effect ───────────
    from pythinker_code.config import get_config_file

    assert not get_config_file(create=False).expanduser().resolve(strict=False).exists()
