from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pythinker_core.tooling import ToolError

from pythinker_code.execution_profiles import resolve_execution_policy

if TYPE_CHECKING:
    from pythinker_code.soul.agent import Runtime


PermissionProfileName = Literal["read_only", "plan", "ask", "implement", "review", "verify"]


@dataclass(frozen=True, slots=True)
class PermissionProfile:
    name: PermissionProfileName
    description: str
    allow_file_mutation: bool
    allow_shell_mutation: bool
    allow_plan_file_mutation: bool = False


_PERMISSION_PROFILES: dict[PermissionProfileName, PermissionProfile] = {
    "read_only": PermissionProfile(
        name="read_only",
        description="read-only exploration",
        allow_file_mutation=False,
        allow_shell_mutation=False,
    ),
    "plan": PermissionProfile(
        name="plan",
        description="plan mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
        allow_plan_file_mutation=True,
    ),
    "ask": PermissionProfile(
        name="ask",
        description="ask-only mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
    ),
    "implement": PermissionProfile(
        name="implement",
        description="implementation mode",
        allow_file_mutation=True,
        allow_shell_mutation=True,
    ),
    "review": PermissionProfile(
        name="review",
        description="review mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
    ),
    "verify": PermissionProfile(
        name="verify",
        description="verification mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
    ),
}

_SUBAGENT_PROFILES: dict[str, PermissionProfileName] = {
    "explore": "read_only",
    "plan": "plan",
    "review": "review",
    "verifier": "verify",
    "coder": "implement",
    "implementer": "implement",
    "code-reviewer": "review",
    "security-reviewer": "review",
    "debugger": "verify",
    "judge": "verify",
}

_STEP_PERMISSION_PROFILE: ContextVar[PermissionProfile | None] = ContextVar(
    "pythinker_step_permission_profile", default=None
)

_SHELL_SEGMENT_SEPARATORS = {";", "&&", "||", "|"}
_WRITING_REDIRECTION_RE = re.compile(r"(?:^|\s)(?:[0-9]*>>?|&>)\s*(\S+)")
_MUTATING_COMMANDS = {
    "chmod",
    "chown",
    "cp",
    "dd",
    "install",
    "ln",
    "mkdir",
    "mktemp",
    "mv",
    "patch",
    "rm",
    "rmdir",
    "rsync",
    "tee",
    "touch",
    "truncate",
    "unlink",
    # Shell interpreters: a wrapped `bash -c "rm -rf X"` would otherwise pass
    # the gate because only the wrapper name `bash` is checked, not the script.
    "bash",
    "csh",
    "dash",
    "fish",
    "ksh",
    "sh",
    "tcsh",
    "zsh",
    # Script runtimes with `-c`/`-e` execute arbitrary code; treat the runtime
    # itself as mutating in read-only/review/verify profiles.
    "lua",
    "node",
    "perl",
    "python",
    "python3",
    "ruby",
    # Container/orchestration commands with side effects on host or cluster.
    "docker",
    "helm",
    "kubectl",
    "podman",
}
# Network clients: blocked in read-only/review/verify profiles so the no-web-tools
# intent of those subagents (judge, verifier, review, ...) cannot be bypassed via Shell.
_NETWORK_COMMANDS = {
    "curl",
    "wget",
    "nc",
    "ncat",
    "netcat",
    "telnet",
    "ssh",
    "scp",
    "sftp",
    "ftp",
    "ping",
}
_PACKAGE_MANAGER_COMMANDS = {
    "apt",
    "apt-get",
    "brew",
    "cargo",
    "dnf",
    "gem",
    "go",
    "npm",
    "pnpm",
    "pip",
    "pip3",
    "poetry",
    "uv",
    "yarn",
}
_PACKAGE_MANAGER_MUTATIONS = {
    "add",
    "build",
    "compile",
    "install",
    "publish",
    "remove",
    "sync",
    "uninstall",
    "update",
    "upgrade",
}
_GIT_MUTATIONS = {
    "add",
    "am",
    "apply",
    "bisect",
    "branch",
    "checkout",
    "cherry-pick",
    "clean",
    "commit",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "switch",
    "tag",
}
# git subcommands that reach the network (read-only working-tree git like
# diff/log/show/status stays allowed so judge/verifier can inspect changes).
_GIT_NETWORK = {"clone", "fetch", "ls-remote"}
_WRAPPER_COMMANDS = {"command", "env", "nohup", "sudo", "time"}


def permission_profile_for_runtime(runtime: Runtime) -> PermissionProfile:
    """Return the hard permission profile currently enforced for a runtime."""
    if runtime.role == "subagent" and runtime.subagent_type:
        profile_name = _SUBAGENT_PROFILES.get(runtime.subagent_type, "read_only")
        # A subagent must never exceed the parent's read-only posture. Plan mode
        # lives on the session, which copy_for_subagent shares by reference, so a
        # coder/implementer subagent spawned under a plan-mode root would otherwise
        # resolve its own mutating "implement" profile and run mutating shell
        # commands or side-effecting external/MCP tools. Downgrade any MUTATING
        # subagent profile to "plan" (matching the root's plan-mode posture) so
        # those vectors are blocked at the single profile layer every gate reads
        # (Shell via check_shell_command_allowed, external/MCP via
        # check_external_tool_allowed). Already-read-only profiles
        # (explore/review/verify) are left untouched so they are not loosened.
        # WriteFile/StrReplaceFile are independently blocked via the inherited
        # plan-mode + inspect_plan_edit_target.
        if runtime.session.state.plan_mode:
            resolved_profile = _PERMISSION_PROFILES[profile_name]
            if resolved_profile.allow_file_mutation or resolved_profile.allow_shell_mutation:
                profile_name = "plan"
    elif runtime.session.state.plan_mode:
        profile_name = "plan"
    else:
        policy = resolve_execution_policy(
            runtime.config.agent_execution_profile,
            yolo=runtime.approval.is_yolo_flag(),
        )
        if policy.write == "deny" and policy.shell == "deny":
            profile_name = "read_only"
        elif runtime.config.agent_execution_profile == "review_safe":
            profile_name = "review"
        elif runtime.config.agent_execution_profile == "ci_fixer":
            profile_name = "verify"
        else:
            profile_name = "implement"
    return _PERMISSION_PROFILES[profile_name]


def active_permission_profile(runtime: Runtime) -> PermissionProfile:
    """Return the effective profile for this task.

    A single LLM step snapshots the profile before tool calls start. Tool tasks inherit that
    ContextVar value, so plan/read-only checks cannot race with an ExitPlanMode tool call from the
    same assistant response.
    """
    return _STEP_PERMISSION_PROFILE.get() or permission_profile_for_runtime(runtime)


def set_step_permission_profile(profile: PermissionProfile) -> Token[PermissionProfile | None]:
    """Freeze permission checks for all tool tasks spawned in the current context."""
    return _STEP_PERMISSION_PROFILE.set(profile)


def reset_step_permission_profile(token: Token[PermissionProfile | None]) -> None:
    _STEP_PERMISSION_PROFILE.reset(token)


def check_file_mutation_allowed(
    runtime: Runtime, *, is_plan_artifact: bool = False
) -> ToolError | None:
    profile = active_permission_profile(runtime)
    if profile.allow_file_mutation:
        return None
    if is_plan_artifact and profile.allow_plan_file_mutation:
        return None
    return ToolError(
        message=(
            f"The active {profile.description} permission profile blocks file mutations. "
            "Switch to an implementation/coder profile before editing files."
        ),
        brief="Permission profile restriction",
    )


def check_shell_command_allowed(runtime: Runtime, command: str) -> ToolError | None:
    profile = active_permission_profile(runtime)
    if profile.allow_shell_mutation:
        return None
    reason = shell_mutation_reason(command)
    if reason is None:
        return None
    return ToolError(
        message=(
            f"The active {profile.description} permission profile blocks this shell command "
            f"because it appears to mutate the workspace or environment, or access the network "
            f"({reason}). Use a read-only, offline command or switch to an implementation/coder "
            "profile."
        ),
        brief="Permission profile restriction",
    )


def check_external_tool_allowed(runtime: Runtime, tool_name: str) -> ToolError | None:
    """Fail closed for tools whose side effects are not classified by built-in guards."""
    profile = active_permission_profile(runtime)
    if profile.allow_file_mutation and profile.allow_shell_mutation:
        return None
    return ToolError(
        message=(
            f"The active {profile.description} permission profile blocks external tool "
            f"`{tool_name}` because its side effects are not known to be read-only. "
            "Switch to an implementation/coder profile before using external tools."
        ),
        brief="Permission profile restriction",
    )


def check_tool_call_allowed(
    runtime: Runtime, tool_name: str, arguments: dict[str, Any], *, tool: object | None = None
) -> ToolError | None:
    """Central permission guard for tool adapters that can bypass per-tool checks."""
    if tool_name == "Shell" and isinstance(arguments.get("command"), str):
        return check_shell_command_allowed(runtime, arguments["command"])

    tool_type = type(tool)
    module = getattr(tool_type, "__module__", "")
    qualname = getattr(tool_type, "__qualname__", "")
    if module == "pythinker_code.plugin.tool" and qualname.endswith("PluginTool"):
        return check_external_tool_allowed(runtime, tool_name)
    if module == "pythinker_code.soul.toolset" and qualname in {"MCPTool", "WireExternalTool"}:
        return check_external_tool_allowed(runtime, tool_name)
    return None


def shell_mutation_reason(command: str) -> str | None:
    """Best-effort guard for obviously mutating or network-accessing shell commands.

    This is intentionally conservative for common destructive/write/network forms. It is not a
    shell sandbox; it prevents accidental tool-level bypasses of read-only/plan/review/verify
    profiles — including circumventing the no-web-tools intent via `curl`/`wget`/`ssh`. Script
    interpreters (python/node/sh) are already treated as mutating, so those paths are blocked too.
    """
    for match in _WRITING_REDIRECTION_RE.finditer(command):
        target = match.group(1)
        if target.startswith("&") or target in {"/dev/null", "NUL"}:
            continue
        return "output redirection"

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "unparsable shell command"

    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token in _SHELL_SEGMENT_SEPARATORS:
            reason = _segment_mutation_reason(segment)
            if reason is not None:
                return reason
            segment = []
        else:
            segment.append(token)
    return None


def _segment_mutation_reason(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    command, args = _unwrap_command(tokens)
    if command is None:
        return None
    base = command.rsplit("/", 1)[-1]

    if base in _MUTATING_COMMANDS:
        return f"{base} command"
    if base in _NETWORK_COMMANDS:
        return f"network access via {base}"
    if base == "sed" and any(arg == "-i" or arg.startswith("-i") for arg in args):
        return "sed in-place edit"
    if base == "perl" and any(arg == "-i" or arg.startswith("-i") for arg in args):
        return "perl in-place edit"
    if base == "git":
        if _has_unsafe_git_global_option(args):
            return "unsafe git option (-c/--config-env/--exec-path)"
        subcommand = _git_subcommand(args)
        if subcommand in _GIT_MUTATIONS:
            return f"git {subcommand}"
        if subcommand in _GIT_NETWORK:
            return f"network access via git {subcommand}"
    if base in _PACKAGE_MANAGER_COMMANDS:
        subcommand = _first_non_option(args)
        if subcommand in _PACKAGE_MANAGER_MUTATIONS:
            return f"{base} {subcommand}"
    return None


def shell_command_signature(command: str) -> str:
    """Coarse, stable identity for a shell command, for per-command session approval.

    Built from the base command (plus git / package-manager subcommand) of every
    ``;``/``&&``/``||``/``|``-separated segment, sorted and de-duplicated. This keeps
    "approve for session" scoped to like commands: approving ``git status`` does not
    also whitelist ``git push`` or ``rm``. It pairs with the destructive backstop,
    which independently re-prompts irreversible commands regardless of signature.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "shell:unparsable"
    bases: set[str] = set()
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token in _SHELL_SEGMENT_SEPARATORS:
            if sig := _segment_signature(segment):
                bases.add(sig)
            segment = []
        else:
            segment.append(token)
    return "shell:" + "|".join(sorted(bases)) if bases else "shell:empty"


def _segment_signature(tokens: list[str]) -> str:
    if not tokens:
        return ""
    command, args = _unwrap_command(tokens)
    if command is None:
        return ""
    base = command.rsplit("/", 1)[-1]
    if base == "git" and (sub := _git_subcommand(args)):
        return f"git {sub}"
    if base in _PACKAGE_MANAGER_COMMANDS and (sub := _first_non_option(args)):
        return f"{base} {sub}"
    return base


def _unwrap_command(tokens: list[str]) -> tuple[str | None, list[str]]:
    remaining = list(tokens)
    while remaining:
        command = remaining.pop(0)
        base = command.rsplit("/", 1)[-1]
        if "=" in command and not command.startswith("=") and command.split("=", 1)[0]:
            continue
        if base not in _WRAPPER_COMMANDS:
            return command, remaining
        if base in {"sudo", "time", "nohup", "command"}:
            while remaining and remaining[0].startswith("-"):
                remaining.pop(0)
        elif base == "env":
            while remaining and (remaining[0].startswith("-") or "=" in remaining[0]):
                remaining.pop(0)
    return None, []


def _git_subcommand(args: list[str]) -> str | None:
    remaining = list(args)
    while remaining:
        arg = remaining.pop(0)
        if arg == "-C" and remaining:
            remaining.pop(0)
            continue
        if arg.startswith("--git-dir=") or arg.startswith("--work-tree="):
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


def _has_unsafe_git_global_option(args: list[str]) -> bool:
    """Detect git global options that can run arbitrary commands.

    ``-c <key>=<value>`` and ``--config-env`` can set ``core.pager``,
    ``core.sshCommand``, ``alias.*``, ``credential.helper`` and similar, which
    execute commands even for otherwise read-only subcommands (``log``, ``diff``);
    ``--exec-path=`` redirects git's helper lookup. Read-only/review/verify
    profiles have no need for these, so any occurrence is treated as unsafe rather
    than stripped (stripping would hide the override behind an allowed subcommand).
    """
    for arg in args:
        if arg == "-c" or (arg.startswith("-c") and "=" in arg):
            return True
        if arg == "--config-env" or arg.startswith("--config-env="):
            return True
        if arg == "--exec-path" or arg.startswith("--exec-path="):
            return True
    return False


def _first_non_option(args: list[str]) -> str | None:
    for arg in args:
        if not arg.startswith("-"):
            return arg
    return None


# --- Destructive (irreversible) classification -----------------------------
# Distinct from "mutating": `mkdir`/`touch` mutate the workspace but are easy to
# undo, so they only matter for read-only profile enforcement. A *destructive*
# command is hard/impossible to reverse (recursive force-delete, force-push,
# hard reset, raw disk writes), so in auto mode it routes the agent into a
# deliberation turn instead of being auto-approved. The two questions are
# deliberately separate; this reuses the same token parser as
# ``shell_mutation_reason`` so it inherits the wrapper/quote/chain hardening.
_OPAQUE_INTERPRETERS = {
    "bash",
    "sh",
    "zsh",
    "dash",
    "ksh",
    "csh",
    "tcsh",
    "fish",
    "lua",
    "node",
    "perl",
    "python",
    "python3",
    "ruby",
}
# Flags that hand an interpreter inline code the token parser cannot inspect.
# A bare `python script.py` is NOT opaque; only inline `-c`/`-e` code is.
_INLINE_CODE_FLAGS = {"-c", "-e"}


def _short_flag_letters(arg: str) -> set[str]:
    """Letters of a clustered short-flag arg: ``-rf`` -> ``{'r', 'f'}``.

    Long flags (``--force``) and non-flag tokens return an empty set.
    """
    if len(arg) < 2 or not arg.startswith("-") or arg.startswith("--"):
        return set()
    letters = arg[1:]
    if not letters.isalpha():
        return set()
    return set(letters)


def shell_destructive_reason(command: str) -> str | None:
    """Best-effort guard for *irreversible* shell commands warranting deliberation.

    Returns a human-readable reason when the command is destructive, else ``None``.
    Shares the tokenization path of :func:`shell_mutation_reason` (``shlex`` split,
    wrapper unwrap, git-subcommand extraction), so ``sudo``/``env`` wrappers,
    quoting, and ``;``/``&&``/``||``/``|`` chains are all covered. Unparsable input
    is treated conservatively as destructive.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "unparsable shell command"

    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token in _SHELL_SEGMENT_SEPARATORS:
            reason = _segment_destructive_reason(segment)
            if reason is not None:
                return reason
            segment = []
        else:
            segment.append(token)
    return None


def _shell_args_destructive_reason(arguments: dict[str, Any]) -> str | None:
    command = arguments.get("command")
    return shell_destructive_reason(command) if isinstance(command, str) else None


# The single, auditable place where a tool opts into auto-deliberation. Today only the
# irreversible surface (Shell, including background shell — same tool name) is classified;
# reversible file tools (WriteFile/StrReplaceFile: restore-point + VCS backed) are
# intentionally excluded. A future destructive tool adds one entry here.
_DESTRUCTIVE_CLASSIFIERS: dict[str, Callable[[dict[str, Any]], str | None]] = {
    "Shell": _shell_args_destructive_reason,
}


def tool_destructive_reason(tool_name: str, arguments: dict[str, Any]) -> str | None:
    """Reason a tool call is irreversibly destructive (warrants deliberation), else ``None``.

    Declarative dispatch: classification lives in ``_DESTRUCTIVE_CLASSIFIERS``.
    """
    classifier = _DESTRUCTIVE_CLASSIFIERS.get(tool_name)
    return classifier(arguments) if classifier is not None else None


def _segment_destructive_reason(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    command, args = _unwrap_command(tokens)
    if command is None:
        return None
    base = command.rsplit("/", 1)[-1]

    if base == "rm":
        recursive = any(
            arg in ("-r", "-R", "--recursive") or bool({"r", "R"} & _short_flag_letters(arg))
            for arg in args
        )
        forced = any(arg == "--force" or "f" in _short_flag_letters(arg) for arg in args)
        # Phase 1: require BOTH recursive and force. `rm -r dir` (no -f) and
        # `rm -f file` (no -r) are intentionally allowed to limit chattiness.
        return "rm recursive force delete" if recursive and forced else None
    if base in ("dd", "truncate"):
        return f"{base} raw write"
    if base == "git":
        subcommand = _git_subcommand(args)
        if subcommand == "push" and any(
            arg in ("--force", "-f") or arg.startswith("--force-with-lease") for arg in args
        ):
            return "git push --force"
        if subcommand == "push" and (
            any(arg in ("--delete", "-d") for arg in args)
            or any(arg.startswith(":") and len(arg) > 1 for arg in args)
        ):
            return "git push --delete (remote ref deletion)"
        if subcommand == "reset" and "--hard" in args:
            return "git reset --hard"
        if subcommand == "clean" and any(
            arg == "--force" or "f" in _short_flag_letters(arg) for arg in args
        ):
            return "git clean -f"
        return None
    # Inline-code interpreters are opaque to the token parser -> deliberate.
    if base in _OPAQUE_INTERPRETERS and any(arg in _INLINE_CODE_FLAGS for arg in args):
        return f"opaque inline code via {base}"
    return None
