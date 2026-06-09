"""Tests for OTel resource identity used by dashboards."""

from __future__ import annotations

from importlib.metadata import version as _pkg_version

from pythinker_code.telemetry.otel import _resource  # pyright: ignore[reportPrivateUsage]


def test_resource_service_name_matches_signoz_dashboard() -> None:
    # Pin the test to whatever version is currently in pyproject.toml so the
    # OTel resource assertions don't have to be hand-edited on every release.
    pythinker_version = _pkg_version("pythinker-code")
    resource = _resource(version=pythinker_version, ui_mode="shell", device_id="dev-test")

    assert resource.attributes["service.name"] == "pythinker-cli"
    assert resource.attributes["service.version"] == pythinker_version
    assert resource.attributes["ui.mode"] == "shell"
