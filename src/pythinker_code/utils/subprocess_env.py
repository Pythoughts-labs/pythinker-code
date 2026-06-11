"""Utilities for subprocess environment handling.

This module provides utilities to handle environment variables when spawning
subprocesses from a PyInstaller-frozen application. The main issue is that
PyInstaller's bootloader modifies LD_LIBRARY_PATH to prioritize bundled libraries,
which can cause conflicts when spawning external programs that expect system libraries.

See: https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
"""

from __future__ import annotations

import os
import sys

# Environment variables that PyInstaller may modify on Linux
_PYINSTALLER_LD_VARS = [
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
]

# Process-local bearer tokens used by the web/visualization servers. They are
# needed by those server processes at startup, but should not be inherited by
# arbitrary child tools, plugins, hooks, git helpers, or shell commands.
_INTERNAL_SESSION_TOKEN_VARS = {
    "PYTHINKER_WEB_SESSION_TOKEN",
    "PYTHINKER_VIS_SESSION_TOKEN",
}


def get_clean_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """
    Get a clean environment suitable for spawning subprocesses.

    In a PyInstaller-frozen application on Linux, this function restores
    the original library path environment variables, preventing subprocesses
    from loading incompatible bundled libraries.

    Args:
        base_env: Base environment to start from. If None, uses os.environ.

    Returns:
        A dictionary of environment variables safe for subprocess use.
    """
    env = dict(base_env if base_env is not None else os.environ)
    for var in _INTERNAL_SESSION_TOKEN_VARS:
        env.pop(var, None)

    # Only process in PyInstaller frozen environment on Linux
    if not getattr(sys, "frozen", False) or sys.platform != "linux":
        return env

    for var in _PYINSTALLER_LD_VARS:
        orig_key = f"{var}_ORIG"
        if orig_key in env:
            # Restore the original value that was saved by PyInstaller bootloader
            env[var] = env[orig_key]
        elif var in env:
            # Variable was not set before PyInstaller modified it, so remove it
            del env[var]

    return env


# Credential-looking environment variable shapes. Read-only/review/verify
# permission profiles block network access, but a child process inherits the
# parent's environment, so API keys and cloud credentials would still be
# readable (and exfiltratable through any future gap). Suffix patterns catch
# the long tail of provider keys (ANTHROPIC_API_KEY, GH_TOKEN, ...); the AWS_
# prefix also drops non-secret AWS config, which restricted-profile commands
# (git/rg/find/cat) never need.
_SECRET_ENV_EXACT = {
    "API_KEY",
    "APIKEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PRIVATE_KEY",
    "JWT",
    "COOKIE",
    "BEARER",
}
_SECRET_ENV_SUFFIXES = (
    "_API_KEY",
    "_APIKEY",
    "_TOKEN",
    "_SECRET",
    "_SECRET_KEY",
    "_PASSWORD",
    "_PASSWD",
    "_CREDENTIALS",
    "_ACCESS_KEY",
    "_ACCESS_KEY_ID",
    "_PRIVATE_KEY",
    "_JWT",
    "_COOKIE",
    "_BEARER",
)
_SECRET_ENV_PREFIXES = ("AWS_", "GOOGLE_APPLICATION_")


def _is_secret_env_name(name: str) -> bool:
    upper = name.upper()
    return (
        upper in _SECRET_ENV_EXACT
        or upper.endswith(_SECRET_ENV_SUFFIXES)
        or upper.startswith(_SECRET_ENV_PREFIXES)
    )


def scrub_secret_env(env: dict[str, str]) -> dict[str, str]:
    """Drop credential-looking variables from a subprocess environment.

    Applied to shell subprocesses spawned under permission profiles without
    shell-mutation rights (read-only/plan/review/verify), so blocked-network
    subagents cannot read inherited secrets either. Heuristic by design; it
    must never be the only secret-protection layer.
    """
    return {k: v for k, v in env.items() if not _is_secret_env_name(k)}


def get_noninteractive_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """
    Get an environment for subprocesses that must not block on interactive prompts.

    Builds on :func:`get_clean_env` and additionally configures git to fail
    fast instead of waiting for user input that will never arrive.

    Args:
        base_env: Base environment to start from. If None, uses os.environ.

    Returns:
        A dictionary of environment variables safe for non-interactive subprocess use.
    """
    env = get_clean_env(base_env)

    # GIT_TERMINAL_PROMPT=0 makes git fail instead of prompting for credentials.
    env.setdefault("GIT_TERMINAL_PROMPT", "0")

    return env
