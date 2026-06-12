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


def test_error_log_forwarding_emits_site_only(monkeypatch):
    """logger.error records reach OTel as site-only app_error_log events —
    module/function/line and exception class, never the message body;
    lower severities are never forwarded."""
    import pythinker_code.telemetry.otel as otel_mod
    from pythinker_code.utils.logging import logger

    emitted = []
    monkeypatch.setattr(otel_mod, "emit_log", lambda **kw: emitted.append(kw), raising=True)
    sink_id = otel_mod._install_error_log_forwarding()
    assert sink_id is not None
    try:
        logger.error("Invalid JSON line: {line}", line='{"token": "sk-SECRET"}')
        logger.warning("warning should not be forwarded")
        try:
            raise ValueError("kaboom in /Users/someone/secret/file.py")
        except ValueError:
            logger.exception("explosion while handling user payload")
    finally:
        logger.remove(sink_id)

    assert len(emitted) == 2
    plain, with_exc = emitted
    for event in (plain, with_exc):
        assert event["name"] == "app_error_log"
        assert event["severity"] == "error"
        attrs = event["attributes"]
        assert attrs["log.level"] == "ERROR"
        assert attrs["log.module"]
        assert attrs["log.function"] == "test_error_log_forwarding_emits_site_only"
        assert isinstance(attrs["log.line"], int) and attrs["log.line"] > 0
        # The formatted message embeds user/wire-controlled content — it must
        # never be exported, in any attribute.
        assert "message" not in attrs
        joined = " ".join(str(v) for v in attrs.values())
        assert "sk-SECRET" not in joined
        assert "Invalid JSON" not in joined
        assert "/Users/someone" not in joined
    assert "exc_class" not in plain["attributes"]
    assert with_exc["attributes"]["exc_class"] == "ValueError"
