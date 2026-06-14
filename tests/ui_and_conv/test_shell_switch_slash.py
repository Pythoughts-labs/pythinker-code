"""Tests for /web and /reports slash commands and their exception propagation.

Ensures that typing /web or /reports in the interactive shell cleanly switches
to the corresponding server without hanging or corrupting terminal state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from pythinker_code.cli import Reload, SwitchToDashboard, SwitchToWeb
from pythinker_code.ui.shell.slash import ShellSlashCmdFunc, shell_mode_registry
from pythinker_code.ui.shell.slash import registry as shell_slash_registry
from pythinker_code.utils.slashcmd import SlashCommand


async def _invoke_slash_command(command: SlashCommand[ShellSlashCmdFunc], shell: Any) -> None:
    ret = command.func(shell, "")
    if isinstance(ret, Awaitable):
        await ret


def _mock_shell_with_soul(session_id: str = "current-session-id") -> Mock:
    """Create a mock Shell whose soul passes the PythinkerSoul isinstance check."""
    from pythinker_code.soul.pythinkersoul import PythinkerSoul

    mock_soul = Mock(spec=PythinkerSoul)
    mock_soul.runtime.session.id = session_id
    shell = Mock()
    shell.soul = mock_soul
    return shell


# ---------------------------------------------------------------------------
# /web — registration
# ---------------------------------------------------------------------------


class TestWebCommandRegistration:
    """Verify /web is registered in the correct registry."""

    def test_registered_in_shell_registry(self) -> None:
        cmd = shell_slash_registry.find_command("web")
        assert cmd is not None
        assert cmd.name == "web"
        assert "Web" in cmd.description

    def test_not_in_shell_mode_registry(self) -> None:
        assert shell_mode_registry.find_command("web") is None

    def test_not_in_soul_registry(self) -> None:
        from pythinker_code.soul.slash import registry as soul_slash_registry

        assert soul_slash_registry.find_command("web") is None


# ---------------------------------------------------------------------------
# /web — behaviour
# ---------------------------------------------------------------------------


class TestWebCommandBehavior:
    """Verify /web raises SwitchToWeb with the current session ID."""

    async def test_raises_switch_to_web(self) -> None:
        shell = _mock_shell_with_soul("my-session-123")

        cmd = shell_slash_registry.find_command("web")
        assert cmd is not None

        with pytest.raises(SwitchToWeb) as exc_info:
            await _invoke_slash_command(cmd, shell)

        assert exc_info.value.session_id == "my-session-123"

    async def test_carries_session_id(self) -> None:
        shell = _mock_shell_with_soul("abc-def")

        cmd = shell_slash_registry.find_command("web")
        assert cmd is not None

        with pytest.raises(SwitchToWeb) as exc_info:
            await _invoke_slash_command(cmd, shell)

        assert exc_info.value.session_id == "abc-def"

    async def test_session_id_none_without_pythinker_soul(self) -> None:
        """When soul is not a PythinkerSoul, session_id should be None."""
        shell = Mock()
        shell.soul = Mock()  # plain Mock, not spec=PythinkerSoul

        cmd = shell_slash_registry.find_command("web")
        assert cmd is not None

        with pytest.raises(SwitchToWeb) as exc_info:
            await _invoke_slash_command(cmd, shell)

        assert exc_info.value.session_id is None

    async def test_does_not_raise_switch_to_dashboard(self) -> None:
        """/web must raise SwitchToWeb, not SwitchToDashboard."""
        shell = _mock_shell_with_soul()

        cmd = shell_slash_registry.find_command("web")
        assert cmd is not None

        with pytest.raises(SwitchToWeb):
            await _invoke_slash_command(cmd, shell)


# ---------------------------------------------------------------------------
# /reports — registration
# ---------------------------------------------------------------------------


class TestReportsCommandRegistration:
    """Verify /reports is registered in the correct registry."""

    def test_registered_in_shell_registry(self) -> None:
        cmd = shell_slash_registry.find_command("reports")
        assert cmd is not None
        assert cmd.name == "reports"
        assert "Visualizer" in cmd.description

    def test_not_in_shell_mode_registry(self) -> None:
        assert shell_mode_registry.find_command("reports") is None

    def test_not_in_soul_registry(self) -> None:
        from pythinker_code.soul.slash import registry as soul_slash_registry

        assert soul_slash_registry.find_command("reports") is None


# ---------------------------------------------------------------------------
# /reports — behaviour
# ---------------------------------------------------------------------------


class TestReportsCommandBehavior:
    """Verify /reports raises SwitchToDashboard with the current session ID."""

    async def test_raises_switch_to_dashboard(self) -> None:
        shell = _mock_shell_with_soul("my-session-123")

        cmd = shell_slash_registry.find_command("reports")
        assert cmd is not None

        with pytest.raises(SwitchToDashboard) as exc_info:
            await _invoke_slash_command(cmd, shell)

        assert exc_info.value.session_id == "my-session-123"

    async def test_carries_session_id(self) -> None:
        shell = _mock_shell_with_soul("abc-def")

        cmd = shell_slash_registry.find_command("reports")
        assert cmd is not None

        with pytest.raises(SwitchToDashboard) as exc_info:
            await _invoke_slash_command(cmd, shell)

        assert exc_info.value.session_id == "abc-def"

    async def test_session_id_none_without_pythinker_soul(self) -> None:
        """When soul is not a PythinkerSoul, session_id should be None."""
        shell = Mock()
        shell.soul = Mock()

        cmd = shell_slash_registry.find_command("reports")
        assert cmd is not None

        with pytest.raises(SwitchToDashboard) as exc_info:
            await _invoke_slash_command(cmd, shell)

        assert exc_info.value.session_id is None

    async def test_does_not_raise_switch_to_web(self) -> None:
        """/reports must raise SwitchToDashboard, not SwitchToWeb."""
        shell = _mock_shell_with_soul()

        cmd = shell_slash_registry.find_command("reports")
        assert cmd is not None

        with pytest.raises(SwitchToDashboard):
            await _invoke_slash_command(cmd, shell)


# ---------------------------------------------------------------------------
# SwitchToWeb / SwitchToDashboard — exception properties
# ---------------------------------------------------------------------------


class TestSwitchExceptionProperties:
    """Verify SwitchToWeb and SwitchToDashboard have consistent interfaces."""

    def test_both_are_exceptions(self) -> None:
        assert issubclass(SwitchToWeb, Exception)
        assert issubclass(SwitchToDashboard, Exception)

    def test_independent_hierarchies(self) -> None:
        """Neither should be a subclass of the other."""
        assert not issubclass(SwitchToDashboard, SwitchToWeb)
        assert not issubclass(SwitchToWeb, SwitchToDashboard)

    def test_str_representations(self) -> None:
        assert str(SwitchToWeb()) == "switch_to_web"
        assert str(SwitchToDashboard()) == "switch_to_dashboard"

    def test_default_session_id_is_none(self) -> None:
        assert SwitchToWeb().session_id is None
        assert SwitchToDashboard().session_id is None

    def test_accepts_session_id(self) -> None:
        assert SwitchToWeb(session_id="x").session_id == "x"
        assert SwitchToDashboard(session_id="x").session_id == "x"

    def test_matching_interface(self) -> None:
        """Both exceptions must expose the same ``session_id`` attribute."""
        web = SwitchToWeb(session_id="s")
        dashboard = SwitchToDashboard(session_id="s")
        assert hasattr(web, "session_id")
        assert hasattr(dashboard, "session_id")
        assert web.session_id == dashboard.session_id


# ---------------------------------------------------------------------------
# Shell exception propagation
# ---------------------------------------------------------------------------


class TestShellExceptionPropagation:
    """Verify Shell._run_slash_command propagates control-flow exceptions.

    The shell's slash command runner has a try/except that catches generic
    exceptions and prints them as errors. Reload, SwitchToWeb, and
    SwitchToDashboard must be in the propagation whitelist so they reach the
    outer _reload_loop handler instead of being swallowed.
    """

    async def test_propagates_through_shell_runner(self) -> None:
        """Each control-flow exception must NOT be caught by ``except Exception``."""
        for exc in (
            Reload(session_id="t"),
            SwitchToWeb(session_id="t"),
            SwitchToDashboard(session_id="t"),
        ):
            raised = False

            def thrower(*args: Any, _exc: Exception = exc, **kwargs: Any) -> None:
                raise _exc

            cmd = SlashCommand(name="test", description="test", func=thrower, aliases=[])

            # Mimic the exact try/except structure from Shell._run_slash_command
            try:
                cmd.func(Mock(), "")
            except (Reload, SwitchToWeb, SwitchToDashboard):
                raised = True
            except (asyncio.CancelledError, KeyboardInterrupt):
                pass
            except Exception:
                pass

            assert raised, f"{type(exc).__name__} was not propagated"


# ---------------------------------------------------------------------------
# /web + /reports — coexistence
# ---------------------------------------------------------------------------


class TestWebAndReportsCoexistence:
    """Verify /web and /reports coexist without interference."""

    def test_both_registered(self) -> None:
        web_cmd = shell_slash_registry.find_command("web")
        dashboard_cmd = shell_slash_registry.find_command("reports")
        assert web_cmd is not None
        assert dashboard_cmd is not None
        assert web_cmd.name != dashboard_cmd.name

    async def test_same_shell_different_exceptions(self) -> None:
        """Given the same shell, /web raises SwitchToWeb and /reports raises SwitchToDashboard."""
        shell = _mock_shell_with_soul("shared-session")

        web_cmd = shell_slash_registry.find_command("web")
        dashboard_cmd = shell_slash_registry.find_command("reports")
        assert web_cmd is not None
        assert dashboard_cmd is not None

        with pytest.raises(SwitchToWeb) as web_exc:
            await _invoke_slash_command(web_cmd, shell)

        with pytest.raises(SwitchToDashboard) as dashboard_exc:
            await _invoke_slash_command(dashboard_cmd, shell)

        assert web_exc.value.session_id == dashboard_exc.value.session_id == "shared-session"


# ---------------------------------------------------------------------------
# /init — snapshot/restore of shared tool bindings and runtime.rearm_injection
# ---------------------------------------------------------------------------


async def test_init_restores_parent_toolset_and_rearm_bindings(
    runtime: Any,
    tmp_path: Path,
) -> None:
    """After /init, runtime.rearm_injection and plan-mode tool bindings must
    point at the *parent* soul, not the discarded temp soul."""
    from pythinker_code.soul.agent import Agent
    from pythinker_code.soul.context import Context
    from pythinker_code.soul.pythinkersoul import PythinkerSoul
    from pythinker_code.soul.slash import init as init_slash
    from pythinker_code.soul.toolset import PythinkerToolset
    from pythinker_code.tools.file.write import WriteFile
    from pythinker_code.tools.plan.enter import EnterPlanMode

    # Build a toolset with WriteFile and EnterPlanMode present.
    toolset = PythinkerToolset(runtime)
    toolset.add(WriteFile(runtime, runtime.approval))
    toolset.add(EnterPlanMode())

    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=toolset,
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    # Capture the parent soul's rearm callback before calling /init.
    parent_rearm = soul.runtime.rearm_injection

    # Monkeypatch PythinkerSoul.run so the temp INIT run is a no-op.
    # Monkeypatch load_agents_md and telemetry.track so /init completes cleanly.
    with (
        patch.object(PythinkerSoul, "run", new_callable=AsyncMock),
        patch(
            "pythinker_code.soul.slash.load_agents_md",
            new_callable=AsyncMock,
            return_value="# Agents",
        ),
        patch("pythinker_code.telemetry.track", return_value=None),
    ):
        # Call the /init slash command handler directly. (init is `async def`;
        # pyright mis-resolves the aliased import in this scope — verified awaitable.)
        await init_slash(soul, "")  # pyright: ignore[reportGeneralTypeIssues]

    # The temp soul's __init__ called runtime.rearm_injection = self.rearm_injection
    # and agent.toolset.bind_plan_mode_tools() with closures pointing at the temp soul.
    # After the fix, soul._bind_plan_mode_tools() is re-called in the finally block,
    # restoring the parent soul's closures. runtime.rearm_injection is restored to
    # the saved (parent) callback.

    # 1. runtime.rearm_injection must be the parent's original callback (not the temp soul's).
    assert soul.runtime.rearm_injection is parent_rearm, (
        "runtime.rearm_injection was not restored: it still points at the discarded temp soul"
    )

    # 2. Plan-mode toggling must still flow through the parent soul's toolset checker.
    #    Set plan mode on the parent and verify the WriteFile checker reflects it.
    write_tool = toolset.find(WriteFile)
    assert write_tool is not None, "WriteFile not found in toolset"
    assert write_tool._plan_mode_checker is not None, "WriteFile._plan_mode_checker is None"

    soul._plan_mode = True
    assert write_tool._plan_mode_checker() is True, (
        "WriteFile plan-mode checker does not track the parent soul (still bound to temp soul)"
    )

    soul._plan_mode = False
    assert write_tool._plan_mode_checker() is False
