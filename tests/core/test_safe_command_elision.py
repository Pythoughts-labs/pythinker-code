"""Known-safe read-only command auto-approval (prompt elision).

A positive allowlist, fail closed: every ;/&&/||/| segment must start with
an allowlisted read-only binary (or read-only git subcommand), with the
mutation guard's hidden-command/redirection/network rejections applied
first. Wrappers (sudo/env/time) are never unwrapped — they disqualify.
Absolute command paths must live in a system bin dir so a workspace-local
fake `git` cannot ride the allowlist.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pythinker_code.soul.permission import is_known_safe_command

SAFE = [
    "ls -la",
    "pwd",
    "git status",
    "git log --oneline -5",
    "git diff HEAD~1",
    "cat README.md",
    "grep -rn pattern src",
    "wc -l file.txt",
    "ls | head -3",
    "pwd && git status",
    "FOO=1 grep x file",
    "/usr/bin/git status",
    "echo done",
]

UNSAFE = [
    "rm -rf /tmp/x",
    "git push",
    "git commit -m x",
    "git branch new-branch",
    "git status --output=/tmp/f",
    "git log --output=/tmp/f --oneline",
    "git -c core.pager=rm status",
    "ls > /tmp/out",
    "echo hi >> /tmp/out",
    "ls $(rm -rf /tmp/x)",
    "ls `rm -rf /tmp/x`",
    "ls; rm -rf /tmp/x",
    "ls;rm -rf /tmp/x",
    "ls && rm -rf /tmp/x",
    "git status\nrm -rf /tmp/x",
    "/tmp/fake/git status",
    "./git status",
    "sudo ls",
    "env ls",
    "nohup ls",
    "find . -exec rm {} ;",
    "python -c 'print(1)'",
    "curl http://example.com",
    "ls | tee /tmp/out",
    "sort -o /tmp/out input",
    "",
    "   ",
]


class TestIsKnownSafeCommand:
    @pytest.mark.parametrize("command", SAFE)
    def test_safe_commands_qualify(self, command: str) -> None:
        assert is_known_safe_command(command) is True, command

    @pytest.mark.parametrize("command", UNSAFE)
    def test_unsafe_commands_never_qualify(self, command: str) -> None:
        assert is_known_safe_command(command) is False, repr(command)


class TestShellPromptElision:
    @pytest.mark.asyncio
    async def test_safe_command_skips_approval(self, shell_tool) -> None:
        from pythinker_code.tools.shell import Params

        spy = AsyncMock()
        shell_tool._approval.request = spy  # type: ignore[method-assign]

        result = await shell_tool(Params(command="echo elision-proof"))

        spy.assert_not_awaited()
        assert "elision-proof" in result.output

    @pytest.mark.asyncio
    async def test_unlisted_command_still_requests_approval(self, shell_tool) -> None:
        from pythinker_code.tools.shell import Params

        class _ApprovalReached(Exception):
            pass

        async def _raise(*args: object, **kwargs: object) -> object:
            raise _ApprovalReached

        shell_tool._approval.request = _raise  # type: ignore[method-assign]

        with pytest.raises(_ApprovalReached):
            await shell_tool(Params(command="touch /tmp/should-not-run"))
