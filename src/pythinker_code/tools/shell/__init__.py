import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Self, override

import pythinker_host
from pydantic import BaseModel, Field, model_validator
from pythinker_core.tooling import CallableTool2, ToolReturnValue
from pythinker_host import AsyncReadable

from pythinker_code.background import TaskView, format_task
from pythinker_code.execution_profiles import resolve_execution_policy
from pythinker_code.soul.agent import Runtime
from pythinker_code.soul.approval import Approval
from pythinker_code.soul.permission import (
    active_permission_profile,
    check_shell_command_allowed,
    is_known_safe_command,
)
from pythinker_code.soul.toolset import (
    emit_current_tool_execution_started,
    get_current_tool_call_or_none,
)
from pythinker_code.tools.display import BackgroundTaskDisplayBlock, ShellDisplayBlock
from pythinker_code.tools.utils import ToolResultBuilder, ToolResultStatus, load_desc
from pythinker_code.utils.environment import Environment
from pythinker_code.utils.logging import logger
from pythinker_code.utils.subprocess_env import get_noninteractive_env, scrub_secret_env

MAX_FOREGROUND_TIMEOUT = 5 * 60
MAX_BACKGROUND_TIMEOUT = 24 * 60 * 60
# Review/read-only workflows must not flag-thrash: after a command has failed
# this many times verbatim, re-running it is a hard denial, not a reminder.
# The counter key is whitespace-normalized so trivial padding cannot mint a
# fresh counter; semantic variations (quoting, flag order) stay distinct.
MAX_IDENTICAL_FAILURES = 2


def _failure_key(command: str) -> str:
    return " ".join(command.split())


def _default_background_description(*, auto_promoted: bool) -> str:
    if auto_promoted:
        return "long-running shell command"
    return "background shell command"


class Params(BaseModel):
    command: str = Field(description="The command to execute.")
    timeout: int = Field(
        description=(
            "The timeout in seconds for the command to execute. "
            "If the command takes longer than this, it will be killed. "
            f"Foreground commands may use at most {MAX_FOREGROUND_TIMEOUT}s; "
            "higher values are automatically run as background tasks."
        ),
        default=60,
        ge=1,
        le=MAX_BACKGROUND_TIMEOUT,
    )
    run_in_background: bool = Field(
        default=False,
        description=(
            "Whether to run the command as a background task. This is automatically enabled "
            f"when timeout is greater than {MAX_FOREGROUND_TIMEOUT}s."
        ),
    )
    description: str = Field(
        default="",
        description=(
            "A short description for the background task. If omitted, a generic description "
            "is used."
        ),
    )

    @model_validator(mode="after")
    def _validate_background_fields(self) -> Self:
        auto_promoted = False
        if not self.run_in_background and self.timeout > MAX_FOREGROUND_TIMEOUT:
            self.run_in_background = True
            auto_promoted = True
        if self.run_in_background and not self.description.strip():
            self.description = _default_background_description(auto_promoted=auto_promoted)
        return self


class Shell(CallableTool2[Params]):
    name: str = "Shell"
    params: type[Params] = Params
    emits_tool_execution_started_after_approval = True

    def __init__(self, approval: Approval, environment: Environment, runtime: Runtime):
        is_powershell = environment.shell_name == "Windows PowerShell"
        super().__init__(
            description=load_desc(
                Path(__file__).parent / ("powershell.md" if is_powershell else "bash.md"),
                {
                    "SHELL": f"{environment.shell_name} (`{environment.shell_path}`)",
                    "MAX_FOREGROUND_TIMEOUT": MAX_FOREGROUND_TIMEOUT,
                    "MAX_BACKGROUND_TIMEOUT": MAX_BACKGROUND_TIMEOUT,
                },
            )
        )
        self._approval = approval
        self._is_powershell = is_powershell
        self._shell_path = environment.shell_path
        self._runtime = runtime
        # Verbatim-command failure counts for this agent, consulted only under
        # restricted (no-shell-mutation) profiles to stop retry loops.
        self._failed_attempts: dict[str, int] = {}

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        # Foreground command output is non-idempotent and unrecoverable once
        # truncated (re-running a build/test is expensive/non-deterministic), so
        # spill the full output to disk with a recovery hint on overflow.
        builder.enable_spill(
            self._runtime.session.dir / "tool-output",
            "powershell" if self._is_powershell else "bash",
        )

        if not params.command:
            return builder.error("Command cannot be empty.", brief="Empty command")

        policy = resolve_execution_policy(
            self._runtime.config.agent_execution_profile,
            yolo=self._runtime.approval.is_yolo_flag(),
        )
        if policy.shell == "deny":
            return builder.error(
                "Shell is denied by the active execution profile.",
                brief="Execution profile restriction",
                status=ToolResultStatus.denied,
            )

        if err := check_shell_command_allowed(self._runtime, params.command):
            return err

        # Profiles without shell-mutation rights also have no business handing
        # inherited credentials to child processes (their network is blocked, so
        # secrets in env are pure downside). Same flag covers fg and bg paths.
        restricted_profile = not active_permission_profile(self._runtime).allow_shell_mutation

        if (
            restricted_profile
            and self._failed_attempts.get(_failure_key(params.command), 0) >= MAX_IDENTICAL_FAILURES
        ):
            return builder.error(
                f"This exact command already failed {MAX_IDENTICAL_FAILURES} times; repeating "
                "it verbatim is blocked under the active restricted permission profile. Change "
                "the approach: verify supported flags from the failure output you already have, "
                "use a different tool, or report the blocker (exact command + exit code) in "
                "your findings instead of retrying.",
                brief="Repeated failing command blocked",
                status=ToolResultStatus.denied,
            )

        if params.run_in_background:
            return await self._run_in_background(params, scrub_secrets=restricted_profile)

        if (
            self._runtime.role == "root"
            and not self._approval.is_safe_mode()
            and is_known_safe_command(params.command)
        ):
            # Provably read-only — elide the approval prompt for the root
            # agent, where prompt fatigue hits the human. Safe mode keeps every
            # prompt: a user who explicitly disabled auto-approval depends on
            # them as checkpoints. Subagents keep the
            # request: their approval path is part of the unattended-denial
            # defense surface (mutation parsing is best-effort there). The
            # deny-path gate (check_shell_command_allowed) already ran above,
            # so this only ever replaces a would-be ask, never a deny. The
            # started event normally fires when approval resolves; emit it.
            from pythinker_code.telemetry import track

            track("shell_safe_command_elision")
            emit_current_tool_execution_started()
        else:
            result = await self._approval.request(
                self.name,
                "run command",
                f"Run command `{params.command}`",
                display=[
                    ShellDisplayBlock(
                        language="powershell" if self._is_powershell else "bash",
                        command=params.command,
                    )
                ],
            )
            if not result:
                return result.rejection_error()

        tool_call = get_current_tool_call_or_none()

        def emit_output_part(stream: Literal["stdout", "stderr", "output"], text: str) -> None:
            if tool_call is None or not text:
                return
            try:
                from pythinker_code.soul import get_wire_or_none
                from pythinker_code.wire.types import ToolOutputPart

                if wire := get_wire_or_none():
                    wire.soul_side.send(
                        ToolOutputPart(tool_call_id=tool_call.id, stream=stream, text=text)
                    )
            except Exception as exc:  # noqa: BLE001 - streaming must not break the tool
                logger.debug("Failed to stream shell output: {error}", error=exc)

        def stdout_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            builder.write(line_str)
            emit_output_part("stdout", line_str)

        def stderr_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            builder.write(line_str)
            emit_output_part("stderr", line_str)

        # Command stdout/stderr is the largest untrusted-input vector in a coding
        # agent (build/test/git output, output from untrusted dependencies). Wrap
        # the aggregated model-facing result in <untrusted_data>; the live UI stream
        # via emit_output_part above stays untagged.
        builder.mark_untrusted()

        try:
            exitcode = await self._run_shell_command(
                params.command,
                stdout_cb,
                stderr_cb,
                params.timeout,
                scrub_secrets=restricted_profile,
            )

            # Output is fully captured now; spill it to disk off the event loop before
            # building the result so a multi-MB write does not block the loop in ok()/error().
            await builder.spill_to_disk()

            if exitcode == 0:
                return builder.ok("Command executed successfully.", status=ToolResultStatus.success)

            if restricted_profile:
                self._record_failed_attempt(params.command)
            builder.extras(exit_code=exitcode)
            brief = f"Failed with exit code: {exitcode}"
            tail = builder.tail()
            if tail:
                brief += f"\n{tail}"
            return builder.error(
                f"Command failed with exit code: {exitcode}.",
                brief=brief,
                status=ToolResultStatus.failure,
            )
        except TimeoutError:
            if restricted_profile:
                self._record_failed_attempt(params.command)
            return builder.error(
                f"Command killed by timeout ({params.timeout}s)",
                brief=f"Killed by timeout ({params.timeout}s)",
                status=ToolResultStatus.cancelled,
            )
        except Exception as e:
            from pythinker_code.telemetry.errors import report_handled_error

            report_handled_error(e, site="tool.shell.exec", tool="Shell")
            logger.error(
                "Shell command execution failed: {command}: {error}",
                command=params.command,
                error=e,
            )
            return builder.error(
                f"Command execution failed: {e}",
                brief="Execution failed",
                status=ToolResultStatus.error,
            )

    def _record_failed_attempt(self, command: str) -> None:
        key = _failure_key(command)
        self._failed_attempts[key] = self._failed_attempts.get(key, 0) + 1

    async def _run_in_background(
        self, params: Params, *, scrub_secrets: bool = False
    ) -> ToolReturnValue:
        tool_call = get_current_tool_call_or_none()
        if tool_call is None:
            return ToolResultBuilder().error(
                "Background shell requires a tool call context.",
                brief="No tool call context",
                status=ToolResultStatus.error,
            )

        result = await self._approval.request(
            self.name,
            "run background command",
            f"Run background command `{params.command}`",
            display=[
                ShellDisplayBlock(
                    language="powershell" if self._is_powershell else "bash",
                    command=params.command,
                )
            ],
        )
        if not result:
            return result.rejection_error()

        try:
            view = self._runtime.background_tasks.create_bash_task(
                command=params.command,
                description=params.description.strip(),
                timeout_s=params.timeout,
                tool_call_id=tool_call.id,
                shell_name="Windows PowerShell" if self._is_powershell else "bash",
                shell_path=str(self._shell_path),
                cwd=str(self._runtime.work_dir),
                scrub_secrets=scrub_secrets,
            )
        except Exception as exc:
            from pythinker_code.telemetry.errors import report_handled_error

            report_handled_error(exc, site="tool.shell.background_start", tool="Shell")
            logger.error(
                "Failed to start background shell task: {command}: {error}",
                command=params.command,
                error=exc,
            )
            builder = ToolResultBuilder()
            return builder.error(
                f"Failed to start background task: {exc}",
                brief="Start failed",
                status=ToolResultStatus.error,
            )

        return self._background_ok(view)

    def _background_ok(self, view: TaskView) -> ToolReturnValue:
        builder = ToolResultBuilder()
        builder.write(
            "\n".join(
                [
                    format_task(view, include_command=True),
                    "tool_status: launched",
                    "automatic_notification: true",
                    "next_step: You will be automatically notified when it completes.",
                    (
                        "next_step: Use TaskOutput with this task_id for a non-blocking "
                        "status/output snapshot. Only set block=true when you intentionally "
                        "want to wait."
                    ),
                    "next_step: Use TaskStop only if the task must be cancelled.",
                    (
                        "human_shell_hint: For users in the interactive shell, "
                        "the only task-management slash command is /task. "
                        "Do not suggest /task list, /task output, /task stop, or /tasks."
                    ),
                ]
            )
        )
        builder.display(
            BackgroundTaskDisplayBlock(
                task_id=view.spec.id,
                kind=view.spec.kind,
                status=view.runtime.status,
                description=view.spec.description,
            )
        )
        return builder.ok(
            "Background task started",
            brief=f"Started {view.spec.id}",
            status=ToolResultStatus.launched,
        )

    async def _run_shell_command(
        self,
        command: str,
        stdout_cb: Callable[[bytes], None],
        stderr_cb: Callable[[bytes], None],
        timeout: int,
        *,
        scrub_secrets: bool = False,
    ) -> int:
        async def _read_stream(stream: AsyncReadable, cb: Callable[[bytes], None]):
            # Use read() instead of readline() to avoid asyncio's 64 KB per-line
            # limit (raises LimitOverrunError / ValueError depending on Python
            # version). The callbacks only accumulate text, so chunk boundaries
            # do not matter for correctness.
            while chunk := await stream.read(65536):
                cb(chunk)

        env = get_noninteractive_env()
        if scrub_secrets:
            env = scrub_secret_env(env)
        process = await pythinker_host.exec(
            *self._shell_args(command), env=env, cwd=str(self._runtime.work_dir)
        )

        # Close stdin immediately so interactive prompts (e.g. git password) get
        # EOF instead of hanging forever waiting for input that will never come.
        process.stdin.close()

        async def _drain_and_wait() -> int:
            await asyncio.gather(
                _read_stream(process.stdout, stdout_cb),
                _read_stream(process.stderr, stderr_cb),
            )
            return await process.wait()

        try:
            return await asyncio.wait_for(_drain_and_wait(), timeout)
        except asyncio.CancelledError:
            await process.kill()
            await process.wait()
            raise
        except TimeoutError:
            await process.kill()
            await process.wait()
            raise

    def _shell_args(self, command: str) -> tuple[str, ...]:
        if self._is_powershell:
            return (str(self._shell_path), "-command", command)
        return (str(self._shell_path), "-c", command)
