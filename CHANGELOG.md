# Changelog

## Unreleased

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
