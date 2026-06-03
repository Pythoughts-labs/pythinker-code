from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.utils.gitignore import ensure_gitignored


def test_creates_gitignore_when_absent(tmp_path):
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml", comment="Added by pythinker")
    gi = tmp_path / ".gitignore"
    assert gi.exists()
    content = gi.read_text()
    assert ".pythinker/config.local.toml" in content
    assert "Added by pythinker" in content


def test_appends_to_existing_gitignore(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("*.pyc\n", encoding="utf-8")
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml")
    content = gi.read_text()
    assert "*.pyc" in content
    assert ".pythinker/config.local.toml" in content


def test_no_op_when_pattern_already_present(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text(".pythinker/config.local.toml\n", encoding="utf-8")
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml")
    # No duplicate
    lines = [l for l in gi.read_text().splitlines() if l == ".pythinker/config.local.toml"]
    assert len(lines) == 1


def test_fixes_missing_trailing_newline(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("*.pyc", encoding="utf-8")  # no trailing newline
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml")
    content = gi.read_text()
    # Pattern must start on its own line, not appended to "*.pyc"
    assert "\n.pythinker/config.local.toml" in content


def test_omits_comment_when_empty(tmp_path):
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml", comment="")
    content = (tmp_path / ".gitignore").read_text()
    assert ".pythinker/config.local.toml" in content
    assert "#" not in content
