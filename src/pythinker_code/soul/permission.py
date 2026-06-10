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

# Control operators that separate one command from the next. ``shlex.split`` isolates
# these as standalone tokens only when whitespace-delimited; the segment scan splits on
# them. ``&``/``|&`` are real separators too — a *glued* ``2>&1``/``&>`` keeps ``&`` inside
# one token (e.g. ``2>&1``), so it is never a standalone separator and stays unaffected.
_SHELL_SEGMENT_SEPARATORS = {";", "&&", "||", "|", "&", "|&"}
# Subset used by the hidden-command detector's glued-operator count. Excludes ``&``/``|&``
# because the punctuation-aware lexer also splits the ``&`` of redirections (``2>&1``),
# which would false-positive; glued ``&`` is caught structurally instead (its signature
# never collides with a benign base command).
_GLUED_OPERATORS = {";", "&&", "||", "|"}
# Standalone & / |& separators. The punct lexer keeps the & of >&/&>/&>> glued
# inside the redirection token, so a *bare* & token is always a real separator.
_AMP_OPERATORS = {"&", "|&"}
# Redirection operators that WRITE to a file target (vs >& which dups an fd).
_WRITE_REDIRECTION_OPS = {">", ">>", "&>", "&>>"}
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
# sudo options that consume a following separate word (the value is NOT the command).
_SUDO_VALUE_OPTS = {"-u", "-g", "-U", "-C", "-p", "-r", "-t", "-T", "-h", "-R", "-D"}
# GNU time options that consume a following separate word.
_TIME_VALUE_OPTS = {"-o", "-f", "--output", "--format"}


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


# Command/process substitution runs commands the bare-token parser never sees:
# ``$(...)``, backticks, ``<(...)``, ``>(...)``.
_COMMAND_SUBSTITUTION_RE = re.compile(r"\$\(|`|<\(|>\(")


def _shell_hidden_command_reason(command: str) -> str | None:
    """Reason *command* can run sub-commands invisible to the token classifier, else ``None``.

    ``shlex.split`` — used by every shell gate below (mutation, signature, destructive) — has
    two blind spots that let an arbitrary command slip past base-command classification:

    * **Command/process substitution** (``$(...)``, backticks, ``<(...)``, ``>(...)``)
      executes commands that never appear as tokens, so ``ls $(rm -rf /)`` looks like a
      benign ``ls``.
    * **Operators glued to a word** (``ls;rm``) tokenize as one word (``ls;rm``), hiding
      the trailing command from the ``;``/``&&``/``|`` segment scan.

    Also catches an unquoted newline, which separates commands but which ``shlex`` eats
    as whitespace (``git status\nrm -rf /`` flattens to one segment).

    Returns a short reason for any of these, else ``None``. A second ``shlex`` pass with
    ``punctuation_chars`` isolates *unquoted* operators while leaving *quoted* ones
    (``grep 'a|b'``) glued, so quoted literals do not false-positive.
    """
    if _COMMAND_SUBSTITUTION_RE.search(command):
        return "command substitution"
    try:
        plain_tokens = shlex.split(command, posix=True)
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        punct_tokens = list(lexer)
    except ValueError:
        return "unparsable shell command"
    # An unquoted newline is a command separator shlex drops as whitespace. If the
    # (interior) command has one that no token kept, it was unquoted -> hidden command.
    # A quoted newline survives inside a token (``printf 'a\nb'``) and is left alone.
    interior = command.strip()
    if ("\n" in interior or "\r" in interior) and not any(
        "\n" in tok or "\r" in tok for tok in plain_tokens
    ):
        return "ungrouped command separator"
    # More separators once unquoted operators are isolated means one was glued to a
    # word — a command the plain-split segment scan would have missed.
    plain_ops = sum(1 for tok in plain_tokens if tok in _GLUED_OPERATORS)
    punct_ops = sum(1 for tok in punct_tokens if tok in _GLUED_OPERATORS)
    if punct_ops > plain_ops:
        return "ungrouped command operator"
    # A bare &/|& between two tokens is a real separator the plain-split segment scan
    # missed (ls&rm tokenizes as one word). A *trailing* & is a legitimate background
    # job, not a hidden command, so ignore the final position. Redirection &s stay glued
    # inside >&/&>/&>> tokens and never appear as a bare & here.
    for i, tok in enumerate(punct_tokens):
        if tok in _AMP_OPERATORS and i != len(punct_tokens) - 1:
            return "ungrouped command operator"
    return None


def shell_mutation_reason(command: str) -> str | None:
    """Best-effort guard for obviously mutating or network-accessing shell commands.

    This is intentionally conservative for common destructive/write/network forms. It is not a
    shell sandbox; it prevents accidental tool-level bypasses of read-only/plan/review/verify
    profiles — including circumventing the no-web-tools intent via `curl`/`wget`/`ssh`. Script
    interpreters (python/node/sh) are already treated as mutating, so those paths are blocked too.
    A command hiding sub-commands the token parser can't see (substitution / glued operators)
    is treated as mutating too, so ``ls $(rm -rf /)`` can't slip past a read-only profile as ``ls``.
    """
    if reason := _shell_hidden_command_reason(command):
        return reason
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        punct_tokens = list(lexer)
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "unparsable shell command"
    # Scan for write-redirection operators isolated by the punct lexer.
    # NOTE: bare '>&' (fd dup, e.g. 2>&1) is intentionally not in _WRITE_REDIRECTION_OPS.
    for i, tok in enumerate(punct_tokens):
        if tok in _WRITE_REDIRECTION_OPS:
            target = punct_tokens[i + 1] if i + 1 < len(punct_tokens) else ""
            if target in {"/dev/null", "NUL", ""}:
                continue
            return "output redirection"

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
    base = _canonical_interpreter_name(command.rsplit("/", 1)[-1])

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
    if base == "uv":
        run_payload = _uv_run_payload(args)
        if run_payload and (r := _segment_mutation_reason(run_payload)):
            return f"uv run: {r}"
        nonopts = [a for a in args if not a.startswith("-")]
        if nonopts:
            head = nonopts[0]
            sub = nonopts[1] if (head in _UV_SUBNAMESPACES and len(nonopts) > 1) else head
            if sub in _PACKAGE_MANAGER_MUTATIONS:
                return f"uv {head} {sub}" if head in _UV_SUBNAMESPACES else f"uv {sub}"
    elif base in _PACKAGE_MANAGER_COMMANDS:
        subcommand = _first_non_option(args)
        if subcommand in _PACKAGE_MANAGER_MUTATIONS:
            return f"{base} {subcommand}"
    if base == "find":
        if any(a == "-delete" for a in args):
            return "find -delete"
        payload = _exec_payload(args)
        if payload:
            if r := _segment_mutation_reason(payload):
                return f"find -exec: {r}"
            return "find -exec command"
    if base == "xargs":
        payload = _xargs_payload(args)
        if payload and (r := _segment_mutation_reason(payload)):
            return f"xargs: {r}"
    if base == "awk" and any("system(" in a or ">" in a for a in args):
        return "awk system/redirection"
    return None


def shell_command_signature(command: str) -> str:
    """Coarse, stable identity for a shell command, for per-command session approval.

    Built from the base command (plus git / package-manager subcommand) of every
    ``;``/``&&``/``||``/``|``-separated segment, sorted and de-duplicated. This keeps
    "approve for session" scoped to like commands: approving ``git status`` does not
    also whitelist ``git push`` or ``rm``. It pairs with the destructive backstop,
    which independently re-prompts irreversible commands regardless of signature.

    A command hiding sub-commands the token parser can't see (substitution / glued
    operators) is self-scoped to its exact text so it can never share a benign
    command's key — defense-in-depth atop the destructive backstop, which also makes
    such commands non-session-approvable.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "shell:unparsable"
    if _shell_hidden_command_reason(command) is not None:
        return "shell:opaque:" + " ".join(tokens)
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
    base = command.rsplit("/", 1)[-1].lower()
    if base == "git" and (sub := _git_subcommand(args)):
        return f"git {sub}"
    if base in _PACKAGE_MANAGER_COMMANDS and (sub := _first_non_option(args)):
        return f"{base} {sub}"
    return base


def _unwrap_command(tokens: list[str]) -> tuple[str | None, list[str]]:
    remaining = list(tokens)
    while remaining:
        command = remaining.pop(0)
        base = command.rsplit("/", 1)[-1].lower()
        if "=" in command and not command.startswith("=") and command.split("=", 1)[0]:
            continue
        if base not in _WRAPPER_COMMANDS:
            return command, remaining
        if base in {"sudo", "command"}:
            value_opts: set[str] = _SUDO_VALUE_OPTS if base == "sudo" else set()
            while remaining and remaining[0].startswith("-"):
                opt = remaining.pop(0)
                if opt == "--":
                    break
                if opt in value_opts and remaining:
                    remaining.pop(0)
        elif base in {"time", "nohup"}:
            value_opts: set[str] = _TIME_VALUE_OPTS if base == "time" else set()
            while remaining and remaining[0].startswith("-"):
                opt = remaining.pop(0)
                if opt == "--":
                    break
                if opt in value_opts and remaining:
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


_FIND_EXEC_OPTS = {"-exec", "-execdir", "-ok", "-okdir"}


def _exec_payload(args: list[str]) -> list[str] | None:
    """Tokens of a find -exec/-ok command (up to a ';' or '+' terminator), else None."""
    for i, a in enumerate(args):
        if a in _FIND_EXEC_OPTS:
            rest = args[i + 1 :]
            end = next((j for j, t in enumerate(rest) if t in (";", "+")), len(rest))
            return [t for t in rest[:end] if t != "{}"]
    return None


_XARGS_VALUE_OPTS = {"-I", "-i", "-n", "-P", "-s", "-d", "-E", "-a"}


def _xargs_payload(args: list[str]) -> list[str]:
    """Trailing command tokens after xargs options (skip opts and their values)."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in _XARGS_VALUE_OPTS and i + 1 < len(args) else 1
    return args[i:]


# Sub-namespaces under ``uv`` that gate a second-level verb: ``uv pip install``,
# ``uv tool install``, ``uv python install``.  Other first non-option tokens
# (``add``, ``sync``, …) are top-level verbs checked directly against
# ``_PACKAGE_MANAGER_MUTATIONS`` via the existing single-level path.
_UV_SUBNAMESPACES = {"pip", "tool", "python"}
# ``uv run`` options that consume a following separate word. Their value is a
# version/package/path/url/setting — never the wrapped command — so it must be
# skipped along with the flag, or the value (e.g. ``3.12``) is mistaken for the
# command and the real command after it slips by. Boolean flags (``--no-sync``,
# ``--isolated``, ``--frozen``, …) are skipped by the generic leading-``-`` scan.
#
# SAFETY INVARIANT: only list options that GENUINELY take a separate-word value.
# A boolean flag wrongly listed here would skip the real command as its "value"
# and OPEN a bypass (``uv run <wrongly-listed-bool> rm -rf`` → ``rm`` swallowed).
# An option omitted here is treated as boolean (skip the flag only), which is the
# safe failure mode. This set is the value-taking (``<VALUE>``-placeholder) subset
# of ``uv run --help``; refresh it if uv's option surface changes.
_UV_RUN_VALUE_OPTS = {
    "--allow-insecure-host",
    "--cache-dir",
    "--color",
    "--config-file",
    "--config-setting",
    "-C",
    "--config-settings-package",
    "--default-index",
    "--directory",
    "--env-file",
    "--exclude-newer",
    "--exclude-newer-package",
    "--extra",
    "--extra-index-url",
    "--find-links",
    "-f",
    "--fork-strategy",
    "--group",
    "--index",
    "--index-strategy",
    "--index-url",
    "-i",
    "--keyring-provider",
    "--link-mode",
    "--no-binary-package",
    "--no-build-isolation-package",
    "--no-build-package",
    "--no-extra",
    "--no-group",
    "--only-group",
    "--package",
    "--prerelease",
    "--project",
    "--python",
    "-p",
    "--python-platform",
    "--refresh-package",
    "--reinstall-package",
    "--resolution",
    "--upgrade-package",
    "-P",
    "--with",
    "-w",
    "--with-editable",
    "--with-requirements",
}


def _uv_run_payload(args: list[str]) -> list[str] | None:
    """For ``uv run [opts] <cmd> ...``, return the wrapped command tokens, else ``None``.

    ``uv run``'s own options precede the wrapped command and must be skipped, or a
    leading option/value (``uv run --no-sync rm`` / ``uv run --python 3.12 rm``)
    is mistaken for the command and the real ``rm`` after it bypasses the guards. A
    ``--`` ends option parsing; value-taking options also consume their next word.
    """
    nonopts = [i for i, a in enumerate(args) if not a.startswith("-")]
    if not (nonopts and args[nonopts[0]] == "run"):
        return None
    rest = args[nonopts[0] + 1 :]
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        if rest[i] == "--":
            i += 1
            break
        i += 2 if rest[i] in _UV_RUN_VALUE_OPTS and i + 1 < len(rest) else 1
    return rest[i:]


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


def _canonical_interpreter_name(base: str) -> str:
    """Map a version-suffixed interpreter binary to its bare name so version-pinned
    invocations hit the same guards as the canonical form: ``python3.14`` -> ``python``,
    ``node20`` -> ``node``. Non-interpreters are returned unchanged.

    Without this, ``sys.executable`` (commonly ``python3.14``) and any explicitly
    versioned interpreter slip the read-only/destructive shell guards, which only list
    the bare ``python``/``python3`` forms — e.g. ``python3.14 -c '<mutating code>'``
    would run unchecked under a read-only subagent profile.

    Stripping is gated on membership in ``_OPAQUE_INTERPRETERS`` (not the broader
    ``_MUTATING_COMMANDS``) so a non-interpreter like ``rm2`` is NOT normalized to a
    guard hit. The mutation guard then checks ``_MUTATING_COMMANDS``, so its interpreter
    subset must stay in sync with ``_OPAQUE_INTERPRETERS`` (identical today) for
    version-suffixed interpreters to be classified as mutating.
    """
    base = base.lower()
    if base in _OPAQUE_INTERPRETERS:
        return base
    stripped = base.rstrip("0123456789.")
    return stripped if stripped in _OPAQUE_INTERPRETERS else base


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

    Commands hiding sub-commands the token parser can't see — substitution
    (``$(...)``/backticks) or operators glued to a word (``status;rm``) — route to
    deliberation too: the same blind spot that smuggles them past the segment scan
    would otherwise let a session-approved benign command carry a destructive payload.
    """
    if reason := _shell_hidden_command_reason(command):
        return reason
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
    base = _canonical_interpreter_name(command.rsplit("/", 1)[-1])

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
        if _has_unsafe_git_global_option(args):
            return "unsafe git option (-c/--config-env/--exec-path)"
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
    if base in ("find", "xargs"):
        payload = _exec_payload(args) if base == "find" else _xargs_payload(args)
        if payload and (r := _segment_destructive_reason(payload)):
            return f"{base}: {r}"
    if base == "uv":
        run_payload = _uv_run_payload(args)
        if run_payload and (r := _segment_destructive_reason(run_payload)):
            return f"uv run: {r}"
    return None
