"""Unknown-config-key detection with source-located diagnostics.

Config models ignore extra keys, so a typo'd key ('defaut_yolo') silently
vanishes and changes behavior with no signal. Loading now diffs the raw
merged dict against the model field tree and warns with the dotted path
and originating scope file; PYTHINKER_STRICT_CONFIG escalates to an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.config import Config, ConfigError, _load_scoped, unknown_config_key_paths


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolated_share_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path / "share"))
    monkeypatch.delenv("PYTHINKER_STRICT_CONFIG", raising=False)


class TestUnknownKeyPaths:
    def test_top_level_typo_detected(self) -> None:
        unknown = unknown_config_key_paths(Config, {"defaut_yolo": True})

        assert ("defaut_yolo",) in unknown

    def test_nested_typo_detected(self) -> None:
        unknown = unknown_config_key_paths(Config, {"tui": {"statuslin": {}}})

        assert ("tui", "statuslin") in unknown

    def test_valid_keys_produce_no_findings(self) -> None:
        data = {
            "default_model": "m",
            "tui": {"statusline": {"enabled": True}},
            "loop_control": {"max_steps_per_run": 5},  # validation alias
        }

        assert unknown_config_key_paths(Config, data) == []

    def test_map_fields_allow_arbitrary_keys_but_check_values(self) -> None:
        data = {
            "providers": {
                "mine": {"type": "openai", "base_url": "x", "api_key": "k", "tpyo": 1}
            }
        }

        unknown = unknown_config_key_paths(Config, data)

        assert ("providers", "mine", "tpyo") in unknown
        assert all(path[:2] != ("providers", "mine") or len(path) == 3 for path in unknown)

    def test_list_of_models_checks_items(self) -> None:
        data = {"hooks": [{"event": "Stop", "command": "x", "matchr": ".*"}]}

        unknown = unknown_config_key_paths(Config, data)

        assert ("hooks", "matchr") in unknown


class TestLoadTimeDiagnostics:
    def test_unknown_key_warned_with_scope(self, tmp_path: Path, monkeypatch) -> None:
        from unittest.mock import patch

        _write(tmp_path / "share" / "config.toml", "defaut_yolo = true\n")

        with patch("pythinker_code.config.logger") as mock_logger:
            _load_scoped(None)

        joined = " ".join(str(call) for call in mock_logger.warning.call_args_list)
        assert "defaut_yolo" in joined
        assert "config.toml" in joined

    def test_strict_mode_escalates_to_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("PYTHINKER_STRICT_CONFIG", "1")
        _write(tmp_path / "share" / "config.toml", "defaut_yolo = true\n")

        with pytest.raises(ConfigError, match="defaut_yolo"):
            _load_scoped(None)

    def test_clean_config_loads_silently_in_strict_mode(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("PYTHINKER_STRICT_CONFIG", "1")
        _write(tmp_path / "share" / "config.toml", "session_retention_days = 30\n")

        config = _load_scoped(None)

        assert config.session_retention_days == 30
