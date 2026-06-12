from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pythinker_core.tooling import ToolError

from pythinker_code.execution_profiles import resolve_execution_policy
from pythinker_code.utils.path import check_shell_path_argument, resolve_shell_path

if TYPE_CHECKING:
    from pythinker_host.path import HostPath

    from pythinker_code.soul.agent import Runtime


PermissionProfileName = Literal["read_only", "plan", "ask", "implement", "review", "verify"]


@dataclass(frozen=True, slots=True)
class PermissionProfile:
    name: PermissionProfileName
    description: str
    allow_file_mutation: bool
    allow_shell_mutation: bool
    allow_plan_file_mutation: bool = False
    # Whether first-class network tools (SearchWeb/FetchURL) may execute.
    # Fail-closed default: review/verify/read-only agents must work offline so
    # reviewed diffs and tool output cannot be exfiltrated or used to fetch
    # untrusted instructions. Plan/ask modes keep network because interactive
    # planning research is a first-class use case.
    allow_network: bool = False


_PERMISSION_PROFILES: dict[PermissionProfileName, PermissionProfile] = {
    "read_only": PermissionProfile(
        name="read_only",
        description="read-only exploration",
        allow_file_mutation=False,
        allow_shell_mutation=False,
        allow_network=False,
    ),
    "plan": PermissionProfile(
        name="plan",
        description="plan mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
        allow_plan_file_mutation=True,
        allow_network=True,
    ),
    "ask": PermissionProfile(
        name="ask",
        description="ask-only mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
        allow_network=True,
    ),
    "implement": PermissionProfile(
        name="implement",
        description="implementation mode",
        allow_file_mutation=True,
        allow_shell_mutation=True,
        allow_network=True,
    ),
    "review": PermissionProfile(
        name="review",
        description="review mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
        allow_network=False,
    ),
    "verify": PermissionProfile(
        name="verify",
        description="verification mode",
        allow_file_mutation=False,
        allow_shell_mutation=False,
        allow_network=False,
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
    # The external-docs researcher: read-only like explore, but its entire
    # mission is live web research, so it gets the network-enabled "ask"
    # profile instead of the offline read_only default.
    "scout": "ask",
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
_SUDO_VALUE_OPTS = {
    # Short value-taking options.
    "-u",
    "-g",
    "-U",
    "-C",
    "-p",
    "-r",
    "-t",
    "-T",
    "-h",
    "-R",
    "-D",
    # Long forms with a space-separated value (e.g. ``sudo --user alice rm``).
    # The ``--opt=value`` form carries its value inline, so it is consumed as a
    # single token and needs no entry here.
    "--user",
    "--group",
    "--other-user",
    "--close-from",
    "--prompt",
    "--role",
    "--type",
    "--command-timeout",
    "--host",
    "--chroot",
    "--chdir",
}
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
    if reason := shell_mutation_reason(command):
        return ToolError(
            message=(
                f"The active {profile.description} permission profile blocks this shell command "
                f"because it appears to mutate the workspace or environment, or access the "
                f"network ({reason}). Use a read-only, offline command or switch to an "
                "implementation/coder profile."
            ),
            brief="Permission profile restriction",
        )
    if reason := shell_workspace_escape_reason(
        command,
        work_dir=runtime.session.work_dir,
        additional_dirs=runtime.additional_dirs,
    ):
        return ToolError(
            message=(
                f"The active {profile.description} permission profile blocks this shell command "
                f"because {reason}. Use the Glob/Grep/ReadFile tools or restrict path arguments "
                f"to the workspace root ({runtime.session.work_dir}) and approved additional "
                "directories."
            ),
            brief="Permission profile restriction",
        )
    return None


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


# First-class network tools, gated on PermissionProfile.allow_network. MCP and
# plugin tools have their own fail-closed gate (check_external_tool_allowed).
_NETWORK_TOOLS = {"SearchWeb", "FetchURL"}


def check_network_tool_allowed(runtime: Runtime, tool_name: str) -> ToolError | None:
    """Hard profile gate for first-class network tools.

    Tool visibility filtering already hides these tools from restricted agents,
    but visibility is advisory; this execution-time check is the enforcement
    layer, and it must hold regardless of the root agent's yolo flag.
    """
    profile = active_permission_profile(runtime)
    if profile.allow_network:
        return None
    return ToolError(
        message=(
            f"The active {profile.description} permission profile blocks the network tool "
            f"`{tool_name}`. Review/read-only agents work offline; report a docs-freshness "
            "or fetch need as a finding instead of accessing the network."
        ),
        brief="Permission profile restriction",
    )


def check_tool_call_allowed(
    runtime: Runtime, tool_name: str, arguments: dict[str, Any], *, tool: object | None = None
) -> ToolError | None:
    """Central permission guard for tool adapters that can bypass per-tool checks."""
    if tool_name == "Shell" and isinstance(arguments.get("command"), str):
        return check_shell_command_allowed(runtime, arguments["command"])
    if tool_name in _NETWORK_TOOLS:
        return check_network_tool_allowed(runtime, tool_name)

    # Declarative flag set by external adapters (MCPTool, WireExternalTool,
    # PluginTool) whose side effects cannot be statically classified; see the
    # `external_side_effect_tool` declarations for the fail-closed contract.
    if getattr(tool, "external_side_effect_tool", False):
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


# Positive allowlist for approval elision. Deliberately tight: every entry is
# read-only regardless of arguments once write redirection, hidden commands,
# and network/mutation segments are rejected. Deliberately EXCLUDED:
# env/printenv (env executes commands and prints secrets), find (-exec/
# -delete), xargs (executes), awk/sed (program execution / in-place), rg
# (--pre executes), sort/uniq/tee (write to file args), less/more (shell
# escapes).
_SAFE_READONLY_COMMANDS = frozenset(
    {
        "ls",
        "pwd",
        "cat",
        "head",
        "tail",
        "wc",
        "stat",
        "file",
        "which",
        "whoami",
        "id",
        "date",
        "uname",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "du",
        "df",
        "tr",
        "cut",
        "nl",
        "column",
        "true",
        "false",
        "echo",
        "printf",
        "grep",
        "diff",
        "cmp",
        "md5sum",
        "sha1sum",
        "sha256sum",
        "shasum",
        "ps",
        "uptime",
        "hostname",
        "arch",
        "tty",
    }
)
# Read-only git subcommands. `branch` is excluded (positional arg creates one);
# `--output*` is rejected separately because log/diff/show can write files.
_SAFE_GIT_SUBCOMMANDS = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "rev-parse",
        "describe",
        "blame",
        "ls-files",
        "shortlog",
    }
)
# Absolute command paths must come from here; a workspace-local fake `git`
# (e.g. ./git or /tmp/x/git) must never ride the allowlist via its basename.
_SYSTEM_BIN_DIRS = frozenset(
    {"/bin", "/usr/bin", "/usr/local/bin", "/sbin", "/usr/sbin", "/opt/homebrew/bin"}
)


def is_known_safe_command(command: str) -> bool:
    """Whether *command* is provably read-only, qualifying for prompt elision.

    Positive allowlist, fail closed. ``shell_mutation_reason`` rejects hidden
    sub-commands (substitution, glued operators, unquoted newlines), write
    redirections, and mutating/network segments first; then every
    ``;``/``&&``/``||``/``|`` segment must start with an allowlisted
    read-only binary or read-only git subcommand. Wrapper commands
    (sudo/env/time/nohup/...) are never unwrapped here — they disqualify —
    and absolute command paths must live in a system bin dir.
    """
    if shell_mutation_reason(command) is not None:
        return False
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    if not tokens:
        return False

    saw_segment = False
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token in _SHELL_SEGMENT_SEPARATORS:
            if segment:
                saw_segment = True
                if not _is_safe_readonly_segment(segment):
                    return False
            segment = []
        else:
            segment.append(token)
    return saw_segment


def _is_safe_readonly_segment(tokens: list[str]) -> bool:
    rest = list(tokens)
    # Allow pure KEY=VALUE env-assignment prefixes (FOO=1 grep x); anything
    # else that precedes the command (wrappers) disqualifies below.
    while rest and "=" in rest[0] and not rest[0].startswith("=") and rest[0].split("=", 1)[0]:
        rest.pop(0)
    if not rest:
        return False
    command, args = rest[0], rest[1:]
    if "/" in command:
        directory, _, base = command.rpartition("/")
        if directory not in _SYSTEM_BIN_DIRS:
            return False
    else:
        base = command
    base = base.lower()
    if base == "git":
        subcommand = _git_subcommand(args)
        if subcommand not in _SAFE_GIT_SUBCOMMANDS:
            return False
        # log/diff/show accept --output=<file>, which writes.
        return not any(arg.startswith("--output") for arg in args)
    return base in _SAFE_READONLY_COMMANDS


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
        uv_args = _uv_strip_global_opts(args)
        run_payload = _uv_run_payload(uv_args)
        if run_payload and (r := _segment_mutation_reason(run_payload)):
            return f"uv run: {r}"
        nonopts = [a for a in uv_args if not a.startswith("-")]
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
    if base == "awk" and (reason := _awk_shell_reason(args)):
        return reason
    return None


# --- Workspace jail for read-style shell commands ---------------------------
# The mutation/network classifier above keeps read-only profiles from writing or
# reaching the network, but a benign-looking discovery command can still wander
# outside the workspace (`find .. -name AGENTS.md` passes every gate above). The
# escape classifier applies the same boundary the first-class file tools already
# enforce (is_within_workspace) to the path arguments of common read commands.
#
# Two tiers, mirroring the file tools' semantics so Shell is never stricter:
# * search/traversal commands (like Glob/Grep, which reject out-of-workspace
#   searches): every path argument must resolve inside the workspace.
# * file-read commands (like ReadFile, which allows absolute paths outside the
#   workspace but rejects relative escapes): absolute arguments are allowed,
#   relative arguments must not resolve outside the workspace.

# Directory-listing/traversal commands whose positional args are all paths.
_TRAVERSAL_PATH_COMMANDS = {"ls", "du", "tree"}
# Shell builtins that move the working directory for the rest of the command.
# `cd`/`pushd` targets are tracked across segments; `popd` and `cd -` restore
# state the static checker cannot model and are rejected fail-closed.
_CWD_COMMANDS = {"cd", "pushd", "popd"}
# Search commands whose first positional is the pattern, the rest are paths.
_SEARCH_PATH_COMMANDS = {"rg", "grep", "egrep", "fgrep"}
# File-read commands whose positional args are all file paths (ReadFile parity).
_FILE_READ_COMMANDS = {"cat", "head", "tail", "wc", "stat", "file", "nl", "less", "more", "cmp"}
# Pattern-first file-read commands (script/program first, then file paths).
_PATTERN_READ_COMMANDS = {"sed", "awk"}
# Value-taking flags whose value scopes a command to a directory, on any command.
_DIR_SCOPE_FLAGS = {"--directory", "--project"}
_GIT_DIR_FLAGS = {"-C", "--git-dir", "--work-tree"}
# Pseudo-files that are safe sinks/sources despite living outside the workspace.
_DEVICE_PATH_ALLOW = {"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/tty"}
_GLOB_CHARS = ("*", "?", "[")
# Common value-taking options of grep/rg whose value is not a path (context
# counts, globs, types). Unknown options are treated as boolean, which can only
# misread a value as a path candidate — harmless unless it resolves outside the
# workspace, which plain option values (numbers, type names) never do.
_SEARCH_SKIP_VALUE_FLAGS = {
    "-A",
    "-B",
    "-C",
    "-m",
    "-d",
    "-g",
    "-t",
    "-T",
    "-j",
    "-M",
    "--after-context",
    "--before-context",
    "--context",
    "--max-count",
    "--max-depth",
    "--include",
    "--exclude",
    "--exclude-dir",
    "--glob",
    "--iglob",
    "--type",
    "--type-not",
    "--threads",
    "--color",
    "--colour",
    "--engine",
    "--sort",
    "--sortr",
}


def shell_workspace_escape_reason(
    command: str,
    *,
    work_dir: HostPath,
    additional_dirs: Sequence[HostPath] = (),
) -> str | None:
    """Reason a read-style command's path arguments escape the workspace, else ``None``.

    Runs only for profiles without shell mutation rights, after
    :func:`shell_mutation_reason` returned ``None`` — so hidden-command forms
    (substitution, glued operators) are already rejected and the plain segment
    scan here sees every sub-command. ``cd``/``pushd`` moves are tracked across
    segments so later relative paths are judged against the directory the shell
    will actually be in.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "the command is unparsable"
    segment: list[str] = []
    effective_dir = work_dir
    for token in [*tokens, ";"]:
        if token in _SHELL_SEGMENT_SEPARATORS:
            reason, effective_dir = _segment_workspace_escape_reason(
                segment, work_dir, additional_dirs, effective_dir
            )
            if reason is not None:
                return reason
            segment = []
        else:
            segment.append(token)
    return None


def _segment_workspace_escape_reason(
    tokens: list[str],
    work_dir: HostPath,
    additional_dirs: Sequence[HostPath],
    effective_dir: HostPath,
) -> tuple[str | None, HostPath]:
    """Escape reason for one command segment, plus the cwd the next segment sees."""
    if not tokens:
        return None, effective_dir
    if tokens[0] == "{" or tokens[0].startswith("("):
        # Brace groups and subshells re-nest commands the flat segment scan
        # cannot attribute (a `cd` inside them moves or hides the cwd).
        return (
            f"command grouping `{tokens[0]}` prevents the boundary check from "
            "tracking the working directory",
            effective_dir,
        )
    command, args = _unwrap_command(tokens)
    if command is None:
        return None, effective_dir
    base = _canonical_interpreter_name(command.rsplit("/", 1)[-1])

    if base in _CWD_COMMANDS:
        return _cwd_move_result(base, args, work_dir, additional_dirs, effective_dir)

    # (candidate, absolute_allowed): absolute_allowed marks ReadFile-parity
    # candidates where an absolute path outside the workspace stays permitted.
    candidates: list[tuple[str, bool]] = [
        (value, False) for value in _flag_values(args, _DIR_SCOPE_FLAGS)
    ]
    if base == "git":
        candidates.extend((value, False) for value in _flag_values(args, _GIT_DIR_FLAGS))
    elif base == "find":
        candidates.extend((root, False) for root in _find_root_args(args))
    elif base in _SEARCH_PATH_COMMANDS:
        paths = _pattern_then_paths(
            args,
            pattern_value_flags={"-e", "--regexp"},
            path_value_flags={"-f", "--file"},
            skip_value_flags=_SEARCH_SKIP_VALUE_FLAGS,
        )
        candidates.extend((path, False) for path in paths)
    elif base in _PATTERN_READ_COMMANDS:
        paths = _pattern_then_paths(
            args,
            pattern_value_flags={"-e", "--expression"},
            path_value_flags={"-f", "--file"},
            skip_value_flags={"-v"},
        )
        candidates.extend((path, True) for path in paths)
    elif base in _TRAVERSAL_PATH_COMMANDS:
        candidates.extend((arg, False) for arg in args if not arg.startswith("-"))
    elif base in _FILE_READ_COMMANDS:
        candidates.extend((arg, True) for arg in args if not arg.startswith("-"))

    for raw, absolute_allowed in candidates:
        if _skip_path_candidate(raw):
            continue
        if "$" in raw or "`" in raw:
            # shlex strips quotes, so a quoted-literal `$` is indistinguishable
            # from a runtime expansion the boundary check cannot resolve.
            # Fail closed; the first-class file tools handle such paths.
            return (
                f"path argument `{raw}` contains an unexpanded shell expansion "
                f"the boundary check cannot resolve ({base})",
                effective_dir,
            )
        checkable, glob_remainder = _split_glob_candidate(raw)
        if glob_remainder is not None and _has_parent_traversal(glob_remainder):
            # `src/*/../..` expands inside the workspace, then climbs out.
            return (
                f"path argument `{raw}` combines a glob with parent-directory traversal ({base})",
                effective_dir,
            )
        if glob_remainder is not None and not checkable:
            continue  # bare glob (`*`, `?.py`) expands under the effective cwd
        if absolute_allowed and Path(checkable).expanduser().is_absolute():
            continue
        if not check_shell_path_argument(
            checkable, work_dir, additional_dirs, base_dir=effective_dir
        ):
            return (
                f"path argument `{raw}` resolves outside the workspace ({base})",
                effective_dir,
            )
    return None, effective_dir


def _cwd_move_result(
    base: str,
    args: list[str],
    work_dir: HostPath,
    additional_dirs: Sequence[HostPath],
    effective_dir: HostPath,
) -> tuple[str | None, HostPath]:
    """Track a ``cd``/``pushd`` move, rejecting targets the checker cannot model."""
    if base == "popd":
        return (
            "`popd` restores a directory-stack entry the boundary check cannot track",
            effective_dir,
        )
    target: str | None = None
    for arg in args:
        if arg == "-":
            return (
                f"`{base} -` switches to a previous directory the boundary check cannot track",
                effective_dir,
            )
        if arg == "--" or (arg.startswith("-") and len(arg) > 1):
            continue  # -P/-L style flags
        target = arg
        break
    if target is None:
        return (
            f"`{base}` without a target changes to the home directory; pass an "
            "explicit in-workspace path",
            effective_dir,
        )
    if "$" in target or "`" in target:
        return (
            f"`{base}` target `{target}` contains an unexpanded shell expansion "
            "the boundary check cannot resolve",
            effective_dir,
        )
    resolved = resolve_shell_path(target, effective_dir)
    if not check_shell_path_argument(str(resolved), work_dir, additional_dirs):
        return (
            f"`{base} {target}` moves the working directory outside the workspace",
            effective_dir,
        )
    return None, resolved


def _split_glob_candidate(raw: str) -> tuple[str, str | None]:
    """Split *raw* at its first glob character: ``(literal prefix, remainder)``.

    The prefix bounds where the expansion can land, so it is what the boundary
    check validates; ``remainder`` is ``None`` when *raw* has no glob characters.
    """
    indices = [raw.index(ch) for ch in _GLOB_CHARS if ch in raw]
    if not indices:
        return raw, None
    split_at = min(indices)
    return raw[:split_at], raw[split_at:]


def _has_parent_traversal(fragment: str) -> bool:
    return ".." in fragment.split("/")


def _skip_path_candidate(raw: str) -> bool:
    """Tokens that are not checkable paths: stdin, devices, URLs."""
    return not raw or raw == "-" or raw in _DEVICE_PATH_ALLOW or "://" in raw


def _flag_values(args: list[str], flags: set[str]) -> list[str]:
    """Values of value-taking *flags*, both ``--flag value`` and ``--flag=value`` forms."""
    values: list[str] = []
    for i, arg in enumerate(args):
        for flag in flags:
            if arg == flag and i + 1 < len(args):
                values.append(args[i + 1])
            elif arg.startswith(f"{flag}="):
                values.append(arg.split("=", 1)[1])
    return values


def _find_root_args(args: list[str]) -> list[str]:
    """The root path arguments of a ``find`` invocation.

    Roots are the positionals between find's pre-root options (``-H``/``-L``/
    ``-P``/``-O``/``-D``) and the first expression token (``-name`` etc.).
    Expression values (``-name AGENTS.md``) are matched names, not paths, so the
    scan stops at the first expression.
    """
    i = 0
    while i < len(args) and (args[i] in {"-H", "-L", "-P"} or args[i].startswith(("-O", "-D"))):
        i += 1
    roots: list[str] = []
    while i < len(args) and not args[i].startswith("-") and args[i] not in {"(", "!"}:
        roots.append(args[i])
        i += 1
    return roots


def _pattern_then_paths(
    args: list[str],
    *,
    pattern_value_flags: set[str],
    path_value_flags: set[str],
    skip_value_flags: set[str],
) -> list[str]:
    """Path arguments of a pattern-first command (grep/rg/sed/awk).

    The first positional is the pattern/script unless *pattern_value_flags* or
    *path_value_flags* already supplied it; *path_value_flags* values are file
    arguments themselves; *skip_value_flags* values are non-path option values.
    """
    paths: list[str] = []
    pattern_supplied = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            rest = args[i + 1 :]
            if not pattern_supplied and rest:
                rest = rest[1:]
            paths.extend(rest)
            break
        if arg in pattern_value_flags:
            pattern_supplied = True
            i += 2
            continue
        if any(arg.startswith(f"{flag}=") for flag in pattern_value_flags):
            pattern_supplied = True
            i += 1
            continue
        if arg in path_value_flags:
            if i + 1 < len(args):
                paths.append(args[i + 1])
            pattern_supplied = True
            i += 2
            continue
        if any(arg.startswith(f"{flag}=") for flag in path_value_flags):
            paths.append(arg.split("=", 1)[1])
            pattern_supplied = True
            i += 1
            continue
        if arg in skip_value_flags:
            i += 2
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        if pattern_supplied:
            paths.append(arg)
        else:
            pattern_supplied = True
        i += 1
    return paths


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


_XARGS_VALUE_OPTS = {"-I", "-i", "-n", "-L", "-P", "-s", "-d", "-E", "-a"}


def _xargs_payload(args: list[str]) -> list[str]:
    """Trailing command tokens after xargs options (skip opts and their values)."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in _XARGS_VALUE_OPTS and i + 1 < len(args) else 1
    return args[i:]


# awk pipe to/from an external command: ``print ... | "cmd"`` or ``"cmd" | getline``.
# Restricted to a pipe adjacent to a quote so it does not fire on regex
# alternation (``/foo|bar/``), which would only over-prompt but is avoidable.
_AWK_PIPE_RE = re.compile(r"""\|\s*["']|["']\s*\|\s*getline""")


def _awk_shell_reason(args: list[str]) -> str | None:
    """Reason string if an awk program shells out, else None.

    awk can escape its sandbox three ways, all opaque to the token parser: a
    ``system("...")`` call, a pipe to/from an external command, or output
    redirection (``> file``). The program text survives shlex as one token, so
    detection is substring/regex based.
    """
    program = " ".join(args)
    if "system(" in program or ">" in program:
        return "awk system/redirection"
    if _AWK_PIPE_RE.search(program):
        return "awk pipe to command"
    return None


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


def _uv_strip_global_opts(args: list[str]) -> list[str]:
    """Drop uv's *global* options (and the values of value-taking ones) that
    precede the subcommand, so ``uv --directory repo run rm`` resolves to
    ``run rm`` and the wrapped command is not hidden behind a global flag's
    value (``uv --directory repo run rm -rf /`` must still classify as ``rm``).

    Reuses ``_UV_RUN_VALUE_OPTS`` (a superset of uv's value-taking global options)
    to decide which flags consume a following word; ``--opt=value`` carries its
    value inline and is consumed as one token.
    """
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "--":
            i += 1
            break
        if "=" not in args[i] and args[i] in _UV_RUN_VALUE_OPTS and i + 1 < len(args):
            i += 2
        else:
            i += 1
    return args[i:]


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
    # awk that shells out is equally opaque: the embedded command could be
    # irreversible (system("rm -rf ...")), so the backstop must re-prompt.
    if base == "awk" and _awk_shell_reason(args):
        return "opaque shell exec via awk"
    if base in ("find", "xargs"):
        payload = _exec_payload(args) if base == "find" else _xargs_payload(args)
        if payload and (r := _segment_destructive_reason(payload)):
            return f"{base}: {r}"
    if base == "uv":
        run_payload = _uv_run_payload(_uv_strip_global_opts(args))
        if run_payload and (r := _segment_destructive_reason(run_payload)):
            return f"uv run: {r}"
    return None
