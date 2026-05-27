from __future__ import annotations

from types import SimpleNamespace

import pytest
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

    async def fake_do_update(*, print: bool) -> update.UpdateResult:
        assert print is True
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

    async def fail_do_update(*, print: bool) -> update.UpdateResult:
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

    async def fail_do_update(*, print: bool) -> update.UpdateResult:
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

    async def fail_do_update(*, print: bool) -> update.UpdateResult:
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


@pytest.mark.asyncio
async def test_resolve_latest_version_fetches_when_due(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print, check_only))
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

    async def fake_do_update(*, print: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print, check_only))
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

    async def fail_do_update(*, print: bool, check_only: bool) -> update.UpdateResult:
        raise AssertionError("must not hit the network when the throttle is not due")

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: False)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    assert await update._resolve_latest_version_for_prompt() == "3.1.0"


@pytest.mark.asyncio
async def test_resolve_latest_version_can_force_refresh(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("3.1.0", encoding="utf-8")
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print, check_only))
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

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", tmp_path / "latest.txt")
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
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
        await update.do_update(print=False, check_only=False)

    assert excinfo.value.code == 0
    assert spawned and "pythinker-code" in spawned[0]


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

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", tmp_path / "latest.txt")
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(update, "_detect_upgrade_command", lambda: [update.NATIVE_INSTALLER_MARKER])
    monkeypatch.setattr(update, "_maybe_run_native_update", fake_native_update)
    monkeypatch.setattr(update.subprocess, "run", fake_run)

    assert await update.do_update(print=False, check_only=False) is update.UpdateResult.UPDATED
    assert native_versions == ["999.0.0"]


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


def test_version_from_release_payload_parses_v_tag():
    assert update._version_from_release_payload({"tag_name": "v1.2.3"}) == "1.2.3"
    assert update._version_from_release_payload({"tag_name": "pythinker-code-v1.2.3"}) is None


def test_linux_package_asset_names(monkeypatch):
    monkeypatch.setattr(update.platform, "machine", lambda: "x86_64")

    assert update._linux_package_asset_name("1.2.3", "deb") == "pythinker-code_1.2.3_amd64.deb"
    assert update._linux_package_asset_name("1.2.3", "rpm") == "pythinker-code-1.2.3.x86_64.rpm"


def test_linux_package_install_command_prefers_sudo_for_deb(monkeypatch, tmp_path):
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
