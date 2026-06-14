"""Tests for subprocess environment utilities."""

from __future__ import annotations

from pythinker_code.utils.subprocess_env import (
    get_clean_env,
    get_noninteractive_env,
    scrub_secret_env,
)

# --- get_clean_env ---


def test_clean_env_does_not_set_git_vars():
    """get_clean_env should NOT inject git/SSH non-interactive flags."""
    env = get_clean_env(base_env={"PATH": "/usr/bin"})
    assert "GIT_TERMINAL_PROMPT" not in env
    assert "GIT_SSH_COMMAND" not in env


def test_clean_env_removes_internal_session_tokens():
    env = get_clean_env(
        base_env={
            "PATH": "/usr/bin",
            "PYTHINKER_WEB_SESSION_TOKEN": "web-secret",
            "PYTHINKER_DASHBOARD_SESSION_TOKEN": "dashboard-secret",
        }
    )
    assert "PYTHINKER_WEB_SESSION_TOKEN" not in env
    assert "PYTHINKER_DASHBOARD_SESSION_TOKEN" not in env


# --- get_noninteractive_env ---


def test_noninteractive_disables_git_terminal_prompt():
    env = get_noninteractive_env(base_env={"PATH": "/usr/bin"})
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_noninteractive_preserves_existing_git_terminal_prompt():
    """If the user already set GIT_TERMINAL_PROMPT, respect it."""
    env = get_noninteractive_env(base_env={"GIT_TERMINAL_PROMPT": "1"})
    assert env["GIT_TERMINAL_PROMPT"] == "1"


def test_noninteractive_does_not_touch_git_ssh_command():
    """get_noninteractive_env should not inject GIT_SSH_COMMAND to avoid overriding core.sshCommand."""
    env = get_noninteractive_env(base_env={"PATH": "/usr/bin"})
    assert "GIT_SSH_COMMAND" not in env


# --- scrub_secret_env ---


def test_scrub_removes_credential_shaped_vars():
    """Known provider keys, tokens, and cloud credentials are dropped for
    restricted-profile subprocesses; the scrub is case-insensitive."""
    env = scrub_secret_env(
        {
            "ANTHROPIC_API_KEY": "sk-1",
            "OPENAI_API_KEY": "sk-2",
            "GH_TOKEN": "gho_x",
            "GITHUB_TOKEN": "gho_y",
            "AWS_ACCESS_KEY_ID": "AKIA",
            "AWS_SECRET_ACCESS_KEY": "x",
            "AWS_REGION": "us-east-1",
            "GOOGLE_APPLICATION_CREDENTIALS": "/path.json",
            "DB_PASSWORD": "p",
            "MY_SERVICE_SECRET": "s",
            "api_key": "lowercase",
            "TOKEN": "bare",
            "PRIVATE_KEY": "-----BEGIN",
            "JWT": "eyJ",
            "SERVICE_JWT": "eyJ",
            "SESSION_COOKIE": "sid=x",
            "AUTH_BEARER": "Bearer x",
        }
    )
    assert env == {}


def test_scrub_keeps_ordinary_vars():
    """Non-credential variables a shell command actually needs survive the scrub."""
    base = {
        "PATH": "/usr/bin",
        "HOME": "/Users/x",
        "LANG": "en_US.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "TERM": "xterm-256color",
        "VIRTUAL_ENV": "/x/.venv",
        "TOKENIZERS_PARALLELISM": "false",  # contains TOKEN but is not a token
        "COOKIE_JAR_PATH": "/tmp/jar",  # cookie-adjacent name, not a credential
    }
    assert scrub_secret_env(dict(base)) == base
