from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pythinker_code.cli import (
    _load_mcp_configs_from_cli_inputs,
    _yaml_files_with_misplaced_mcp_servers,
)
from pythinker_code.cli.vis import cli as vis_cli
from pythinker_code.cli.web import cli as web_cli


def test_load_mcp_configs_rechecks_default_file_between_reloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reload must see MCP servers added after process startup."""
    default_mcp_file = tmp_path / "mcp" / "global.json"
    monkeypatch.setattr(
        "pythinker_code.cli.mcp.get_global_mcp_config_file", lambda: default_mcp_file
    )

    assert not default_mcp_file.exists()
    assert _load_mcp_configs_from_cli_inputs(None, None) == []

    default_mcp_file.parent.mkdir(parents=True, exist_ok=True)
    expected = {
        "mcpServers": {"context7": {"url": "https://mcp.example.test", "transport": "http"}}
    }
    default_mcp_file.write_text(json.dumps(expected), encoding="utf-8")

    assert _load_mcp_configs_from_cli_inputs(None, None) == [expected]


def test_detects_misplaced_mcp_servers_in_yaml_configs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`mcpServers` in a config.yaml (global or project) is flagged, since
    Pythinker reads MCP only from mcp.json and would otherwise drop it silently."""
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setattr(
        "pythinker_code.cli.mcp.get_global_mcp_config_file", lambda: share / "mcp.json"
    )
    (share / "config.yaml").write_text("mcpServers:\n  foo:\n    command: npx\n", encoding="utf-8")

    project = tmp_path / "proj"
    (project / ".pythinker").mkdir(parents=True)
    (project / ".git").mkdir()
    (project / ".pythinker" / "config.yaml").write_text(
        "mcpServers:\n  bar:\n    command: npx\n", encoding="utf-8"
    )
    monkeypatch.chdir(project)

    found = {p.resolve() for p in _yaml_files_with_misplaced_mcp_servers()}
    assert (share / "config.yaml").resolve() in found
    assert (project / ".pythinker" / "config.yaml").resolve() in found


def test_clean_yaml_config_is_not_flagged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A config.yaml without an `mcpServers` block must not be flagged."""
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setattr(
        "pythinker_code.cli.mcp.get_global_mcp_config_file", lambda: share / "mcp.json"
    )
    (share / "config.yaml").write_text(
        "onboarding:\n  seen:\n    busy_input_prompt: true\n", encoding="utf-8"
    )
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)

    assert _yaml_files_with_misplaced_mcp_servers() == []


def test_load_mcp_configs_ignores_misplaced_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stray mcpServers-in-config.yaml must not break loading or leak into the
    returned configs — only the real mcp.json is loaded."""
    share = tmp_path / "share"
    share.mkdir()
    mcp_file = share / "mcp.json"
    monkeypatch.setattr("pythinker_code.cli.mcp.get_global_mcp_config_file", lambda: mcp_file)
    expected = {"mcpServers": {"ctx": {"url": "https://mcp.example.test", "transport": "http"}}}
    mcp_file.write_text(json.dumps(expected), encoding="utf-8")
    (share / "config.yaml").write_text(
        "mcpServers:\n  ignored:\n    command: npx\n", encoding="utf-8"
    )
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)

    assert _load_mcp_configs_from_cli_inputs(None, None) == [expected]


def test_web_dash_h_shows_help_not_host() -> None:
    """-h on web/vis CLIs must show help (exit 0), not demand a host argument (exit 2)."""
    runner = CliRunner()

    # web: -h shows help
    result = runner.invoke(web_cli, ["-h"], color=False)
    assert result.exit_code == 0, f"web -h exit_code={result.exit_code!r}, output={result.output!r}"
    assert "Usage" in result.output

    # web: -H sets host without error
    result_h = runner.invoke(web_cli, ["-H", "1.2.3.4", "--help"], color=False)
    assert result_h.exit_code == 0

    # vis: -h shows help
    result_vis = runner.invoke(vis_cli, ["-h"], color=False)
    assert result_vis.exit_code == 0, (
        f"vis -h exit_code={result_vis.exit_code!r}, output={result_vis.output!r}"
    )
    assert "Usage" in result_vis.output

    # vis: -H sets host without error
    result_vis_h = runner.invoke(vis_cli, ["-H", "1.2.3.4", "--help"], color=False)
    assert result_vis_h.exit_code == 0
