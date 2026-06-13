from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pythinker_host.path import HostPath

from pythinker_code.scratchpad import GitResult


def _hp(p: Path) -> HostPath:
    return HostPath.unsafe_from_local_path(p)


class FakeGit:
    def __init__(self, responses):
        self.responses = responses

    async def __call__(self, argv):
        for prefix, result in self.responses.items():
            if tuple(argv[: len(prefix)]) == prefix:
                return result
        return GitResult(ok=True, exit_code=1, stdout="")


def _runtime(tmp_path, role="root", work_dir=None) -> SimpleNamespace:
    session = SimpleNamespace(id="sess1", title="t", work_dir=_hp(tmp_path / "repo"))
    return SimpleNamespace(
        role=role,
        session=session,
        work_dir=work_dir or session.work_dir,
        rearmed=[],
        rearm_injection=lambda key: None,
    )


def _make_tool(tmp_path, monkeypatch, role="root"):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path / "share"))
    from pythinker_code.project_memory import ProjectMemoryStore
    from pythinker_code.tools.memory import Memory

    tool = Memory(cast(Any, _runtime(tmp_path, role)))
    fake = FakeGit({("rev-parse", "--show-toplevel"): GitResult(True, 0, str(tmp_path / "repo"))})
    tool._store = ProjectMemoryStore(_hp(tmp_path / "repo"), git_runner=fake)
    return tool


async def test_memory_tool_add_and_read_back(tmp_path, monkeypatch):
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    calls: list[str] = []
    tool._runtime.rearm_injection = calls.append
    res = await tool(Params(action="add", target="memory", content="uses pytest"))
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == ["uses pytest"]
    assert calls == ["project_memory"]


async def test_memory_tool_list_reports_status(tmp_path, monkeypatch):
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    await tool._store.add("memory", "uses pytest")

    # `list` is read-only: needs no content/old_text and must not rearm injection.
    rearmed: list[str] = []
    tool._runtime.rearm_injection = rearmed.append
    res = await tool(Params(action="list", target="memory"))
    assert res.is_error is False
    assert "uses pytest" in res.output
    assert rearmed == []


async def test_memory_tool_appends_routing_advisory_for_corrections(tmp_path, monkeypatch):
    """A correction-shaped write succeeds (advisory, not block) but carries a
    nudge to edit the governing file instead."""
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    res = await tool(
        Params(action="add", target="memory", content="user prefers a conclusion limit of 100")
    )
    assert res.is_error is False
    # The write still lands — the guard never blocks.
    assert await tool._store.read_entries("memory") == ["user prefers a conclusion limit of 100"]
    assert "edit that file" in res.message.lower()


async def test_memory_tool_no_advisory_for_plain_facts(tmp_path, monkeypatch):
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    res = await tool(Params(action="add", target="memory", content="uses pytest with xdist"))
    assert res.is_error is False
    assert "edit that file" not in res.message.lower()


async def test_memory_tool_locational_fact_saves_with_advisory(tmp_path, monkeypatch):
    """A legit fact that names a file is allowed to save — the file_ref signal
    only earns an advisory, never a rejection."""
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    res = await tool(
        Params(action="add", target="memory", content="MCP servers load only from mcp.json")
    )
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == ["MCP servers load only from mcp.json"]
    assert "edit that file" in res.message.lower()


async def test_memory_tool_remove_by_index(tmp_path, monkeypatch):
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    await tool._store.add("memory", "uses pytest")
    await tool._store.add("memory", "uses ruff")
    res = await tool(Params(action="remove", target="memory", index=0))
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == ["uses ruff"]


async def test_memory_tool_remove_needs_locator(tmp_path, monkeypatch):
    """remove/replace require either old_text or index."""
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    res = await tool(Params(action="remove", target="memory"))
    assert res.is_error is True
    assert "index" in res.message.lower()


async def test_memory_tool_missing_content_errors(tmp_path, monkeypatch):
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch)
    res = await tool(Params(action="add", target="memory", content=None))
    assert res.is_error is True


async def test_memory_tool_blocks_subagent(tmp_path, monkeypatch):
    from pythinker_code.tools.memory import Params

    tool = _make_tool(tmp_path, monkeypatch, role="subagent")
    res = await tool(Params(action="add", target="memory", content="x"))
    assert res.is_error is True
    assert "root" in res.message.lower()


def test_memory_tool_uses_runtime_work_dir_seam(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path / "share"))
    from pythinker_code.tools.memory import Memory

    runtime = _runtime(tmp_path, work_dir=_hp(tmp_path / "different_repo"))
    tool = Memory(cast(Any, runtime))

    assert tool._store._work_dir == runtime.work_dir
    assert tool._store._work_dir != runtime.session.work_dir
