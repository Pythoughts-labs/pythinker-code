from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from pythinker_code.config import Config
from pythinker_code.web.api import config as config_api
from pythinker_code.web.api.config import UpdateGlobalConfigRequest, update_global_config


@pytest.fixture
def saved_config(monkeypatch) -> dict[str, Config]:
    """Stub load/save so the PATCH merge runs against an in-memory Config."""
    store: dict[str, Config] = {}

    def fake_load_config(*_args: object, **_kwargs: object) -> Config:
        return store.get("config") or Config()

    def fake_save_config(config: Config, *_args: object, **_kwargs: object) -> None:
        store["config"] = config

    monkeypatch.setattr(config_api, "load_config", fake_load_config)
    monkeypatch.setattr(config_api, "save_config", fake_save_config)
    return store


async def _patch(request: UpdateGlobalConfigRequest) -> None:
    http_request = cast(
        Any,
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(restrict_sensitive_apis=False))),
    )
    await update_global_config(request, http_request, runner=cast(Any, None))


@pytest.mark.parametrize(
    ("thinking", "effort", "expected_thinking", "expected_effort"),
    [
        # When effort is provided it is the source of truth and the bool is
        # derived from it — a contradictory bool must not win (regression: the
        # PATCH used to silently flip these).
        (True, "off", False, "off"),
        (False, "high", True, "high"),
        # When effort is omitted, fall back to the legacy bool.
        (True, None, True, "high"),
        (False, None, False, "off"),
        # Effort alone is enough.
        (None, "low", True, "low"),
    ],
)
async def test_patch_thinking_effort_is_source_of_truth(
    saved_config: dict[str, Config],
    thinking: bool | None,
    effort: str | None,
    expected_thinking: bool,
    expected_effort: str | None,
) -> None:
    await _patch(
        UpdateGlobalConfigRequest(
            default_thinking=thinking,
            default_thinking_effort=cast(Any, effort),
            restart_running_sessions=False,
        )
    )
    config = saved_config["config"]
    assert config.default_thinking is expected_thinking
    assert config.default_thinking_effort == expected_effort


async def test_patch_then_get_round_trips_effort(saved_config: dict[str, Config]) -> None:
    await _patch(
        UpdateGlobalConfigRequest(
            default_thinking_effort=cast(Any, "medium"), restart_running_sessions=False
        )
    )
    snapshot = await config_api.get_global_config()
    assert snapshot.default_thinking_effort == "medium"
    assert snapshot.default_thinking is True
