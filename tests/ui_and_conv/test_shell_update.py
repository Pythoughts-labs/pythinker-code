from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from rich.console import Console

from pythinker_code.ui.shell import update


@pytest.mark.asyncio
async def test_prompt_pre_start_update_runs_update_and_exits_on_accept(monkeypatch):
    calls: list[str] = []

    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_prompt(
        current: str, latest: str, *, allow_exit: bool = False
    ) -> update.UpdatePromptSelection:
        assert allow_exit is True
        return update.UpdatePromptSelection.UPDATE_NOW

    async def fake_do_update(*, print_output: bool) -> update.UpdateResult:
        assert print_output is True
        calls.append("update")
        return update.UpdateResult.UPDATED

    async def fake_ack() -> None:
        calls.append("ack")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)
    monkeypatch.setattr(update, "do_update", fake_do_update)
    monkeypatch.setattr(update, "_await_exit_acknowledgment", fake_ack)

    with pytest.raises(update.typer.Exit) as excinfo:
        await update.prompt_pre_start_update()

    assert excinfo.value.exit_code == 0
    # The acknowledgment pause must run after the update and before the exit so
    # the "Updated / relaunch" message stays on screen instead of vanishing.
    assert calls == ["update", "ack"]


@pytest.mark.asyncio
async def test_prompt_update_selection_offers_exit_only_when_allowed(monkeypatch):
    seen_options: list[list[tuple[str, str]]] = []

    class FakeChoiceInput:
        def __init__(self, *, message: str, options: list[tuple[str, str]], default: str):
            assert message == "Update now?"
            assert default == "update"
            seen_options.append(options)

        async def prompt_async(self) -> str:
            return "exit"

    monkeypatch.setattr("prompt_toolkit.shortcuts.choice_input.ChoiceInput", FakeChoiceInput)

    assert (
        await update._prompt_update_selection("1.0.0", "2.0.0", allow_exit=True)
        is update.UpdatePromptSelection.EXIT
    )
    assert ("exit", "Exit Pythinker") in seen_options[-1]

    assert (
        await update._prompt_update_selection("1.0.0", "2.0.0", allow_exit=False)
        is update.UpdatePromptSelection.SKIP
    )
    assert all(value != "exit" for value, _label in seen_options[-1])


@pytest.mark.asyncio
async def test_await_exit_acknowledgment_waits_for_keypress(monkeypatch):
    waited: list[bool] = []

    def fake_input(*_a) -> str:
        waited.append(True)
        return ""

    monkeypatch.setattr("builtins.input", fake_input)

    await update._await_exit_acknowledgment()

    assert waited == [True]


@pytest.mark.asyncio
async def test_await_exit_acknowledgment_swallows_eof(monkeypatch):
    def fake_input(*_a) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)

    # A piped/closed stdin must not crash the exit path.
    assert await update._await_exit_acknowledgment() is None


@pytest.mark.asyncio
async def test_prompt_pre_start_update_exits_without_update_on_exit_selection(monkeypatch):
    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_prompt(
        current: str, latest: str, *, allow_exit: bool = False
    ) -> update.UpdatePromptSelection:
        assert allow_exit is True
        return update.UpdatePromptSelection.EXIT

    async def fail_do_update(*, print_output: bool) -> update.UpdateResult:
        raise AssertionError("exit must not run the update")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    with pytest.raises(update.typer.Exit) as excinfo:
        await update.prompt_pre_start_update()

    assert excinfo.value.exit_code == 0


@pytest.mark.asyncio
async def test_prompt_pre_start_update_continues_on_decline(monkeypatch):
    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_prompt(
        current: str, latest: str, *, allow_exit: bool = False
    ) -> update.UpdatePromptSelection:
        assert allow_exit is True
        return update.UpdatePromptSelection.SKIP

    async def fail_do_update(*, print_output: bool) -> update.UpdateResult:
        raise AssertionError("declining must not run the update")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    # Returns without raising typer.Exit (session continues).
    assert await update.prompt_pre_start_update() is None


@pytest.mark.asyncio
async def test_prompt_pre_start_update_can_dismiss_until_next_version(monkeypatch, tmp_path):
    dismissed_file = tmp_path / "dismissed.txt"

    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_prompt(
        current: str, latest: str, *, allow_exit: bool = False
    ) -> update.UpdatePromptSelection:
        assert allow_exit is True
        return update.UpdatePromptSelection.DISMISS_VERSION

    async def fail_do_update(*, print_output: bool) -> update.UpdateResult:
        raise AssertionError("dismissing must not run the update")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "DISMISSED_VERSION_FILE", dismissed_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    assert await update.prompt_pre_start_update() is None
    assert dismissed_file.read_text(encoding="utf-8") == "999.0.0"


@pytest.mark.asyncio
async def test_prompt_pre_start_update_respects_dismissed_version(monkeypatch, tmp_path):
    prompted: list[bool] = []
    dismissed_file = tmp_path / "dismissed.txt"
    dismissed_file.write_text("999.0.0", encoding="utf-8")

    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_prompt(
        current: str, latest: str, *, allow_exit: bool = False
    ) -> update.UpdatePromptSelection:
        prompted.append(True)
        return update.UpdatePromptSelection.UPDATE_NOW

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "DISMISSED_VERSION_FILE", dismissed_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)

    assert await update.prompt_pre_start_update() is None
    assert prompted == []


@pytest.mark.asyncio
async def test_prompt_pre_start_update_skips_when_up_to_date(monkeypatch):
    confirmed: list[bool] = []

    async def fake_resolve() -> str:
        return "0.0.0"

    async def fake_prompt(
        current: str, latest: str, *, allow_exit: bool = False
    ) -> update.UpdatePromptSelection:
        confirmed.append(True)
        return update.UpdatePromptSelection.UPDATE_NOW

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)

    assert await update.prompt_pre_start_update() is None
    assert confirmed == []


@pytest.mark.asyncio
async def test_prompt_pre_start_update_respects_opt_out(monkeypatch):
    async def fail_resolve() -> str:
        raise AssertionError("opt-out must short-circuit before checking versions")

    monkeypatch.setenv("PYTHINKER_CLI_NO_AUTO_UPDATE", "1")
    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fail_resolve)

    assert await update.prompt_pre_start_update() is None


@pytest.mark.asyncio
async def test_prompt_pre_start_update_skips_non_tty(monkeypatch):
    async def fail_resolve() -> str:
        raise AssertionError("non-tty must short-circuit before checking versions")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fail_resolve)

    assert await update.prompt_pre_start_update() is None


def test_should_auto_check_does_not_require_stdout_tty(monkeypatch, tmp_path):
    last_check_file = tmp_path / "last_update_check.txt"

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_auto_update_disabled", lambda: False)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)

    assert update._should_auto_check_for_updates() is True


@pytest.mark.asyncio
async def test_resolve_latest_version_fetches_when_due(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print_output, check_only))
        latest_file.write_text("2.0.0", encoding="utf-8")
        return update.UpdateResult.UPDATE_AVAILABLE

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(update, "do_update", fake_do_update)

    result = await update._resolve_latest_version_for_prompt()

    assert result == "2.0.0"
    assert calls == [(False, True)]
    assert last_check_file.exists()


@pytest.mark.asyncio
async def test_resolve_latest_version_fetches_when_cache_missing(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print_output, check_only))
        latest_file.write_text("2.0.0", encoding="utf-8")
        return update.UpdateResult.UPDATE_AVAILABLE

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: False)
    monkeypatch.setattr(update, "do_update", fake_do_update)

    assert await update._resolve_latest_version_for_prompt() == "2.0.0"
    assert calls == [(False, True)]
    assert last_check_file.exists()


@pytest.mark.asyncio
async def test_resolve_latest_version_uses_cache_when_not_due(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("3.1.0", encoding="utf-8")

    async def fail_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        raise AssertionError("must not hit the network when the throttle is not due")

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: False)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    assert await update._resolve_latest_version_for_prompt() == "3.1.0"


@pytest.mark.asyncio
async def test_resolve_latest_version_revalidates_stale_cache_when_not_due(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("0.0.0", encoding="utf-8")
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print_output, check_only))
        latest_file.write_text("999.0.0", encoding="utf-8")
        return update.UpdateResult.UPDATE_AVAILABLE

    def fail_should_auto_check() -> bool:
        raise AssertionError("stale prompt cache must bypass the 24h throttle")

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", fail_should_auto_check)
    monkeypatch.setattr(update, "do_update", fake_do_update)

    assert await update._resolve_latest_version_for_prompt() == "999.0.0"
    assert calls == [(False, True)]
    assert last_check_file.exists()


@pytest.mark.asyncio
async def test_resolve_latest_version_keeps_cache_when_prompt_refresh_times_out(
    monkeypatch, tmp_path
):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("0.0.0", encoding="utf-8")
    calls: list[bool] = []

    async def slow_refresh(*, force: bool) -> update.UpdateResult:
        calls.append(force)
        await asyncio.sleep(60)
        return update.UpdateResult.UPDATE_AVAILABLE

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "PROMPT_UPDATE_REFRESH_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(update, "_refresh_update_cache", slow_refresh)

    assert await update._resolve_latest_version_for_prompt() == "0.0.0"
    assert calls == [True]


@pytest.mark.asyncio
async def test_refresh_cache_does_not_throttle_on_failure(monkeypatch, tmp_path):
    """A failed check must not mark the throttle file.

    Regression for: first shell start hits a transient network issue, the old
    throttle-before-check path would suppress retries for 24 hours, so users
    never saw the update banner until then.
    """
    latest_file = tmp_path / "latest.txt"
    last_check_file = tmp_path / "last_update_check.txt"

    async def failing_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        return update.UpdateResult.FAILED

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(update, "do_update", failing_do_update)

    result = await update._refresh_update_cache(force=False)
    assert result is update.UpdateResult.FAILED
    assert not last_check_file.exists(), (
        "failed checks must not mark the throttle — otherwise a transient "
        "network issue silences update notices for 24h"
    )


@pytest.mark.asyncio
async def test_refresh_cache_does_not_throttle_on_exception(monkeypatch, tmp_path):
    last_check_file = tmp_path / "last_update_check.txt"

    async def raising_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(update, "do_update", raising_do_update)

    assert await update._refresh_update_cache(force=False) is None
    assert not last_check_file.exists()


class _FakeJsonResponse:
    """Minimal aiohttp.ClientResponse stand-in for update-check tests."""

    def __init__(
        self,
        *,
        status: int,
        json_data: object | None = None,
        etag: str | None = None,
        text_data: str = "",
    ) -> None:
        self.status = status
        self._json = json_data
        self._text = text_data
        self.headers: dict[str, str] = {}
        if etag is not None:
            self.headers["ETag"] = etag

    async def __aenter__(self) -> _FakeJsonResponse:
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"http {self.status}")

    async def json(self, *, content_type=None) -> object:
        return self._json

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, response: _FakeJsonResponse) -> None:
        self._response = response
        self.captured_headers: dict[str, str] | None = None

    def get(self, url: str, *, headers=None):
        self.captured_headers = headers or {}
        return self._response


class _FakeSessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *_exc) -> None:
        return None


@pytest.mark.asyncio
async def test_update_candidate_waits_for_native_asset_pair(monkeypatch):
    response = _FakeJsonResponse(
        status=200,
        json_data={"assets": [{"name": "pythinker-9.0.0-x86_64-unknown-linux-gnu.tar.gz"}]},
    )
    session = _FakeSession(response)

    monkeypatch.setattr(
        update,
        "_native_update_asset_name",
        lambda version: "pythinker-9.0.0-x86_64-unknown-linux-gnu.tar.gz",
    )

    reason = await update._update_candidate_unavailable_reason(
        session,  # type: ignore[arg-type]
        "9.0.0",
        [update.NATIVE_INSTALLER_MARKER],
    )

    assert reason is not None
    assert "still publishing" in reason
    assert "pythinker-9.0.0-x86_64-unknown-linux-gnu.tar.gz" in reason


@pytest.mark.asyncio
async def test_update_candidate_accepts_ready_native_asset_pair(monkeypatch):
    asset = "pythinker-9.0.0-x86_64-unknown-linux-gnu.tar.gz"
    response = _FakeJsonResponse(
        status=200,
        json_data={"assets": [{"name": asset}, {"name": f"{asset}.sha256"}]},
    )
    session = _FakeSession(response)

    monkeypatch.setattr(update, "_native_update_asset_name", lambda version: asset)

    assert (
        await update._update_candidate_unavailable_reason(
            session,  # type: ignore[arg-type]
            "9.0.0",
            [update.NATIVE_INSTALLER_MARKER],
        )
        is None
    )


@pytest.mark.asyncio
async def test_update_candidate_waits_for_homebrew_formula_version():
    response = _FakeJsonResponse(
        status=200,
        text_data='class PythinkerCode\n  version "8.0.0"\nend',
    )
    session = _FakeSession(response)

    reason = await update._update_candidate_unavailable_reason(
        session,  # type: ignore[arg-type]
        "9.0.0",
        ["brew", "upgrade", "pythinker-code"],
    )

    assert reason is not None
    assert "Homebrew formula is still publishing" in reason


@pytest.mark.asyncio
async def test_do_update_managed_check_only_caches_latest(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    messages: list[str] = []

    async def fake_get_latest(session) -> str:
        return "999.0.0"

    async def fail_unavailable(session, latest_version: str, upgrade_command: list[str]) -> str:
        raise AssertionError("managed channel must not run install-channel readiness checks")

    monkeypatch.setenv("PYTHINKER_MANAGED", "docker")
    monkeypatch.setattr(update.sys, "executable", "/usr/local/bin/python")
    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(update, "_update_candidate_unavailable_reason", fail_unavailable)
    monkeypatch.setattr(update, "new_client_session", lambda timeout: _FakeSessionContext(object()))

    result = await update.do_update(
        print_output=False, check_only=True, output_callback=messages.append
    )

    assert result is update.UpdateResult.UPDATE_AVAILABLE
    assert latest_file.read_text(encoding="utf-8") == "999.0.0"
    assert any("managed by your docker channel" in message for message in messages)


@pytest.mark.asyncio
async def test_do_update_does_not_cache_uninstallable_latest(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("8.0.0", encoding="utf-8")
    etag_file = tmp_path / "etag"
    etag_file.write_text('W/"unready"', encoding="utf-8")

    async def fake_get_latest(session) -> str:
        return "9.0.0"

    async def fake_unavailable(session, latest_version: str, upgrade_command: list[str]) -> str:
        assert latest_version == "9.0.0"
        return "Pythinker 9.0.0 is still publishing."

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LATEST_VERSION_ETAG_FILE", etag_file)
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(
        update,
        "_detect_upgrade_command",
        lambda: ["uv", "tool", "upgrade", "pythinker-code"],
    )
    monkeypatch.setattr(update, "_update_candidate_unavailable_reason", fake_unavailable)
    monkeypatch.setattr(update, "new_client_session", lambda timeout: _FakeSessionContext(object()))

    result = await update.do_update(print_output=False, check_only=True)

    assert result is update.UpdateResult.FAILED
    assert not latest_file.exists()
    assert not etag_file.exists()


@pytest.mark.asyncio
async def test_get_latest_version_sends_if_none_match_when_etag_cached(monkeypatch, tmp_path):
    """Per GitHub REST best practices, the polling caller must send
    If-None-Match with the cached ETag — that's what unlocks 304 responses
    that skip rate-limit accounting."""
    etag_file = tmp_path / "etag"
    etag_file.write_text('W/"cached-etag-value"', encoding="utf-8")

    monkeypatch.setattr(update, "LATEST_VERSION_ETAG_FILE", etag_file)
    response = _FakeJsonResponse(status=200, json_data={"tag_name": "v1.2.3"}, etag='W/"new-etag"')
    session = _FakeSession(response)

    version = await update._get_latest_version(session)  # type: ignore[arg-type]

    assert version == "1.2.3"
    assert session.captured_headers is not None
    assert session.captured_headers.get("If-None-Match") == 'W/"cached-etag-value"'


@pytest.mark.asyncio
async def test_get_latest_version_returns_cached_on_304(monkeypatch, tmp_path):
    """A 304 Not Modified means "the cached version is still current". The
    function must read the local version cache instead of erroring or hitting
    the network again."""
    etag_file = tmp_path / "etag"
    etag_file.write_text('W/"server-etag"', encoding="utf-8")
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("4.5.6", encoding="utf-8")

    monkeypatch.setattr(update, "LATEST_VERSION_ETAG_FILE", etag_file)
    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    response = _FakeJsonResponse(status=304)
    session = _FakeSession(response)

    assert await update._get_latest_version(session) == "4.5.6"  # type: ignore[arg-type]
    # ETag must remain — we got 304, so the server-side resource is unchanged
    # and our cache is valid:
    assert etag_file.read_text(encoding="utf-8") == 'W/"server-etag"'


@pytest.mark.asyncio
async def test_get_latest_version_clears_etag_on_304_with_empty_cache(monkeypatch, tmp_path):
    """Edge case: cached ETag but missing version cache (e.g. user manually
    cleared $XDG_DATA_HOME). Returning None and dropping the etag forces a
    real refetch on the next call instead of getting stuck in a 304 loop."""
    etag_file = tmp_path / "etag"
    etag_file.write_text('W/"orphan-etag"', encoding="utf-8")
    latest_file = tmp_path / "latest.txt"  # intentionally not created

    monkeypatch.setattr(update, "LATEST_VERSION_ETAG_FILE", etag_file)
    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    response = _FakeJsonResponse(status=304)
    session = _FakeSession(response)

    assert await update._get_latest_version(session) is None  # type: ignore[arg-type]
    assert not etag_file.exists()


@pytest.mark.asyncio
async def test_get_latest_version_writes_etag_on_200(monkeypatch, tmp_path):
    """When the server returns 200 with a fresh ETag, we must persist it for
    the next request — otherwise we never benefit from conditional caching."""
    etag_file = tmp_path / "etag"  # not yet created

    monkeypatch.setattr(update, "LATEST_VERSION_ETAG_FILE", etag_file)
    response = _FakeJsonResponse(
        status=200, json_data={"tag_name": "v9.0.0"}, etag='W/"freshly-served"'
    )
    session = _FakeSession(response)

    assert await update._get_latest_version(session) == "9.0.0"  # type: ignore[arg-type]
    assert etag_file.read_text(encoding="utf-8") == 'W/"freshly-served"'
    # No cached etag was sent on the first call:
    assert session.captured_headers is not None
    assert "If-None-Match" not in session.captured_headers


@pytest.mark.asyncio
async def test_resolve_latest_version_can_force_refresh(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("3.1.0", encoding="utf-8")
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print_output: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print_output, check_only))
        latest_file.write_text("3.2.0", encoding="utf-8")
        return update.UpdateResult.UPDATE_AVAILABLE

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: False)
    monkeypatch.setattr(update, "do_update", fake_do_update)

    assert await update._resolve_latest_version_for_prompt(force_refresh=True) == "3.2.0"
    assert calls == [(False, True)]
    assert last_check_file.exists()


@pytest.mark.asyncio
async def test_do_update_on_windows_spawns_detached_and_exits(monkeypatch, tmp_path):
    spawned: list[list[str]] = []

    async def fake_get_latest(session):
        return "999.0.0"

    async def fake_unavailable(session, latest_version: str, upgrade_command: list[str]):
        return None

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", tmp_path / "latest.txt")
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(update, "_update_candidate_unavailable_reason", fake_unavailable)
    monkeypatch.setattr(update, "_is_windows", lambda: True)

    def fake_spawn(cmd: list[str]) -> bool:
        spawned.append(cmd)
        return True

    monkeypatch.setattr(update, "_spawn_detached_windows_upgrade", fake_spawn)

    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(update.asyncio, "sleep", _noop_sleep)

    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called on Windows path")

    monkeypatch.setattr(update.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        await update.do_update(print_output=False, check_only=False)

    assert excinfo.value.code == 0
    assert spawned and "pythinker-code" in spawned[0]


def test_run_upgrade_command_streams_subprocess_output(monkeypatch):
    messages: list[str] = []
    launched: list[list[str]] = []

    class FakeProc:
        stdout = ["first line\n", "second line\n"]

        def wait(self, *, timeout: float) -> int:
            assert timeout == update.UPGRADE_COMMAND_TIMEOUT_SECONDS
            return 0

    def fake_popen(command, **kwargs):
        launched.append(command)
        assert kwargs["stdout"] is update.subprocess.PIPE
        assert kwargs["stderr"] is update.subprocess.STDOUT
        assert kwargs["text"] is True
        return FakeProc()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    returncode = update._run_upgrade_command(
        ["uv", "tool", "upgrade", "pythinker-code"],
        print_output=False,
        output_callback=messages.append,
    )

    assert returncode == 0
    assert launched == [["uv", "tool", "upgrade", "pythinker-code"]]
    assert messages == ["first line", "second line"]


@pytest.mark.asyncio
async def test_do_update_reports_non_native_upgrade_failure_to_callback(monkeypatch, tmp_path):
    messages: list[str] = []

    async def fake_get_latest(session):
        return "999.0.0"

    async def fake_unavailable(session, latest_version: str, upgrade_command: list[str]):
        return None

    def fake_run_upgrade_command(command, *, print_output: bool, output_callback):
        assert command == ["uv", "tool", "upgrade", "pythinker-code"]
        assert print_output is False
        assert output_callback is not None
        output_callback("installer said no")
        return 2

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", tmp_path / "latest.txt")
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(update, "_update_candidate_unavailable_reason", fake_unavailable)
    monkeypatch.setattr(
        update,
        "_detect_upgrade_command",
        lambda: ["uv", "tool", "upgrade", "pythinker-code"],
    )
    monkeypatch.setattr(update, "_run_upgrade_command", fake_run_upgrade_command)

    result = await update.do_update(print_output=False, output_callback=messages.append)

    assert result is update.UpdateResult.FAILED
    assert "installer said no" in messages
    assert any("Upgrade failed" in message for message in messages)


@pytest.mark.asyncio
async def test_do_update_uses_native_installer_marker(monkeypatch, tmp_path):
    native_versions: list[str] = []

    async def fake_get_latest(session):
        return "999.0.0"

    async def fake_native_update(latest_version: str) -> update.UpdateResult:
        native_versions.append(latest_version)
        return update.UpdateResult.UPDATED

    def fake_run(*args, **kwargs):
        raise AssertionError("native updates must not invoke uv/pip subprocesses")

    async def fake_unavailable(session, latest_version: str, upgrade_command: list[str]):
        return None

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", tmp_path / "latest.txt")
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(update, "_update_candidate_unavailable_reason", fake_unavailable)
    monkeypatch.setattr(update, "_detect_upgrade_command", lambda: [update.NATIVE_INSTALLER_MARKER])
    monkeypatch.setattr(update, "_maybe_run_native_update", fake_native_update)
    monkeypatch.setattr(update.subprocess, "run", fake_run)

    assert (
        await update.do_update(print_output=False, check_only=False) is update.UpdateResult.UPDATED
    )
    assert native_versions == ["999.0.0"]


def test_spawn_detached_windows_upgrade_uses_real_command_not_powershell(monkeypatch):
    launched: list[tuple[list[str], dict[str, object]]] = []

    monkeypatch.setattr(update, "_is_windows", lambda: True)
    monkeypatch.setattr(update, "which", lambda name: f"C:\\Tools\\{name}.exe")

    def fake_popen(args, **kwargs):
        launched.append((args, kwargs))
        return object()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    assert update._spawn_detached_windows_upgrade(["uv", "tool", "upgrade", "pythinker-code"])
    assert launched == [
        (
            ["C:\\Tools\\uv.exe", "tool", "upgrade", "pythinker-code"],
            {"creationflags": 0x00000010 | 0x00000200, "close_fds": True},
        )
    ]


def test_spawn_detached_windows_installer_uses_inno_directly_not_powershell(monkeypatch, tmp_path):
    installer = tmp_path / "PythinkerSetup-999.0.0.exe"
    installer.write_bytes(b"")
    launched: list[tuple[list[str], dict[str, object]]] = []

    monkeypatch.setattr(update, "_is_windows", lambda: True)

    def fake_popen(args, **kwargs):
        launched.append((args, kwargs))
        return object()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    assert update._spawn_detached_windows_installer(installer)
    assert launched == [
        (
            [
                str(installer),
                "/SILENT",
                "/NORESTART",
                "/CURRENTUSER",
                "/CLOSEAPPLICATIONS",
                "/NORESTARTAPPLICATIONS",
            ],
            {"creationflags": 0x00000200, "close_fds": True},
        )
    ]


def test_run_native_installer_detaches_on_windows(monkeypatch, tmp_path):
    installer = tmp_path / "PythinkerSetup-999.0.0.exe"
    installer.write_bytes(b"")
    spawned: list[object] = []

    monkeypatch.setattr(
        update, "_spawn_detached_windows_installer", lambda path: spawned.append(path) or True
    )

    with pytest.raises(SystemExit) as excinfo:
        update._run_native_installer(installer)

    assert excinfo.value.code == 0
    assert spawned == [installer]


def test_run_native_installer_reports_fallback_spawn_failure(monkeypatch, tmp_path):
    installer = tmp_path / "PythinkerSetup-999.0.0.exe"
    installer.write_bytes(b"")

    monkeypatch.setattr(update, "_spawn_detached_windows_installer", lambda path: False)

    def fake_popen(*args, **kwargs):
        raise OSError("blocked")

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    with pytest.raises(typer.Exit) as excinfo:
        update._run_native_installer(installer)

    assert excinfo.value.exit_code == 1


def test_version_from_release_payload_parses_v_tag():
    assert update._version_from_release_payload({"tag_name": "v1.2.3"}) == "1.2.3"
    assert update._version_from_release_payload({"tag_name": "pythinker-code-v1.2.3"}) is None


def test_linux_package_asset_names(monkeypatch):
    monkeypatch.setattr(update.platform, "machine", lambda: "x86_64")

    assert update._linux_package_asset_name("1.2.3", "deb") == "pythinker-code_1.2.3_amd64.deb"
    assert update._linux_package_asset_name("1.2.3", "rpm") == "pythinker-code-1.2.3.x86_64.rpm"


def test_linux_package_install_command_prefers_apt_get_for_deb(monkeypatch, tmp_path):
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"apt-get", "dpkg", "sudo"} else None

    monkeypatch.setattr(update, "which", fake_which)
    monkeypatch.setattr(update.os, "geteuid", lambda: 1000, raising=False)

    command = update._linux_package_install_command(tmp_path / "pkg.deb", "deb")

    assert command == ["sudo", "apt-get", "install", "-y", str(tmp_path / "pkg.deb")]


def test_linux_package_install_command_falls_back_to_dpkg_for_deb(monkeypatch, tmp_path):
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"dpkg", "sudo"} else None

    monkeypatch.setattr(update, "which", fake_which)
    monkeypatch.setattr(update.os, "geteuid", lambda: 1000, raising=False)

    command = update._linux_package_install_command(tmp_path / "pkg.deb", "deb")

    assert command == ["sudo", "dpkg", "-i", str(tmp_path / "pkg.deb")]


@pytest.mark.asyncio
async def test_native_update_uses_linux_package_asset_for_system_package(monkeypatch, tmp_path):
    installed: list[tuple[object, str]] = []
    fetched_assets: list[str] = []

    async def fake_fetch(session, asset_name: str, channel: str):
        fetched_assets.append(asset_name)
        return "https://example.invalid/pkg", "a" * 64

    async def fake_download(session, asset_name: str, download_url: str, destination):
        destination.write_bytes(b"package")
        return update.UpdateResult.UPDATED

    def fake_install(asset, package_kind: str) -> update.UpdateResult:
        installed.append((asset.name, package_kind))
        return update.UpdateResult.UPDATED

    monkeypatch.setattr(update.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(update, "_is_windows", lambda: False)
    monkeypatch.setattr(update, "_installed_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(update, "_fetch_native_release_asset", fake_fetch)
    monkeypatch.setattr(update, "_download_native_asset", fake_download)
    monkeypatch.setattr(update, "_verify_sha256", lambda path, expected: True)
    monkeypatch.setattr(update, "_install_linux_package", fake_install)

    assert await update._maybe_run_native_update("1.2.3") is update.UpdateResult.UPDATED
    assert fetched_assets == ["pythinker-code_1.2.3_amd64.deb"]
    assert installed == [("pythinker-code_1.2.3_amd64.deb", "deb")]


@pytest.mark.asyncio
async def test_native_update_cleans_up_tmpdir_on_success(monkeypatch, tmp_path):
    """The Linux/Mac install path must release the ~50-100MB staging tmpdir
    on every update. Pre-fix this leaked into /tmp on every update."""
    captured_tmpdirs: list[Path] = []

    async def fake_fetch(session, asset_name: str, channel: str):
        return "https://example.invalid/pkg", "a" * 64

    async def fake_download(session, asset_name: str, download_url: str, destination):
        destination.write_bytes(b"package-bytes")
        return update.UpdateResult.UPDATED

    def fake_install(asset, package_kind: str) -> update.UpdateResult:
        # Snapshot tmpdir while the install is mid-flight: cleanup must NOT
        # have run yet — the installer needs the asset on disk.
        captured_tmpdirs.append(asset.parent)
        assert asset.exists(), "asset must still exist while installer runs"
        return update.UpdateResult.UPDATED

    monkeypatch.setattr(update.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(update, "_is_windows", lambda: False)
    monkeypatch.setattr(update, "_installed_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(update, "_fetch_native_release_asset", fake_fetch)
    monkeypatch.setattr(update, "_download_native_asset", fake_download)
    monkeypatch.setattr(update, "_verify_sha256", lambda path, expected: True)
    monkeypatch.setattr(update, "_install_linux_package", fake_install)

    result = await update._maybe_run_native_update("1.2.3")

    assert result is update.UpdateResult.UPDATED
    assert len(captured_tmpdirs) == 1
    # Post-install, the staging tmpdir must be gone:
    assert not captured_tmpdirs[0].exists(), (
        "tmpdir leaked after install — /tmp will fill with stale installers"
    )


@pytest.mark.asyncio
async def test_native_update_cleans_up_tmpdir_on_failure(monkeypatch, tmp_path):
    """A SHA mismatch (or any install-time failure) must still release tmpdir
    so a failed update doesn't leave a half-broken installer + extract dir
    sitting in /tmp until reboot."""
    captured_tmpdirs: list[Path] = []

    async def fake_fetch(session, asset_name: str, channel: str):
        return "https://example.invalid/pkg", "a" * 64

    async def fake_download(session, asset_name: str, download_url: str, destination):
        destination.write_bytes(b"package-bytes")
        captured_tmpdirs.append(destination.parent)
        return update.UpdateResult.UPDATED

    monkeypatch.setattr(update.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(update, "_is_windows", lambda: False)
    monkeypatch.setattr(update, "_installed_linux_package_kind", lambda: "deb")
    monkeypatch.setattr(update, "_fetch_native_release_asset", fake_fetch)
    monkeypatch.setattr(update, "_download_native_asset", fake_download)
    # Simulate a SHA verification failure:
    monkeypatch.setattr(update, "_verify_sha256", lambda path, expected: False)

    result = await update._maybe_run_native_update("1.2.3")

    assert result is update.UpdateResult.FAILED
    assert len(captured_tmpdirs) == 1
    assert not captured_tmpdirs[0].exists()


def test_detect_upgrade_command_uses_brew_for_homebrew_formula(monkeypatch):
    monkeypatch.setattr(update, "_is_native_build", lambda: True)
    monkeypatch.setattr(
        update.sys,
        "executable",
        "/opt/homebrew/Cellar/pythinker-code/1.2.3/libexec/bin/python",
    )

    assert update._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


def test_update_prompt_text_shows_version_and_command(monkeypatch):
    rendered = Console(width=100, record=True, color_system=None)
    monkeypatch.setattr(update, "console", rendered)
    monkeypatch.setattr(
        update,
        "_detect_upgrade_command",
        lambda: ["uv", "tool", "upgrade", "pythinker-code"],
    )

    text = update._update_prompt_text("1.2.0", "1.3.0")
    rendered.print(text)
    output = rendered.export_text()

    assert "✨ Update available! 1.2.0 -> 1.3.0" in output
    assert "Release notes:" in output
    assert "uv tool upgrade pythinker-code" in output


@pytest.mark.asyncio
async def test_run_awaits_pre_start_update_before_auto_update(runtime, tmp_path, monkeypatch):
    """Regression (efe101c/#63): Shell.run() must await prompt_pre_start_update()
    — the blocking update menu — before scheduling the _auto_update background
    toast. The menu was silently unwired while its unit tests stayed green; this
    pins the wiring so it can't regress again unnoticed.
    """
    from unittest.mock import AsyncMock, MagicMock

    from pythinker_core.tooling.empty import EmptyToolset

    from pythinker_code.soul.agent import Agent
    from pythinker_code.soul.context import Context
    from pythinker_code.soul.pythinkersoul import PythinkerSoul
    from pythinker_code.ui.shell import Shell

    monkeypatch.delenv("PYTHINKER_CLI_NO_AUTO_UPDATE", raising=False)

    agent = Agent(name="Test", system_prompt="test", toolset=EmptyToolset(), runtime=runtime)
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "h.jsonl"))
    shell = Shell(soul)

    class _PromptReached(Exception):
        pass

    # Patch the name where run() looks it up (imported into the ui.shell module).
    prompt_mock = AsyncMock(side_effect=_PromptReached)
    monkeypatch.setattr("pythinker_code.ui.shell.prompt_pre_start_update", prompt_mock)
    # If auto_update were scheduled before the prompt, this spy would be called.
    auto_update_mock = MagicMock(name="_auto_update")
    monkeypatch.setattr(shell, "_auto_update", auto_update_mock)

    # The sentinel is the real guard: _PromptReached is only reachable if run()
    # actually awaits the (patched) prompt, so it pins prompt-before-auto_update.
    # If the wiring were removed, run() would instead schedule the un-awaited
    # MagicMock _auto_update and fail at create_task (TypeError) — still a failure,
    # just a noisier one.
    with pytest.raises(_PromptReached):
        await shell.run()

    prompt_mock.assert_awaited_once()
    auto_update_mock.assert_not_called()


# ---------------------------------------------------------------------------
# welcome_update_target and consume_whats_new
# ---------------------------------------------------------------------------


def test_welcome_update_target_returns_newer_cached_version(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("99.0.0", encoding="utf-8")
    dismissed_file = tmp_path / "dismissed.txt"

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "DISMISSED_VERSION_FILE", dismissed_file)
    monkeypatch.setattr(update, "_auto_update_disabled", lambda: False)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)

    result = update.welcome_update_target()
    assert result == "99.0.0"


def test_welcome_update_target_not_suppressed_by_session_skip(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("99.0.0", encoding="utf-8")
    dismissed_file = tmp_path / "dismissed.txt"

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "DISMISSED_VERSION_FILE", dismissed_file)
    monkeypatch.setattr(update, "_auto_update_disabled", lambda: False)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    # Simulate that the user chose "Skip this session" on the modal.
    monkeypatch.setattr(update, "_skipped_version_this_session", "99.0.0")

    # welcome_update_target does NOT suppress session-skips (that's its purpose).
    assert update.welcome_update_target() == "99.0.0"


def test_welcome_update_target_suppressed_by_dismiss(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("99.0.0", encoding="utf-8")
    dismissed_file = tmp_path / "dismissed.txt"
    dismissed_file.write_text("99.0.0", encoding="utf-8")

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "DISMISSED_VERSION_FILE", dismissed_file)
    monkeypatch.setattr(update, "_auto_update_disabled", lambda: False)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)

    assert update.welcome_update_target() is None


def test_welcome_update_target_suppressed_for_source_checkout(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("99.0.0", encoding="utf-8")

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: True)

    assert update.welcome_update_target() is None


def test_consume_whats_new_baseline_on_first_launch(monkeypatch, tmp_path):
    from pythinker_code.constant import VERSION as current_version

    last_seen_file = tmp_path / "last_seen.txt"

    monkeypatch.setattr(update, "LAST_SEEN_VERSION_FILE", last_seen_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)

    # First-ever launch: no file → write the current version as baseline, return None.
    result = update.consume_whats_new()
    assert result is None
    assert last_seen_file.read_text(encoding="utf-8").strip() == current_version


def test_consume_whats_new_returns_version_after_upgrade(monkeypatch, tmp_path):
    from pythinker_code.constant import VERSION as current_version

    last_seen_file = tmp_path / "last_seen.txt"
    last_seen_file.write_text("0.0.1", encoding="utf-8")  # older than current

    monkeypatch.setattr(update, "LAST_SEEN_VERSION_FILE", last_seen_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)

    result = update.consume_whats_new()
    assert result == current_version
    assert last_seen_file.read_text(encoding="utf-8").strip() == current_version


def test_consume_whats_new_no_disk_write_in_steady_state(monkeypatch, tmp_path):
    from pythinker_code.constant import VERSION as current_version

    last_seen_file = tmp_path / "last_seen.txt"
    last_seen_file.write_text(current_version, encoding="utf-8")
    mtime_before = last_seen_file.stat().st_mtime

    monkeypatch.setattr(update, "LAST_SEEN_VERSION_FILE", last_seen_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)

    result = update.consume_whats_new()
    assert result is None
    # File must not have been rewritten (mtime unchanged).
    assert last_seen_file.stat().st_mtime == mtime_before


def test_consume_whats_new_suppressed_for_source_checkout(monkeypatch, tmp_path):
    last_seen_file = tmp_path / "last_seen.txt"
    last_seen_file.write_text("0.0.1", encoding="utf-8")

    monkeypatch.setattr(update, "LAST_SEEN_VERSION_FILE", last_seen_file)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: True)

    assert update.consume_whats_new() is None


def test_brew_unchanged_when_pythinker_managed_unset(monkeypatch):
    monkeypatch.delenv("PYTHINKER_MANAGED", raising=False)
    monkeypatch.setattr(
        update.sys,
        "executable",
        "/opt/homebrew/Cellar/pythinker-code/0.27.0/libexec/bin/python",
    )
    monkeypatch.setattr(update, "_is_native_build", lambda: False)
    assert update._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


def test_brew_unchanged_even_with_native_marker(monkeypatch):
    # The .pythinker-native marker also trips _is_native_build(); the cellar
    # path-sniff must win first so brew installs stay on `brew upgrade`.
    monkeypatch.delenv("PYTHINKER_MANAGED", raising=False)
    monkeypatch.setattr(
        update.sys,
        "executable",
        "/opt/homebrew/Cellar/pythinker-code/0.27.0/libexec/bin/python",
    )
    monkeypatch.setattr(update, "_is_native_build", lambda: True)
    assert update._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


def test_pythinker_managed_channel_short_circuits(monkeypatch):
    monkeypatch.setenv("PYTHINKER_MANAGED", "docker")
    monkeypatch.setattr(update.sys, "executable", "/usr/local/bin/python")
    cmd = update._detect_upgrade_command()
    assert cmd == [update.MANAGED_CHANNEL_MARKER, "docker"]


def test_update_prompt_text_renders_managed_channel_hint(monkeypatch):
    # The contract requires a usable channel-native hint, not a raw marker.
    monkeypatch.setenv("PYTHINKER_MANAGED", "docker")
    monkeypatch.setattr(update.sys, "executable", "/usr/local/bin/python")
    text = update._update_prompt_text("0.27.0", "0.28.0")
    rendered = text.plain
    assert "docker" in rendered
    assert update.MANAGED_CHANNEL_MARKER not in rendered
