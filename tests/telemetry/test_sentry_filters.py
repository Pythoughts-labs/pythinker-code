"""Tests for Sentry/Bugsink export filters."""

from __future__ import annotations

from typing import cast

from sentry_sdk.types import Event, Hint

from pythinker_code.telemetry.config import is_disabled, is_enabled, is_test_environment
from pythinker_code.telemetry.sentry import _before_send  # pyright: ignore[reportPrivateUsage]


def test_external_telemetry_disabled_under_pytest() -> None:
    assert is_test_environment() is True
    assert is_disabled() is True


def test_external_telemetry_is_on_by_default(monkeypatch) -> None:
    monkeypatch.setenv("PYTHINKER_FORCE_TELEMETRY_IN_TESTS", "1")
    monkeypatch.delenv("PYTHINKER_DISABLE_TELEMETRY", raising=False)
    # On by default outside the explicit kill switch / pytest guard.
    assert is_disabled() is False

    # Explicit kill switch opts out.
    monkeypatch.setenv("PYTHINKER_DISABLE_TELEMETRY", "1")
    assert is_disabled() is True


def test_is_enabled_combines_toml_and_kill_switch(monkeypatch) -> None:
    """``is_enabled`` is the single gate shared by app startup and the SDK inits.

    Telemetry is on by default; the gate is False only when the TOML setting
    opts out or the kill switch / pytest guard disables emission. Keeping app
    startup and the SDK initializers on this one gate prevents the EventSink
    from being attached while the exporters refuse to initialize.
    """
    monkeypatch.setenv("PYTHINKER_FORCE_TELEMETRY_IN_TESTS", "1")
    monkeypatch.delenv("PYTHINKER_DISABLE_TELEMETRY", raising=False)

    # Default TOML setting + no kill switch -> enabled.
    assert is_enabled(config_telemetry=True) is True
    # TOML opt-out wins even with telemetry on by default.
    assert is_enabled(config_telemetry=False) is False

    # Explicit kill switch disables regardless of the TOML setting.
    monkeypatch.setenv("PYTHINKER_DISABLE_TELEMETRY", "1")
    assert is_enabled(config_telemetry=True) is False


def test_before_send_drops_test_frame_events() -> None:
    event = {
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "boom",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "tests/telemetry/test_crash.py",
                                "abs_path": "/home/user/project/tests/telemetry/test_crash.py",
                            }
                        ]
                    },
                }
            ]
        }
    }

    assert _before_send(cast(Event, event), cast(Hint, {})) is None


def test_before_send_drops_normal_queue_shutdown_events() -> None:
    event = {
        "exception": {
            "values": [
                {
                    "module": "asyncio.queues",
                    "type": "QueueShutDown",
                    "value": "",
                }
            ]
        }
    }

    assert _before_send(cast(Event, event), cast(Hint, {})) is None


def test_init_does_not_register_asyncio_integration(monkeypatch) -> None:
    """AsyncioIntegration's create_task monkeypatch wraps every coroutine in
    ``_task_with_sentry_span_creation`` (``result = await coro``). When such a
    wrapper task is cancelled before its first step — e.g. a freshly re-armed
    ``WireUISide.receive()`` during turn teardown — the wrapper raises before
    reaching ``await coro``, orphaning the inner coroutine and emitting spurious
    "coroutine ... was never awaited" RuntimeWarnings. It must stay out of the
    integration list (with ``default_integrations=False`` so it can't sneak back
    in via the defaults either)."""
    from sentry_sdk.integrations.asyncio import AsyncioIntegration

    import pythinker_code.telemetry.sentry as sentry_mod

    captured: dict[str, object] = {}

    def _fake_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(sentry_mod, "_initialized", False)
    monkeypatch.setattr(sentry_mod, "is_disabled", lambda: False)
    monkeypatch.setattr(sentry_mod, "sentry_dsn", lambda: "https://pub@example.test/1")
    monkeypatch.setattr(sentry_mod.sentry_sdk, "init", _fake_init)

    assert sentry_mod.init(version="1.2.3") is True

    assert captured.get("default_integrations") is False
    integrations = cast(list[object], captured.get("integrations") or [])
    assert not any(isinstance(i, AsyncioIntegration) for i in integrations), (
        "AsyncioIntegration must not be registered: its create_task wrapper orphans "
        "coroutines cancelled before their first step (never-awaited warnings)."
    )


def test_before_send_redacts_paths_in_exception_value_and_message() -> None:
    event = {
        "exception": {
            "values": [
                {
                    "type": "FileNotFoundError",
                    "value": "FileNotFoundError: /Users/panda/.config/pythinker/secrets.yaml not found",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "src/pythinker_code/tools/read.py",
                                "abs_path": "/Users/panda/dev/src/pythinker_code/tools/read.py",
                            }
                        ]
                    },
                }
            ]
        },
        "message": "failed at /home/alice/.ssh/id_rsa",
        "logentry": {
            "message": "read /home/alice/.aws/credentials",
            "formatted": "read /home/alice/.aws/credentials",
        },
    }

    result = _before_send(cast(Event, event), cast(Hint, {}))
    assert result is not None

    exc_value = result["exception"]["values"][0]["value"]  # type: ignore[index]
    assert "/Users/panda/.config" not in exc_value
    assert "<path>" in exc_value

    assert "/home/alice" not in result["message"]  # type: ignore[index]

    logentry = cast("dict[str, str]", result["logentry"])  # type: ignore[index]
    assert "/home/alice" not in logentry["message"]
    assert "/home/alice" not in logentry["formatted"]


def test_scrub_path_redacts_home_for_pyinstaller_conda_layouts(monkeypatch) -> None:
    """_scrub_path must replace a leading $HOME prefix with <home> for paths
    that the env-token regex does not match (PyInstaller onedir, conda envs
    without 'site-packages', editable scripts). The env-token regex must still
    win for paths containing site-packages so the <env>/site-packages/... form
    is preserved.
    """
    import pythinker_code.telemetry.sentry as sentry_mod
    from pythinker_code.telemetry.sentry import _scrub_path  # pyright: ignore[reportPrivateUsage]

    fake_home = "/Users/testuser"
    monkeypatch.setattr(sentry_mod, "_HOME", fake_home)

    # PyInstaller onedir — no site-packages token, home must be masked.
    assert (
        _scrub_path("/Users/testuser/.local/bin/_internal/dep.py")
        == "<home>/.local/bin/_internal/dep.py"
    )

    # Conda env without site-packages token — home must be masked.
    assert _scrub_path("/Users/testuser/miniforge3/envs/x/lib/python3.12/pkg/mod.py") == (
        "<home>/miniforge3/envs/x/lib/python3.12/pkg/mod.py"
    )

    # Env-token regex wins — site-packages under home still maps to <env>/site-packages/...
    assert _scrub_path("/Users/testuser/.venv/lib/python3.12/site-packages/foo/bar.py") == (
        "<env>/site-packages/foo/bar.py"
    )

    # Path outside home is untouched (stdlib, no PII).
    assert (
        _scrub_path("/usr/lib/python3.12/asyncio/queues.py")
        == "/usr/lib/python3.12/asyncio/queues.py"
    )


def test_init_disables_local_variables_and_source_context(monkeypatch) -> None:
    """sentry_sdk 2.x defaults include_local_variables=True and
    include_source_context=True, leaking frame locals and surrounding source
    lines. Both must be explicitly disabled so secrets bound to locals under
    non-denylisted names (auth_header, payload, token_value) and inlined
    string literals cannot reach Bugsink."""
    import pythinker_code.telemetry.sentry as sentry_mod

    captured: dict[str, object] = {}

    def _fake_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(sentry_mod, "_initialized", False)
    monkeypatch.setattr(sentry_mod, "is_disabled", lambda: False)
    monkeypatch.setattr(sentry_mod, "sentry_dsn", lambda: "https://pub@example.test/1")
    monkeypatch.setattr(sentry_mod.sentry_sdk, "init", _fake_init)

    assert sentry_mod.init(version="1.2.3") is True

    assert captured.get("include_local_variables") is False, (
        "include_local_variables must be False: frame locals can hold secrets "
        "under names not covered by the denylist (auth_header, token, payload)."
    )
    assert captured.get("include_source_context") is False, (
        "include_source_context must be False: context lines can contain "
        "inlined string literals with secrets."
    )
