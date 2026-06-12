"""Tests for the sensitive file detection module."""

from __future__ import annotations

import pytest

from pythinker_code.utils.sensitive import (
    is_sensitive_file,
    redact_secrets,
    sensitive_file_warning,
)

_REDACTED = "[REDACTED]"


def test_redact_env_assignment():
    out = redact_secrets("ADMIN_PASSWORD=cp-zeyLWvKHRh_jDm8guvg")
    assert "cp-zeyLWvKHRh_jDm8guvg" not in out
    assert _REDACTED in out
    # The key name is preserved so the line is still readable.
    assert out.startswith("ADMIN_PASSWORD=")


def test_redact_preserves_numbered_grep_prefix():
    # A grep result line like "3ADMIN_PASSWORD=secret" keeps its line number.
    out = redact_secrets("3ADMIN_PASSWORD=hunter2value")
    assert "hunter2value" not in out
    assert out == f"3ADMIN_PASSWORD={_REDACTED}"


def test_redact_colon_separated_secret():
    out = redact_secrets("api_key: sk-live-abc123def456")
    assert "sk-live-abc123def456" not in out
    assert _REDACTED in out


def test_redact_multiple_lines_only_touches_secret_lines():
    text = "SITE_NAME=Random Pattern\nSECRET_TOKEN=abcdef123456\nPORT=3020"
    out = redact_secrets(text)
    assert "Random Pattern" in out
    assert "3020" in out
    assert "abcdef123456" not in out


def test_redact_ignores_non_secret_keys():
    text = "USERNAME=rp_editor\nHOST=localhost"
    assert redact_secrets(text) == text


def test_redact_handles_quoted_values():
    out = redact_secrets('PASSWORD="s3cr3t value"')
    assert "s3cr3t value" not in out
    assert _REDACTED in out


def test_redact_empty_and_no_secrets():
    assert redact_secrets("") == ""
    assert redact_secrets("just some prose about passwords") == ("just some prose about passwords")


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "/app/.env",
        "project/.env",
    ],
)
def test_is_sensitive_env_files(path: str):
    assert is_sensitive_file(path)


@pytest.mark.parametrize(
    "path",
    [
        ".env.local",
        ".env.production",
        "/app/.env.staging",
    ],
)
def test_is_sensitive_env_variants(path: str):
    assert is_sensitive_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "/home/user/.ssh/id_rsa",
        "/home/user/.ssh/id_ed25519",
    ],
)
def test_is_sensitive_ssh_keys(path: str):
    assert is_sensitive_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/.aws/credentials",
        "/home/user/.gcp/credentials",
        ".aws/credentials",
        ".gcp/credentials",
        "credentials",
    ],
)
def test_is_sensitive_cloud_credentials(path: str):
    assert is_sensitive_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "app.py",
        "config.yml",
        "README.md",
        "package.json",
        "server.key.example",
        "id_rsa.pub",
        "credentials.json",
        ".envrc",
        "environment.py",
        ".env_example",
        ".env.example",
        ".env.sample",
        ".env.template",
        "/app/.env.example",
    ],
)
def test_not_sensitive_normal_files(path: str):
    assert not is_sensitive_file(path)


@pytest.mark.parametrize(
    "path",
    [
        ".ENV",
        ".Env.Local",
        "ID_RSA",
        "/home/user/.SSH/ID_ED25519",
        "/app/.AWS/credentials",
    ],
)
def test_is_sensitive_case_insensitive(path: str):
    assert is_sensitive_file(path)


def test_is_sensitive_exemption_case_insensitive():
    assert not is_sensitive_file(".ENV.EXAMPLE")


def test_sensitive_file_warning_single():
    warning = sensitive_file_warning([".env"])
    assert "1 sensitive file(s)" in warning
    assert ".env" in warning
    assert "protect secrets" in warning


def test_sensitive_file_warning_multiple():
    warning = sensitive_file_warning([".env", ".env.local", "id_rsa"])
    assert "3 sensitive file(s)" in warning
    assert ".env" in warning
    assert "id_rsa" in warning
