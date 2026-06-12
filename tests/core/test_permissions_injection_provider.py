"""Live permissions-state injection.

The model used to discover policy through denied tool calls; the provider
renders the enforced posture once per state change.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pythinker_code.soul.approval import Approval, ApprovalState
from pythinker_code.soul.dynamic_injections.permissions_state import PermissionsInjectionProvider


def _make_soul(
    *,
    is_subagent: bool = False,
    yolo: bool = False,
    auto: bool = False,
    safe_mode: bool = False,
    approved: set[str] | None = None,
) -> MagicMock:
    soul = MagicMock()
    soul.is_subagent = is_subagent
    runtime = soul.runtime
    runtime.role = "root"
    runtime.subagent_type = None
    runtime.session.state.plan_mode = False
    runtime.config.agent_execution_profile = "default"
    runtime.approval = Approval(
        state=ApprovalState(
            yolo=yolo, auto=auto, safe_mode=safe_mode, auto_approve_actions=approved or set()
        )
    )
    return soul


class TestPermissionsInjectionProvider:
    async def test_injects_posture_on_first_step(self) -> None:
        provider = PermissionsInjectionProvider()

        result = await provider.get_injections([], _make_soul(safe_mode=True))

        assert len(result) == 1
        content = result[0].content
        assert "profile 'implement'" in content
        assert "Safe mode on" in content
        assert "yolo off" in content
        assert "Command shaping" in content

    async def test_does_not_reinject_while_posture_unchanged(self) -> None:
        provider = PermissionsInjectionProvider()
        soul = _make_soul()

        assert len(await provider.get_injections([], soul)) == 1
        assert await provider.get_injections([], soul) == []

    async def test_reinjects_when_yolo_toggles(self) -> None:
        provider = PermissionsInjectionProvider()
        soul = _make_soul()
        await provider.get_injections([], soul)

        soul.runtime.approval.set_yolo(True)
        result = await provider.get_injections([], soul)

        assert len(result) == 1
        assert "yolo on" in result[0].content

    async def test_reinjects_when_session_approval_granted(self) -> None:
        provider = PermissionsInjectionProvider()
        soul = _make_soul()
        await provider.get_injections([], soul)

        soul.runtime.approval.session_approved_actions()  # no-op read
        soul = _make_soul(approved={"run command"})
        provider_result = await provider.get_injections([], soul)

        assert len(provider_result) == 1
        assert "run command" in provider_result[0].content

    async def test_compaction_rearms(self) -> None:
        provider = PermissionsInjectionProvider()
        soul = _make_soul()
        await provider.get_injections([], soul)

        await provider.on_context_compacted()

        assert len(await provider.get_injections([], soul)) == 1

    async def test_auto_toggle_rearms(self) -> None:
        provider = PermissionsInjectionProvider()
        soul = _make_soul()
        await provider.get_injections([], soul)

        await provider.on_auto_changed(True)

        assert len(await provider.get_injections([], soul)) == 1

    async def test_subagents_are_excluded(self) -> None:
        provider = PermissionsInjectionProvider()

        assert await provider.get_injections([], _make_soul(is_subagent=True)) == []

    async def test_plan_mode_renders_plan_profile(self) -> None:
        provider = PermissionsInjectionProvider()
        soul = _make_soul()
        soul.runtime.session.state.plan_mode = True

        result = await provider.get_injections([], soul)

        assert "profile 'plan'" in result[0].content
        assert "File mutation denied" in result[0].content
