# Changelog

## Unreleased

## 2.3.0 (2026-05-09)

Telemetry & observability audit.

- New `pythinker_code/telemetry/errors.py` helper `report_handled_error(exc, *, site, tool=None, **attrs)` forwards caught-and-rendered exceptions to both Sentry/Bugsink and the OTel `error` event stream. Both forwarding paths are `contextlib.suppress`-wrapped so monitoring can never break the host program.
- 38 silent-catch sites instrumented across `tools/`, `auth/`, `soul/`, `acp/`, `hooks/`, `subagents/`. Tool failures, OAuth errors, MCP server hiccups, hook callback failures, and subagent crashes now reach Bugsink and SigNoz.
- `pythinker_code/telemetry/otel.py`: TracerProvider now uses `ParentBased(TraceIdRatioBased(rate))` driven by `PYTHINKER_OTEL_TRACE_SAMPLE_RATE` (default 1.0).
- New `pythinker.mcp.call` span around every MCPTool RPC.
- New `/report-error` slash command (aliases `/report`, `/report-error`).
- `docs/en/reference/telemetry.md` documents the full telemetry contract.
- `chore(test)`: updated google-genai snapshot for pydantic 2.13.4 + google-genai 2.0.0.


## 2.2.1 (2026-05-09)

CI hardening: macOS binary build is now optional-codesign.

- `.github/workflows/release-pythinker-cli.yml`: detect whether `APPLE_CERTIFICATE_P12` and `APPLE_NOTARIZATION_KEY_P8` repo secrets are configured. When they aren't, skip the keychain setup, codesign, and notarization steps and ship an ad-hoc-signed PyInstaller binary instead of failing the whole release. The 2.2.0 release run failed because those secrets were empty in CI; this makes the release matrix all-green even without an Apple Developer cert.
- `.github/workflows/release-pythinker-cli.yml`: add `skip-existing: true` to `pypa/gh-action-pypi-publish` so re-runs of the release workflow against an already-published version are no-ops instead of HTTP 400 errors.
- macOS-arm64 binary downloads from the GitHub Release page will now show a Gatekeeper warning on first launch when the secrets aren't configured. Users can clear it with `xattr -d com.apple.quarantine ./pythinker`. PyPI install (`pip install pythinker-code`) is unaffected.

## 2.2.0 (2026-05-09)

Installer UX: animated logo + Windows PATH automation.

- `scripts/install.sh`: Tetris-style logo animation. Pieces (walls, bars, eyes, ears, antenna) fall from above the canvas one at a time and settle into the robot head before install proceeds. Static logo remains the fallback for non-TTY / `NO_COLOR` / `TERM=dumb` / `CI=1` / `PYTHINKER_NO_ANIMATION=1`. Tunables: `PYTHINKER_LOGO_FRAME_DELAY` and `PYTHINKER_LOGO_STAGGER_DELAY` (seconds).
- `scripts/install.ps1`: same animation, PowerShell port. Tunables: `PYTHINKER_LOGO_FRAME_DELAY_MS` and `PYTHINKER_LOGO_STAGGER_DELAY_MS` (milliseconds).
- `scripts/install.ps1`: idempotently append `$USERPROFILE\.local\bin` to the User PATH via `[Environment]::SetEnvironmentVariable` and broadcast `WM_SETTINGCHANGE` so future shells (and Explorer-spawned children) pick up the new PATH automatically. No-op when the directory is already present.
- `scripts/install.ps1`: force `[Console]::OutputEncoding = UTF8` so the box-drawing characters render correctly on Windows hosts.

## 2.1.2 (2026-05-09)

Windows installer fix.

- `scripts/install.ps1`: dot-source Astral's `uv` bootstrap inside `& { ... }` instead of spawning `powershell -File`, so `$env:PATH` updates land in the running process.
- `scripts/install.ps1`: refresh PATH after `uv tool install` and verify `pythinker` resolves before printing success; otherwise emit the absolute shim path.
- README: invoke the downloaded `install.ps1` with `& $installer` (current shell) instead of a `powershell -NoProfile -File $installer` subprocess. `uv`, `uvx`, and `pythinker` are now usable in the calling shell as soon as the installer exits.
- `tests/test_installation_docs.py`: lock in current-session invocation in the README and a dot-sourced `uv` bootstrap in `install.ps1`.

## 2.1.1 (2026-05-08)

Documentation refresh.

- README: image and key file links converted to absolute GitHub URLs so the project page on PyPI renders the logo, demo GIFs, and architecture diagram correctly.
- README: added a "What's New in 2.1.0" section summarising the TUI CLI and slash-command enhancements.
- README: corrected the License section to Apache-2.0 (matches `pyproject.toml` and the `LICENSE` badge).

## 2.1.0 (2026-05-08)

TUI CLI design and slash command enhancements.

- New selectors package — interactive `/theme`, `/thinking`, `/model`, `/login`, `/settings`, `/extension`, and `/show-images` panels replace inline numeric/text prompts.
- New `/thinking` slash command for adjusting reasoning effort at runtime.
- `SettingsList` component + `/settings` selector for live `Config` editing (theme, default model, TUI style, default thinking, telemetry).
- Selector framework: `SelectorHeader` sentinel and per-row `on_change` callback.
- Card-style TUI polish: bordered shell card, footer/toolbar, tool renderers (read/write/edit/grep/find/bash/agent) and a diff component; subagent tool cards get a running-dots spinner.
- Pythinker-branded slash menu, input row, and tool execution components.
- Prompt template discovery simplified to `.pythinker/prompts` at project and user scope (legacy directory lookup removed).
- TUI style flag now accepts only `card` (default) or `pythinker`; the legacy alias has been dropped.

- Update notifier: standalone "Update Available" banner shown above the welcome panel when a newer release is on PyPI; suppressed by `PYTHINKER_CLI_NO_AUTO_UPDATE=1`.
- New `pythinker update` subcommand (`--check` for a non-installing check) that auto-detects the install method (`uv tool`, `pipx`, or `pip`) and runs the matching upgrade command.
- Image paste placeholder now renders as `[Image #N]` in the input/buffer (mirroring `[Pasted text #N +K lines]`); history serialization keeps the canonical `[image:<id>,WxH]` form so attachments still resolve cross-session.
- Lower default paste-placeholderize thresholds to 200 chars / 5 lines (was 1000 / 15) so medium-length pastes collapse into `[Pasted text #N]` instead of overflowing the compact input window. Override via `PYTHINKER_CLI_PASTE_CHAR_THRESHOLD` and `PYTHINKER_CLI_PASTE_LINE_THRESHOLD`.

## 1.0.0 (2026-05-06)

Initial release of Pythinker CLI.

- Interactive terminal AI coding agent with shell command mode (Ctrl-X)
- ACP server (`pythinker acp`) for IDE integrations such as Zed and JetBrains
- MCP tool support: `pythinker mcp` sub-commands and ad-hoc `--mcp-config-file`
- Multi-provider auth: OpenAI, OpenAI Codex, Anthropic, OpenRouter, DeepSeek, MiniMax, Opencode-Go
- Skills, plugins, and slash commands across project / user / built-in scopes
- Session persistence with subagents and approval workflows
- Print mode and wire mode for non-interactive and programmatic use
- Plan mode for read-only research and design before code changes
- YOLO mode (`--yolo` / `/yolo`) to dangerously skip permission approvals while keeping the user reachable via `AskUserQuestion`
- Auto mode (`--auto` / `/auto`) for unattended runs: auto-approves tool calls and auto-dismisses `AskUserQuestion` so the agent finishes end-to-end without a user
