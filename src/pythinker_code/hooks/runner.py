from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Literal, cast

from pythinker_code.utils.logging import logger


@dataclass
class HookResult:
    """Result of a single hook execution."""

    action: Literal["allow", "block"] = "allow"
    reason: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    additional_context: str = ""


async def run_hook(
    command: str,
    input_data: dict[str, Any],
    *,
    timeout: int = 30,
    cwd: str | None = None,
) -> HookResult:
    """Execute a single hook command. Fail-open: errors/timeouts -> allow."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=json.dumps(input_data).encode("utf-8")),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Hook timed out after {}s: {}", timeout, command)
            return HookResult(action="allow", timed_out=True)
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
    except Exception as e:
        from pythinker_code.telemetry.errors import report_handled_error

        report_handled_error(e, site="hooks.runner")
        logger.warning("Hook failed: {}: {}", command, e)
        return HookResult(action="allow", stderr=str(e))

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = proc.returncode or 0

    # Exit 2 = block
    if exit_code == 2:
        return HookResult(
            action="block",
            reason=stderr.strip(),
            stdout=stdout,
            stderr=stderr,
            exit_code=2,
        )

    # Exit 0 + JSON stdout = structured decision
    if exit_code == 0 and stdout.strip():
        try:
            raw = json.loads(stdout)
            if isinstance(raw, dict):
                parsed = cast(dict[str, Any], raw)
                hook_output = cast(dict[str, Any], parsed.get("hookSpecificOutput", {}))
                additional_context = _extract_additional_context(parsed, hook_output)
                if hook_output.get("permissionDecision") == "deny":
                    return HookResult(
                        action="block",
                        reason=str(hook_output.get("permissionDecisionReason", "")),
                        stdout=stdout,
                        stderr=stderr,
                        exit_code=0,
                        additional_context=additional_context,
                    )
                return HookResult(
                    action="allow",
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    additional_context=additional_context,
                )
        except (json.JSONDecodeError, TypeError):
            if _stdout_adds_context(input_data):
                return HookResult(
                    action="allow",
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    additional_context=stdout,
                )

    return HookResult(action="allow", stdout=stdout, stderr=stderr, exit_code=exit_code)


def _extract_additional_context(parsed: dict[str, Any], hook_output: dict[str, Any]) -> str:
    """Extract ``additionalContext`` from JSON hook output."""
    candidates = (hook_output.get("additionalContext"), parsed.get("additionalContext"))
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _stdout_adds_context(input_data: dict[str, Any]) -> bool:
    """Whether plain stdout from this hook should be recoverable as context."""
    event = input_data.get("hook_event_name")
    if event == "PostCompact":
        return True
    return event == "SessionStart" and input_data.get("source") == "compact"
