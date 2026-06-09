"""mcpext-3: inject --rm into docker/podman stdio MCP launch commands.

A stdio MCP server configured as `docker run ...` leaves a stopped container behind
on teardown unless --rm is present; killing the client process does not remove the
daemon-managed container. ensure_docker_rm adds --rm so the container is cleaned up.
"""

from __future__ import annotations

import pytest

from pythinker_code.cli.mcp import ensure_docker_rm


@pytest.mark.parametrize("cmd", ["docker", "podman"])
def test_injects_rm_after_run(cmd: str) -> None:
    args = ensure_docker_rm(cmd, ["run", "-i", "ghcr.io/example/mcp"])
    assert args == ["run", "--rm", "-i", "ghcr.io/example/mcp"]


def test_keeps_existing_rm() -> None:
    original = ["run", "--rm", "-i", "img"]
    assert ensure_docker_rm("docker", original) == original


def test_ignores_non_run_docker_subcommand() -> None:
    args = ["ps", "-a"]
    assert ensure_docker_rm("docker", args) == args


def test_ignores_non_container_runtime() -> None:
    args = ["mcp-server", "--port", "3000"]
    assert ensure_docker_rm("npx", args) == args


def test_handles_empty_args() -> None:
    assert ensure_docker_rm("docker", []) == []


def test_full_path_runtime_is_recognized() -> None:
    # A docker binary referenced by path should still be treated as docker.
    args = ensure_docker_rm("/usr/bin/docker", ["run", "img"])
    assert args == ["run", "--rm", "img"]
