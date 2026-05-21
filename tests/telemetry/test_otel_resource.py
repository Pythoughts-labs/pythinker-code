"""Tests for OTel resource identity used by dashboards."""

from __future__ import annotations

import pytest

from pythinker_code.telemetry.otel import (  # pyright: ignore[reportPrivateUsage]
    _is_context_detach_mismatch,
    _resource,
)


def test_resource_service_name_matches_signoz_dashboard() -> None:
    resource = _resource(version="2.6.0", ui_mode="shell", device_id="dev-test")

    assert resource.attributes["service.name"] == "pythinker-cli"
    assert resource.attributes["service.version"] == "2.6.0"
    assert resource.attributes["ui.mode"] == "shell"


@pytest.mark.parametrize(
    "message",
    [
        "<Token var=<ContextVar name='current_context' default={} at 0x1> at 0x2> was created in a different Context",
        "Token was created in a different Context",
    ],
)
def test_otel_context_detach_mismatch_is_identified(message: str) -> None:
    assert _is_context_detach_mismatch(ValueError(message))


def test_unrelated_value_error_is_not_context_detach_mismatch() -> None:
    assert not _is_context_detach_mismatch(ValueError("something else"))
