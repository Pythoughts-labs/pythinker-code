"""Per-project trust gating of auto-executed project config.

A cloned repository's .pythinker/config.toml can define shell hooks that
run automatically at session start. Project-scope hooks must therefore
load only after the user trusts the project root; the decision persists
across sessions in a user-scope trust file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.project_trust import is_project_trusted, set_project_trusted


@pytest.fixture(autouse=True)
def _isolated_share_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path / "share"))


def _project_with_hooks(tmp_path: Path, body: str | None = None) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    config_dir = root / ".pythinker"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        body
        if body is not None
        else '[[hooks]]\nevent = "SessionStart"\ncommand = "touch /tmp/pwned"\n',
        encoding="utf-8",
    )
    return root


class TestTrustStore:
    def test_unknown_project_is_untrusted(self, tmp_path: Path) -> None:
        assert is_project_trusted(tmp_path / "nowhere") is False

    def test_set_and_revoke_roundtrip(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()

        set_project_trusted(root, True)
        assert is_project_trusted(root) is True

        set_project_trusted(root, False)
        assert is_project_trusted(root) is False

    def test_paths_are_normalized(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "sub").mkdir(parents=True)

        set_project_trusted(root / "sub" / "..", True)

        assert is_project_trusted(root) is True

    def test_corrupt_trust_file_is_tolerated(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        set_project_trusted(root, True)
        trust_files = list((tmp_path / "share").glob("trusted_projects.json"))
        assert trust_files
        trust_files[0].write_text("{not json", encoding="utf-8")

        assert is_project_trusted(root) is False


class TestUntrustedProjectConfigGating:
    def test_untrusted_project_hooks_are_stripped(self, tmp_path: Path) -> None:
        from pythinker_code.config import _load_scoped

        root = _project_with_hooks(tmp_path)

        config = _load_scoped(root)

        assert config.hooks == []

    def test_trusted_project_hooks_load(self, tmp_path: Path) -> None:
        from pythinker_code.config import _load_scoped

        root = _project_with_hooks(tmp_path)
        set_project_trusted(root, True)

        config = _load_scoped(root)

        assert len(config.hooks) == 1
        assert config.hooks[0].event == "SessionStart"

    def test_user_scope_hooks_unaffected_by_project_trust(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pythinker_code.config import _load_scoped, get_config_file

        root = _project_with_hooks(tmp_path, body="")
        user_file = get_config_file()
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text(
            '[[hooks]]\nevent = "SessionStart"\ncommand = "echo mine"\n', encoding="utf-8"
        )

        config = _load_scoped(root)

        assert len(config.hooks) == 1
        assert config.hooks[0].command == "echo mine"

    def test_local_scope_hooks_also_gated(self, tmp_path: Path) -> None:
        from pythinker_code.config import _load_scoped

        root = _project_with_hooks(tmp_path, body="")
        (root / ".pythinker" / "config.local.toml").write_text(
            '[[hooks]]\nevent = "SessionStart"\ncommand = "echo local"\n', encoding="utf-8"
        )

        config = _load_scoped(root)

        assert config.hooks == []

    def test_invalid_toml_in_untrusted_project_is_empty_scope(self, tmp_path: Path) -> None:
        from pythinker_code.config import _load_scoped

        root = _project_with_hooks(tmp_path, body="this = [is not toml")

        config = _load_scoped(root)  # must not raise

        assert config.hooks == []

    def test_invalid_toml_in_trusted_project_still_raises(self, tmp_path: Path) -> None:
        from pythinker_code.config import ConfigError, _load_scoped

        root = _project_with_hooks(tmp_path, body="this = [is not toml")
        set_project_trusted(root, True)

        with pytest.raises(ConfigError):
            _load_scoped(root)
