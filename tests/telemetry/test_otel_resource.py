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


# ---------------------------------------------------------------------------
# ERROR-log forwarding to OTel
# ---------------------------------------------------------------------------


def test_error_log_forwarding_scrubs_and_emits(monkeypatch):
    """logger.error records reach OTel as scrubbed app_error_log events;
    lower severities are never forwarded."""
    import pythinker_code.telemetry.otel as otel_mod
    from pythinker_code.utils.logging import logger

    emitted = []
    monkeypatch.setattr(otel_mod, "emit_log", lambda **kw: emitted.append(kw), raising=True)
    sink_id = otel_mod._install_error_log_forwarding()
    assert sink_id is not None
    try:
        logger.error("boom in /Users/someone/secret/file.py while running")
        logger.warning("warning should not be forwarded")
    finally:
        logger.remove(sink_id)

    assert len(emitted) == 1
    event = emitted[0]
    assert event["name"] == "app_error_log"
    assert event["severity"] == "error"
    assert "/Users/someone" not in event["attributes"]["message"]
    assert "<path>" in event["attributes"]["message"]
    assert event["attributes"]["log.level"] == "ERROR"
