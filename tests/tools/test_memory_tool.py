from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pythinker_host.path import HostPath

from pythinker_code.scratchpad import GitResult
from pythinker_code.soul.approval import ApprovalResult


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


class FakeApproval:
    """Stand-in for ``Runtime.approval`` that returns a canned decision and records
    the requests it received, so gate behavior is testable without a live tool-call
    context. Defaults to auto-approve (matching yolo/auto-approve), so unflagged
    writes — which never reach the gate — are unaffected."""

    def __init__(self, result: ApprovalResult | None = None) -> None:
        self._result = result if result is not None else ApprovalResult(approved=True)
        self.requests: list[tuple[str, str, str]] = []

    async def request(self, sender, action, description, display=None) -> ApprovalResult:
        self.requests.append((sender, action, description))
        return self._result


def _runtime(tmp_path, role="root", work_dir=None, approval=None) -> SimpleNamespace:
    session = SimpleNamespace(id="sess1", title="t", work_dir=_hp(tmp_path / "repo"))
    return SimpleNamespace(
        role=role,
        session=session,
        work_dir=work_dir or session.work_dir,
        rearmed=[],
        rearm_injection=lambda key: None,
        approval=approval if approval is not None else FakeApproval(),
    )


def _make_tool(tmp_path, monkeypatch, role="root", approval=None):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path / "share"))
    from pythinker_code.project_memory import ProjectMemoryStore
    from pythinker_code.tools.memory import Memory

    tool = Memory(cast(Any, _runtime(tmp_path, role, approval=approval)))
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


async def test_memory_tool_flagged_write_saves_when_approved(tmp_path, monkeypatch):
    """A correction-shaped write is gated for confirmation; on approval it persists."""
    from pythinker_code.tools.memory import Params

    approval = FakeApproval(ApprovalResult(approved=True))
    tool = _make_tool(tmp_path, monkeypatch, approval=approval)
    res = await tool(
        Params(action="add", target="memory", content="user prefers a conclusion limit of 100")
    )
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == ["user prefers a conclusion limit of 100"]
    # The flagged write went through the confirmation gate.
    assert approval.requests and approval.requests[0][1] == "save to memory"


async def test_memory_tool_flagged_write_declined_redirects_to_file(tmp_path, monkeypatch):
    """When the user declines a flagged write, nothing is stored and the agent is
    told to edit the governing file (with the user's feedback)."""
    from pythinker_code.tools.memory import Params

    approval = FakeApproval(ApprovalResult(approved=False, feedback="edit POST_PROTOCOL.md"))
    tool = _make_tool(tmp_path, monkeypatch, approval=approval)
    res = await tool(
        Params(action="add", target="memory", content="set the conclusion limit to 100")
    )
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == []  # not saved
    assert "project file" in res.message.lower()
    assert "edit POST_PROTOCOL.md" in res.message


async def test_memory_tool_flagged_write_skipped_when_no_user(tmp_path, monkeypatch):
    """With no user available to confirm (e.g. headless), a flagged write is skipped
    cleanly — not stored, and reported as skipped rather than a hard error."""
    from pythinker_code.tools.memory import Params

    approval = FakeApproval(ApprovalResult(approved=False, user_rejection=False))
    tool = _make_tool(tmp_path, monkeypatch, approval=approval)
    res = await tool(
        Params(action="add", target="memory", content="always cap the conclusion at 100 words")
    )
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == []
    assert "no user" in res.message.lower()


async def test_memory_tool_plain_fact_saves_without_gate(tmp_path, monkeypatch):
    """A plain durable fact has no routing signals, so it writes without prompting."""
    from pythinker_code.tools.memory import Params

    approval = FakeApproval()
    tool = _make_tool(tmp_path, monkeypatch, approval=approval)
    res = await tool(Params(action="add", target="memory", content="uses pytest with xdist"))
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == ["uses pytest with xdist"]
    assert approval.requests == []  # no signals -> no confirmation


async def test_memory_tool_file_ref_write_is_gated(tmp_path, monkeypatch):
    """A fact that names a project file trips the file_ref signal and is gated;
    on approval it still saves."""
    from pythinker_code.tools.memory import Params

    approval = FakeApproval(ApprovalResult(approved=True))
    tool = _make_tool(tmp_path, monkeypatch, approval=approval)
    res = await tool(
        Params(action="add", target="memory", content="MCP servers load only from mcp.json")
    )
    assert res.is_error is False
    assert await tool._store.read_entries("memory") == ["MCP servers load only from mcp.json"]
    assert approval.requests and "project file" in approval.requests[0][2].lower()


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
