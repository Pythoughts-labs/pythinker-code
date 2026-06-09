# Changelog

All notable changes to `pythinker-code` are tracked in this file.

Pythinker Code uses a `0.MINOR.PATCH` version scheme. `MINOR` is a release
counter that continues advancing with each release. `PATCH` is reserved for
hotfixes against an already-released `MINOR`. There is no `1.0.0` milestone
planned on this line.

Releases earlier than `0.8.0` were published as `pythinker-code` 1.x/2.x
under a different scheme. The full pre-`0.8.0` history is preserved in
[`docs/history/CHANGELOG-pre-0.8.0.md`](docs/history/CHANGELOG-pre-0.8.0.md).
All 1.x and 2.x releases have been yanked from PyPI and removed from the
GitHub Releases page; `0.8.0` is the new starting line.

## Unreleased

- **Refreshed TUI theme and Catppuccin syntax highlighting.** The interface adopts a brand periwinkle/indigo accent (`#B3B9F4` dark / `#0B114E` light) with a reharmonized selection tint, and code blocks now highlight with Catppuccin Mocha (dark) / Latte (light), adaptive to the active theme — implemented as foreground-only Pygments styles with no new dependency. Markdown inline code and links render terminal-native cyan, blockquotes green, and ordered-list markers bright blue (so they adapt per terminal), and user messages sit on a neutral grey block instead of the prior blue tint.
- **Homebrew updater no longer no-ops or false-reports success.** `pythinker update` on a Homebrew install now runs `brew update` to refresh the tap before `brew upgrade`, so a stale local tap clone can't pin the old formula and silently no-op ("0.37.0 already installed"). After upgrading it re-checks the installed version via `brew list --versions` and reports a clear failure instead of "Updated successfully!" when the version did not actually advance.
- **Friendlier usage-limit (429) messages and ChatGPT account switching.** When a provider returns a 429, Pythinker now renders a human-readable notice — the plan name, the reset window, and a dimmed `Server:` detail line (all markup-escaped) — instead of a raw error string. `/login` for ChatGPT now uses `prompt=login`, so you can switch between ChatGPT accounts instead of being silently kept on the previous session.
- **Agent phase-0 enhancements.** Adds a model-invocable cross-session Recall tool (search and read prior sessions on demand, sanitized and read-only for subagents), read-only MCP resources/prompts surfaced as tools, project-scoped `.pythinker/mcp.json` layering, subagent token/cost roll-up to the orchestrator, and truncated tool output that spills to disk with a recovery hint instead of being lost.
- **No more spurious `coroutine … was never awaited` warnings.** Dropped Sentry's `AsyncioIntegration`, whose `create_task` monkeypatch wrapped every coroutine and — when a task was cancelled before its first step during turn/prompt teardown — orphaned the inner coroutine, printing `WireUISide.receive` and prompt_toolkit "never awaited" `RuntimeWarning`s to the console. The integration added no spans (tracing/profiling are off), and exception capture for async tasks is preserved by the existing asyncio exception handler.
- **Read-only profile guard hardened against version-pinned interpreters.** Inline-code interpreter invocations that use a version-suffixed or absolute binary (`python3.14 -c …`, `/usr/bin/python3.12 -c …`, `node20 -e …`) are now classified as mutating/destructive just like the bare `python`/`node` forms, so they can no longer bypass a read-only subagent profile or skip destructive deliberation.
- **The agent sets up MCP servers on request instead of refusing.** Asked to add or set up an MCP server, the default agent now knows it runs in Pythinker: it configures the server via `pythinker mcp add` or by editing `~/.pythinker/mcp.json` / `./.pythinker/mcp.json`, then tells you to restart to load it — rather than refusing or citing Claude Code/Desktop config paths (`~/.claude.json`) it cannot use.

## 0.38.0 (2026-06-08)

- **Quieter `/login`.** Logging in no longer prints a `RuntimeWarning` about an un-awaited `redraw_in_future` coroutine. The prompt redraw throttle now uses a coroutine-free path (`max_render_postpone_time`), eliminating the warning emitted during the login prompt handoff.
- **Alibaba usage reporting.** `/usage` now ships a dedicated Alibaba adapter, so logging in with an Alibaba key produces a populated cost/quota panel instead of falling through to the no-adapter branch.
- **Live model pricing from models.dev.** Cost estimates in `/usage` and the session stats panel now pull per-model input/output pricing from the models.dev catalog (fetched once and cached for 24 hours), improving cost accuracy across providers.
- **More robust ripgrep resolution.** File search now verifies that a bundled `rg` binary can actually execute on the host platform and architecture before using it, falling back to a system or freshly downloaded ripgrep when the bundled one cannot run — fixing search failures on mismatched-architecture installs.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.38.0`, or use the native installer for your platform from the [Releases page](https://github.com/Pythoughts-labs/pythinker-code/releases/latest).

## 0.37.0 (2026-06-07)

- **Agent runtime tool visibility hardening.** `PythinkerToolset` now filters the tools advertised to the model by active execution policy, permission profile, root/subagent role, and plan-mode state while preserving execution-time guards as defense in depth.
- **Agent design upgrades.** Agent specs now carry mode/hidden/step/model-parameter metadata, built-in `ask` and `debug` primary agents are selectable with `--agent`, the new `scout` subagent handles external docs/API freshness research, and compaction summaries use a stable handoff-oriented structure.
- **Prompt-injection defense: `UntrustedData` wrapper.** All external content returned by `ReadFile` and `FetchURL` is now wrapped in `<untrusted_data id="NONCE">…</untrusted_data>` tags before being passed to the LLM, providing a clear boundary between trusted instructions and untrusted file/web content. The `UntrustedData` primitive escapes embedded closing tags to prevent breakout attacks.
- **Agent boundary artifacts.** New `CodingArtifact` / `VerificationResult` and `VulnerabilityArtifact` / `AuditVerdict` frozen dataclasses in `pythinker_code.utils.artifacts` enforce a typed information barrier between coder and verifier subagents.
- **Recon-first `planner` subagent.** A new read-only `planner` built-in agent type decomposes open-ended tasks into distinct parallel seed descriptions emitted as `<recon_seeds>` JSON, enabling structured fan-out before parallel workers start.
- **Coder artifact contract.** The `coder` subagent now emits a `<coding_artifact>` JSON block at the end of every response, providing structured handoff data (`files_changed`, `test_command`, `expected_behavior`, optional `edge_cases_claimed`) that the `verifier` subagent can consume directly.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.37.0`, or use the native installer for your platform from the [Releases page](https://github.com/Pythoughts-labs/pythinker-code/releases/latest).

## 0.36.0 (2026-06-05)

- **Alibaba DashScope multi-region fallback.** Logging in with a China-region key (`dashscope.aliyuncs.com`) against the default US Virginia endpoint now auto-detects the mismatch and reconfigures for the correct endpoint rather than failing with a misleading "API key is wrong" error.
- **Alibaba Token Plan compatibility (`sk-ws-`).** `/login alibaba` now requires the dedicated workspace Base URL shown in the Token Plan console instead of accepting a public `/models` response as credential validation. Dedicated workspace endpoints hide Kimi K2.6 when Alibaba advertises it without a working route, and use non-streaming Chat Completions for DeepSeek V3.2 because those endpoints return an empty SSE stream. Kimi requests on other Alibaba routes use DashScope's `enable_thinking` parameter.
- **Alibaba model catalog refresh.** Added Qwen3.7 Plus (1M context), Qwen3 Coder Plus, and Qwen3 Coder Flash. Removed `kimi-k2.5`, `glm-5`, and `MiniMax-M2.5` (absent from the live endpoint). Corrected Qwen3.7 Max context window to 1M tokens.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.36.0`, or use the native installer for your platform from the [Releases page](https://github.com/Pythoughts-labs/pythinker-code/releases/latest).

## 0.35.0 (2026-06-04)

- **Alibaba DashScope provider and MiniMax M3 catalog.** `/login alibaba` now configures Alibaba Cloud Model Studio / DashScope Token Plan models, including workspace-compatible endpoints and native GLM thinking behavior. MiniMax API-key login now defaults to MiniMax M3 with its larger context and multimodal capabilities.
- **Security review vulnerability intelligence.** `pythinker security-scan` can now parse dependency manifests, query OSV package advisories, look up CVE intelligence from NVD/EPSS/CISA KEV/GitHub/vendor feeds, and carry those leads into security-review prompts and reports as evidence-checked context.

## 0.34.0 (2026-06-03)

### What changed in this release

- **`/stats` usage dashboard.** New slash command opens an interactive prompt_toolkit TUI showing token and cost breakdown by provider/model across Today / This Week / Last Week / All Time. Powered by a static pricing table (`get_cost_usd`) and a session collector that walks `~/.pythinker/sessions/` wire files. `StatusUpdate` wire events now carry optional `model_name` / `provider_key` fields for per-step attribution.
- **Z AI provider auth.** Login/logout via API key, model discovery, and OAuth selector wired into the TUI and `refresh_managed_models`.
- **Moonshot provider auth.** Login/logout via API key, model discovery (Kimi K2.x catalog), OAuth selector wired into the TUI and `refresh_managed_models`.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.34.0`, or use the native installer for your OS (see the README install table).

## 0.33.0 (2026-06-03)

### What changed in this release

- **Three-scope config resolution (User → Project → Local).** `load_config()` now runs a five-step pipeline — Ingest → Guard → Merge → Env → Validate — merging `~/.pythinker/config.toml`, `.pythinker/config.toml`, and `.pythinker/config.local.toml` with type-based rules. Scalars use last-writer-wins; lists are concatenated (deduplication for `allowed_domains` and `extra_skill_dirs`); dicts are recursively merged. Scope-locked fields (`providers.*`, `services.*`, `feedback.api_key`) are blocked from project/local files with a clear error. The resolved config now tracks which files contributed via `source_scopes`. Local config files are auto-gitignored on first use. PYTHINKER_* environment variables overlay all file-sourced values.
- **Pythinker identity: developed by Pythoughts-labs.** Package metadata, `--version` output, and `pythinker info` now reflect Pythoughts-labs as the author organisation.
- **❓ question marker standardized across all question surfaces.** A new `QUESTION_MARKER` constant in `glyphs.py` replaces the inconsistent mix of `●` (inline transcript) and `?` (interactive panel, pager, prompt) with a single `❓` glyph (ASCII fallback: `?`) used everywhere.
- **Scratchpad isolated to current session; cleans up on interruption.** Agents no longer fast-skim all prior sessions' scratch files on startup, eliminating the post-interrupt confusion where stale planning from previous sessions was injected into a new session's context. Scratch files are now deleted on every session exit — success or interruption — so files no longer accumulate.
- **`SetTodoList` gated behind explicit plan approval.** The tool description and agent system prompt now require that todos are set only after the user agrees on the plan. During planning and exploration the tool must not be called; once set, the list is the single source of truth for execution with status-only updates.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.33.0`, or use the native installer for your OS (see the README install table).

## 0.32.0 (2026-06-03)

### What changed in this release

- **`pythinker mcp add` no longer crashes on Windows and Linux native builds.** The PyInstaller specs were using `collect_data_files()` which silently omits the `fastmcp-*.dist-info/` sibling directory; fastmcp calls `importlib.metadata.version("fastmcp")` at import time, so every `mcp add` / `mcp list` invocation raised `PackageNotFoundError`. Switched all three specs (Windows installer, Linux installer, macOS/tarball) to `copy_metadata()` — the PyInstaller-standard hook for bundling dist-info.
- **Pythinker work directories are automatically gitignored on startup.** When the agent starts inside a git repository, `.pythinker/`, `.pythinker-review/`, and `.pythinker-review-flow/` are silently appended to the project's `.gitignore` if missing, preventing local agent state from making the working tree dirty.
- **Old sessions and plan files are swept on startup.** Archived session directories under `~/.pythinker/sessions/` and hero-name plan files under `~/.pythinker/plans/` older than `session_retention_days` (default 30) are removed non-interactively at startup. Set `session_retention_days = 0` to disable.
- **Windows upgrade version display fix.** In-place upgrades no longer show a stale version number or re-trigger the update prompt. Inno Setup now wipes `_internal` before installing new files, preventing old `dist-info` directories from accumulating and causing `importlib.metadata` to report the previous version.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.32.0`, or use the native installer for your OS (see the README install table).

## 0.31.0 (2026-06-02)

### What changed in this release

- **Release promotion no longer stalls when the Homebrew tap is broken.** The `promote-release` workflow now gates only on platform assets and PyPI; a lagging or broken Homebrew tap emits a warning annotation and step summary note but no longer blocks the GitHub Release from reaching Latest.
- **Calmer, theme-aligned TUI rendering.** Transcript, recap, and tool-header output now use theme-standardized activity colors instead of hardcoded values, and Markdown tables render as a bordered grid (wide tables no longer collapse into a stacked-record list).
- **Auto-mode tool approval fails closed when unattended.** In auto/non-interactive runs, an action that still needs approval under the active safe-mode/trust policy is denied with guidance instead of waiting indefinitely for an absent user, and outside-workspace writes are never auto-approved. A destructive auto-approved action is now bounced once for deliberation whenever no user is present (regardless of config), so the obvious `--yolo --auto` combination is no longer more dangerous than the `autonomous_coding` profile; the `auto_deliberate_destructive_actions` setting extends that backstop to interactive `--yolo` sessions, where a user is present but approvals are skipped.
- **Yolo + auto mode hardened against silent over-reach.** Entering plan mode now requires confirmation in an interactive `--yolo` session (matching exit), so the plan-review checkpoint is preserved when a user is present. A `--yolo` run no longer clears or persists the workspace's safe-mode/trust state. A new `--no-yolo` flag forces yolo off for a run — overriding the `--yolo` flag, the `default_yolo` config, and any resumed session state. Resuming a session that restores yolo and/or auto now surfaces a startup warning so it is never silent.
- **`pythinker review` validates finding evidence.** Reviewflow assembles prompts from a shared security-knowledge manifest and validates findings, handling invalid ones without failing the whole review.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.31.0`, or use the native installer for your OS (see the README install table).

## 0.30.0 (2026-06-02)

### What changed in this release

- **ACP session close and auth errors are spec-compliant.** `session/close` now cancels any
  in-flight work and frees the session's runtime resources (MCP toolset, background refresh)
  before dropping it, instead of leaking them, per the ACP `session/close` requirement. The
  `authenticate` failure path now serializes its `authMethods` to plain dicts so the JSON-RPC
  error response no longer raises `TypeError` on encode.
- **Auto-mode destructive actions deliberate per turn and context.** Auto-deliberation now
  scopes destructive-command one-shots to the active execution context and LLM generation,
  so duplicate destructive calls in one response keep bouncing while later deliberate retries
  and isolated subagent calls are handled independently. If a destructive action is ever
  evaluated without that turn context, the gate now fails closed — it keeps deliberating
  rather than auto-approving the action.
- **Release packaging keeps SDK/core pins in lockstep.** The SDK's `pythinker-core`
  dependency is now updated by release automation and checked by CI/release validation,
  preventing no-sources binary builds from resolving against a stale core pin.
- **Routine dependency bumps with the breaking-change fallout fixed.** Upgrades `agent-client-protocol` to 0.10.1, `aiohttp` to 3.14.0, and `typer` to 0.26.5. Aligns the `pythinker-review` `typer` pin so the uv workspace resolves; migrates the ACP server to the 0.10 auth schema (`TerminalAuthMethod`) and expanded `Agent` protocol (`additional_directories`, `close_session`, session config options); and restores the optional-value behaviour of `--session`/`--resume` (interactive picker when used without an ID) under Typer 0.26's new argument parser.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.30.0`, or use the native installer for your OS (see the README install table).

## 0.29.0 (2026-06-01)

### What changed in this release

- **Reloads pick up MCP and model changes cleanly.** `/reload` now re-reads MCP server configuration added after startup, cleans up stale MCP/model-refresh resources during same-process reloads, and `/model` starts a fresh session when switching models so old context does not carry across providers.
- **Thinking effort controls and safer auto-mode decisions.** Thinking effort is now a first-class setting across the CLI, ACP, web config, and supported providers; Shift+Tab cycles available efforts in the shell, and auto-mode can deliberate with advisor feedback before sensitive or destructive approval flows.
- **Shell sessions get cleaner recaps and rendering.** The interactive shell can show turn recaps, includes hook stdout/stderr in the transcript, improves prompt/file-mention and tool-output spacing, and uses branded browser-login result pages.
- **MiniMax Token Plan model availability stays current.** MiniMax login and startup refresh now use the authenticated model catalog so Token Plan keys only keep models actually available to that key, while preserving user model preferences and isolating discovery failures from other provider refreshes.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.29.0`, or use the native installer for your OS (see the README install table).

## 0.28.0 (2026-05-31)

### What changed in this release

- **Repository moved to the Pythoughts-labs GitHub org.** All GitHub URLs, install scripts, CI configuration, and the default `/feedback` repository now point to `github.com/Pythoughts-labs/pythinker-code`; existing configs that still reference the previous owner are auto-migrated to the new default.
- **Broadened distribution channels for releases.** Releases now include best-effort Docker/GHCR, Scoop, Nix, and manual WinGet distribution plumbing with channel-native update markers where the installer format supports them.
- **Release preparation now uses a version single source of truth.** `scripts/release.py` rewrites derived release files from `pyproject.toml`, verifies version lockstep on every PR, enforces the frozen `pythinker-review==0.1.0` pin, and managed-channel installs now show channel-native update guidance instead of trying to self-update.
- **Node.js 24 CI with pinned, credential-checked workflows.** CI and release workflows now run on Node.js 24-backed GitHub Actions, pin action revisions to immutable commits, and preflight optional website/tap GitHub App credentials with clear errors or notices instead of opaque token failures.
- **Release pipeline hardening.** Migrate the pythinker-home website-sync dispatch to the org-owned `pythinker-release-bot` GitHub App and fail loud on an empty token; retire the dead pythinker-core API-docs gh-pages publish step; add exponential backoff to the native install scripts and fix the Windows installer's release-pagination cliff.
- **Redesigned startup welcome banner.** The banner now uses a cleaner footer-chip layout: the "What's new / Update available" chip sits on the panel's bottom border, the headline/strapline/help lines align beside the robot logo, and the info grid drops its vertical separator. The robot art and palette are unchanged.
- **Terminal-aware rendering for minimal and CI terminals.** The shell UI adapts to the terminal — ASCII glyph fallbacks for `TERM=dumb` and legacy Windows code pages, reduced-motion mode (`PYTHINKER_REDUCED_MOTION`), and `NO_COLOR`/`CLICOLOR` support that strips color cleanly — so output stays readable in CI logs, SSH panes, and bare terminals.
- **Windows updates avoid encoded PowerShell.** Native updates now launch the signed Inno installer directly with Restart Manager flags instead of a `powershell.exe -EncodedCommand` helper, reducing antivirus command-line heuristic false positives. Windows bootstrap installs use visible `/SILENT` progress instead of fully suppressed setup, and the installer build signs bundled PE files plus Inno's setup/uninstaller/temp copies when signing credentials are configured.
- **New `judge` subagent and redesigned default prompts.** Adds an independent LLM-as-judge quality-gate subagent — a cheap single spot-checking pass for high-stakes deliverables, after deterministic gates — and rewrites the default agent, plan, and system prompts for clearer, more efficient guidance.
- **`.pythinker/AGENTS.md` is no longer loaded as project instructions.** Only `AGENTS.md`/`agents.md` from the project root down to the working directory are merged. Move any instructions kept solely in `.pythinker/AGENTS.md` to a root or directory-level `AGENTS.md` (see breaking changes).
- **Read-only subagent profiles block network and git config-injection shell commands.** The `read_only`/`plan`/`review`/`verify` permission profiles now deny network clients (`curl`/`wget`/`ssh`/`git fetch`) and unsafe `git -c`/`--config-env`/`--exec-path` options that can execute arbitrary commands (for example via `core.pager`/`core.sshCommand`), closing a Shell-tool bypass of a read-only agent's no-web-tools intent.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.28.0`, or use the native installer for your OS (see the README install table).

## 0.27.0 (2026-05-31)

### What changed in this release

- **`/feedback` submits structured reports with redacted session context.** A new
  `/feedback [bug|feature|ux|wrong] [message]` command collects recent session context
  and strips sensitive file contents before sending, shows a confirmation preview, and
  falls back to opening a prefilled GitHub issue when direct submission is unavailable.
- **Fresh releases surface in the startup update prompt immediately.** The pre-start
  update prompt now revalidates a cached "already current" answer with a bounded
  conditional request instead of waiting for the 24-hour background-check throttle.
  Release promotion also waits for exact native assets, PyPI, and the Homebrew tap
  before marking a version latest, so installed clients no longer resolve a release
  before its install channel is ready.
- **Background agent recovery preserves terminal task state.** Recovery now re-reads
  task runtime under the store update lock before marking orphaned agent work
  recoverable, so a stale snapshot can no longer clobber a task that completed.
- **Project memory recall keeps the simple lexical path.** The unused SQLite FTS
  retriever seam and dead recall path argument are removed; collaborators now use
  a public memory-store root accessor instead of reaching into private methods.
- **Shell prompt echoes and background todo rows are clearer.** Transcript echoes now
  show the resolved submitted text for pasted-content placeholders, and background
  todo rows align continuation icons with the first row.
- **StrReplaceFile now refuses ambiguous single replacements.** A non-`replace_all` edit now
  errors when `old` matches more than once instead of silently editing the first match. Add
  surrounding context to make the old string unique, or pass `replace_all=true` when every
  occurrence should change.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.27.0`, or use the native installer for your OS (see the README install table).

## 0.26.0 (2026-05-30)

### What changed in this release

- **Install and update no longer 404 on a freshly published release.** The 0.24.0 "atomic latest" gate turned out to be dead code — it ran only on a `release: published` event that a token-created release never fires, and did not affect `/releases/latest` anyway. The GitHub Release is now created as a **prerelease**, and a new `promote-release.yml` runs on the tag push, waits for every platform asset to finish uploading, then clears the prerelease flag and marks the release latest — the single point at which a version becomes resolvable by installers and the in-app updater. As defense-in-depth, the curl and PowerShell installers now resolve the newest release that actually carries their platform asset (skipping drafts and prereleases) and wait for the archive plus checksum before downloading, so `irm | iex` / `curl | bash` run during the publish window no longer fail on a missing `PythinkerSetup-<ver>.exe` or archive.
- **OpenCode Go model catalog refreshes on every startup without a re-login.** Bundled catalog changes — new models, corrected provider shapes — previously reached an existing install only after a manual `pythinker login --opencode-go`. OpenCode Go is now wired into the every-startup `refresh_managed_models` task with its own discovery and a dedicated apply that upserts and prunes across both its OpenAI- and Anthropic-shaped providers while preserving your `default_model` and `default_thinking`. Discovery failures are isolated so they cannot abort other providers' saves; provider `base_url` repairs still require a re-login.
- **Homebrew install shows the logo and fails fast on a missing tap token.** `brew install` now prints the robot-head banner via a formula `caveats` block — the banner previously lived only in the curl and PowerShell installers, which Homebrew never runs. The tap auto-update workflow now detects an empty `HOMEBREW_TAP_TOKEN` (lost in the org migration, which had frozen the tap at 0.23.0) and fails with an actionable error instead of an opaque git exit-128.
- **Markdown and report rendering hardened against real model output.** Code-span pipes inside Markdown tables are now protected so a `|` inside backticks no longer fractures the table, and a `report` block nested inside an outer documentation fence is no longer wrongly promoted to a report — report fences are extracted via a markdown-it AST walk instead of a flat regex. Backed by a new TUI markdown/report contract test suite grounded in a real security-scan fixture.
- **Steadier agent editing and a restored update prompt.** File-replace edit handling is hardened, subagent prompt persistence and the agent's working language are preserved across turns, and the todo list stays aligned during a turn. The blocking pre-start update prompt — wired in 0.24.0 but again left unwired by a later refactor — is restored so it runs before every interactive session.
- **CI runs required checks on every pull request.** The `check`, `test`, and `release-validate` contexts were path-filtered off docs-only (and `sdks/`/`examples/`-only) PRs, so the required statuses never reported and those PRs stayed BLOCKED under branch protection with no clean override. The `pull_request` path filter is dropped so every PR runs each required context exactly once; the `push` trigger keeps its filter unchanged.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.26.0`, or use the native installer for your OS (see the README install table).

## 0.25.0 (2026-05-29)

### What changed in this release

- **`Fetch` now re-checks every redirect hop against the SSRF guard.** Redirects were followed without re-validating the destination, so a public URL could redirect to a link-local address (e.g. a cloud metadata endpoint) and slip past the guard that only inspected the original URL. Redirects are now followed manually and every hop is re-validated, closing the public→link-local bypass.
- **Web domain allowlist for `Fetch` and `Search`.** A new `web.allowed_domains` config option restricts which hosts the web tools may reach. When set, `Fetch` (including every redirect hop) and `Search` reject any host outside the list; leave it unset to keep web access unrestricted.
- **Crash-consistent background tasks.** Task and agent-task state is now serialised under a cross-process per-task lock, so a worker heartbeat landing mid-update is no longer lost. Every terminal agent-task update routes through a single finalizer that writes the authoritative runtime first, and recovery reconciles records left divergent by a crash or kill without ever clobbering a live agent. Bash task output is capped (default 50 MiB) so a chatty task cannot exhaust disk, terminated processes get a SIGTERM→SIGKILL fallback, and aged terminal task directories are pruned (default 7 days).
- **Calmer, more reliable TUI.** The todo list no longer renders twice during an in-flight turn, OAuth and feedback links open through a detached browser launcher so browser output cannot corrupt the terminal or steal key presses, and the terminal is restored to a sane state on `SIGTERM`/`SIGQUIT` and at exit.
- **Live tool-execution feedback.** Tool calls now show a calm "preparing" row during approval and hooks, switch to a live status once execution starts, and stream shell `stdout`/`stderr` as a running tail before the final result lands. The composing assistant block renders a live Markdown preview as the model writes, code blocks gain clearer framing, and the active spinner uses smoother braille dots.
- **Steadier agent loop.** The model is nudged once when a turn ends on a bare statement of intent with no tool call, steered away from blocking on a single background task while siblings are still running, and a `SetTodoList` call whose todos arrive as a JSON-encoded string is now parsed transparently instead of failing validation.
- **Unified report rendering.** Code review, verify, and security-review output now share one standardized, muted report renderer — including `report` blocks emitted by skills and agents; a malformed block falls back to ordinary markdown rather than being swallowed.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.25.0`, or use the native installer for your OS (see the README install table).

## 0.24.0 (2026-05-28)

### What changed in this release

- **Update prompt is now wired and highlighted.** The blocking 4-choice update menu (Update now / Skip / Dismiss / Exit) was defined but never invoked at shell startup — users only ever saw the passive bottom-bar toast. It now runs before the auto-update path in every interactive session. The persistent status-line update notice also renders in bold bright-yellow so it is harder to miss.
- **Complete native installer `Fetch` fix.** The 0.23.0 release bundled trafilatura's data files but missed `justext`'s stoplists directory, so the `Fetch` tool still crashed with `FileNotFoundError: ./_MEIxxxx/justext/stoplists` on `.exe`, `.deb`, and `.rpm` installs. All three installer specs now bundle both `trafilatura` and `justext` data files. PyPI / `pip install` was unaffected.
- **Atomic "latest" release gating.** The GitHub Release is no longer marked "latest" until every platform asset (4 archives, 1 `.exe`, 4 `.deb`/`.rpm`) is attached. A dispatch workflow polls for completeness before flipping the flag, so `/releases/latest` and the in-app updater no longer serve a partially-built release during the publish window.
- **Smarter `/update` command.** `run_update_prompt` now routes through `do_update(check_only=True)` to get a fresh PyPI version before showing the update modal, and verifies that the expected binary asset for your platform exists on the GitHub Release before initiating a native upgrade.
- **Repository transferred to Pythoughts-labs.** All GitHub URLs, install script references, and CI configuration now point to `github.com/Pythoughts-labs/pythinker-code`.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.24.0`, or use the native installer for your OS (see the README install table).

## 0.23.0 (2026-05-28)

### What changed in this release

- **Fetch tool works again in native installers.** The PyInstaller-built `pythinker` binaries (Homebrew, `.deb`, `.rpm`, `PythinkerSetup-*.exe`) shipped without `trafilatura/settings.cfg`, so the first `Fetch` call against any non-empty page crashed with `No option 'min_extracted_size' in section: 'DEFAULT'` as trafilatura tried to read an empty `ConfigParser`. The PyInstaller datas tuple now collects trafilatura's data files, so the bundled binary's `Fetch` tool extracts page content as expected. PyPI / `pip` installs were unaffected.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.23.0`, or use the native installer for your OS (see the README install table).

## 0.22.0 (2026-05-28)

### What changed in this release

- **Reliable update banner.** The auto-update check no longer skips when prompt_toolkit wraps stdout (the incorrect `isatty()` guard is gone), and the 24-hour throttle is now armed only after a successful round-trip — transient first-launch failures no longer silence the banner for a day. The blocking pre-start update prompt is removed; the bottom-bar toast is the sole update UI.
- **Lighter GitHub releases polling.** Update checks send `If-None-Match` with the cached ETag and serve `304 Not Modified` from disk, so shared-NAT users no longer burn unauthenticated rate limit on every launch.
- **Robust Windows upgrade flow.** The detached upgrade helper is launched as a single base64 `-EncodedCommand` PowerShell call, eliminating quote leakage through `cmd.exe`/`CommandLineToArgvW` that had been printing `Wait-Process …` as a literal string. The non-PowerShell installer fallback now sets `close_fds=True` so the running `pythinker.exe` handle is no longer inherited and locked against replacement.
- **Always-clean upgrade staging.** Linux and macOS native upgrades wrap the post-`mkdtemp` work in `try`/`finally` so the staging tmpdir is removed on every exit, including failures (Windows continues to delegate cleanup to the detached helper).

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.22.0`, or use the native installer for your OS (see the README install table).

## 0.21.0 (2026-05-28)

### What changed in this release

- **Non-blocking memory recall.** Recall I/O is now dispatched to a thread-pool executor, preventing the event loop from stalling during memory lookups. Sessions with large memory stores or slow disks will remain responsive throughout recall.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.21.0`, or use the native installer for your OS (see the README install table).

## 0.20.0 (2026-05-28)

### What changed in this release

- **Ranked recall injection and Scratchpad working memory.** The memory subsystem gains a dependency-free lexical retriever, ranked recall injection replacing the previous verbatim memory dump, and a new root-only `Scratchpad` tool that lets the agent record structured notes across tool calls during a session.
- **Full memory lifecycle: Phases B–D.** A unified injection bus re-arms recall on every Memory or Scratchpad write (Phase B), session-end episodic recaps are harvested before compaction into a per-project journal (Phase C, off by default), and an approval-gated inbox consolidation flow (`/memory inbox`) proposes—but never auto-applies—memory merges (Phase D).
- **Context-aware and web-fresh agent subagents.** Code-reviewer, security-reviewer, coder, and plan specialists now mandate a context7-first / web-fallback freshness check before scoring third-party findings or writing against a library. The system prompt gains a Granular Todo discipline (one in-progress sub-todo per dispatched subagent) and an Engineering Discipline section.
- **Memory robustness hardening.** Compaction harvest failures are now isolated per-phase (a broken prepare step no longer silently cancels recall), inbox JSON-parse errors log and skip instead of dropping silently, and the recall injection bus uses a knapsack budget that continues filling with lower-priority candidates after a high-priority slot overflows.
- **Animated robot logo in all native installers.** The curl-bash and PowerShell native installers now display a Tetris-style animated robot-head logo on supported terminals, with a static fallback for CI, `NO_COLOR`, dumb-term, or `PYTHINKER_NO_ANIMATION=1`.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.20.0`, or use the native installer for your OS (see the README install table).

## 0.19.0 (2026-05-27)

### What changed in this release

- **Central per-project agent memory.** Pythinker now keeps a durable per-project memory (`MEMORY.md` / `USER.md`) under `~/.pythinker/projects/<key>/memory/`, written through a new root-only `Memory` tool with content guards and secret-shape detection, recalled into the root agent's first wakeup prompt within a bounded budget, and inspectable with the new `/memory` command.
- **Non-blocking update flow.** The blocking pre-start update prompt is replaced by a cached, no-network startup notice plus a triggerable `/update` command, and the native Windows installer now waits on the launching process before swapping files and cleans up its staged installer.
- **Fully native Homebrew formula.** Brew installs are generated from the same GitHub Release tarballs as the curl installer (including macOS Intel native assets), so they no longer depend on PyPI virtualenv resources.
- **Release pipeline hardening.** TestPyPI publishing is now non-blocking and publish steps carry timeouts, so a transient staging flake no longer fails a release.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.19.0`, or use the native installer for your OS (see the README install table).

## 0.18.0 (2026-05-27)

### What changed in this release

- **Live subagent activity streaming.** Subagent tool calls now stream live into the transcript, with safe pending headers for in-flight tool calls, new transcript progress events, and a unified shimmer animation across active-work labels so long-running exploration stays legible.
- **Smarter delegation and orchestration.** A Context-First Orchestration Protocol guides the default agent, specialist subagents receive prompt packets for single-objective delegation plus evidence and verification gates, and overflow RunAgents children are deferred instead of hard-failing.
- **Calmer, more resilient TUI.** In-flight and singular Ask payloads no longer flash an invalid badge, MCP startup status is cleaner, and shell rendering and MCP guidance are refined.
- **Sturdier configuration handling.** Incompatible legacy JSON config is now preserved instead of being silently reset to defaults.
- **Security and shell hardening.** The security scan and shell execution paths were hardened against unexpected input.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.18.0`, or use the native installer for your OS (see the README install table).

## 0.17.0 (2026-05-25)

### What changed in this release

- **Sharper compaction continuity.** PreCompact now carries custom instructions, restores skill and hook context after compaction, triggers SessionStart after restore, and preserves the `Conversation compacted.` handoff so long sessions resume cleanly.
- **Better subagent orchestration.** Subagent specs merge inherited subagent maps, foreground and background launches preserve parent-agent IDs for spawn-tree tracking, RunAgents fingerprints include agent names, and markdown agent discovery warns on unknown models instead of silently falling back.
- **Polished terminal workflow.** The shell adopts the robot-brand palette, compact transcript/agent/file-mention menus, pinned live todo activity, calmer tool output, safer auto-backgrounding for long shell commands, and updated render snapshots.
- **Release and installer hardening.** Interactive sessions show a blocking pre-start update prompt, update exits wait for acknowledgement, Homebrew publish retries package installs, and native installers gain a friendlier animated path with Windows User PATH automation.
- **Provider compatibility refresh.** Anthropic SDK support is updated for 0.101 tool-result block types so direct Anthropic sessions continue to stream tool output correctly.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.17.0`, or use the native installer for your OS (see the README install table).

## 0.16.0 (2026-05-24)

### What changed in this release

- **Standardized native install docs across platforms.** README Quick Start now presents one canonical Windows command (`irm https://pythinker.com/install.ps1 | iex`) and one canonical macOS/Linux command (`curl -fsSL https://pythinker.com/install.sh | bash`) before package-manager/manual alternatives.
- **Removed old local installer guidance.** User-facing docs no longer advertise legacy local shell wrappers or Python-tool manager shortcuts. `pip install pythinker-code==0.16.0` remains as the universal Python fallback and release-gate snippet.
- **Aligned release artifact instructions.** Manual Windows, Linux package, and tarball sections all point at `0.16.0` GitHub Release assets and keep SHA-256 verification explicit.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.16.0`, or use the native installer for your OS (see the README install table).

## 0.15.0 (2026-05-24)

### What changed in this release

- **Fixed `pythinker update` for curl-bash native installs.** Frozen onefile installs in `~/.local/bin/pythinker` are now detected as native even when older tarballs do not include the `.pythinker-native` sentinel, avoiding the broken `pythinker -m pip install --upgrade pythinker-code` path.
- **Added Unix native archive updating.** Linux and Apple Silicon macOS native builds now download the matching GitHub Release tarball, verify its `.sha256`, extract `pythinker`, and replace the current executable in place.
- **Improved native update guidance.** The update banner now shows the canonical fixed-version curl installer on Unix and keeps the Windows installer guidance for Windows native builds.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.15.0`, or use the native installer for your OS (see the README install table).

## 0.14.0 (2026-05-24)

### What changed in this release

- **Install counter and README badge.** `https://pythinker.com/install.sh` and `https://pythinker.com/install.ps1` now route through a Cloudflare Worker-backed counter that records successful installer fetches and exposes both JSON and Shields-compatible badge endpoints. The README now shows the live install badge alongside PyPI downloads.
- **Canonical installer endpoint polish.** The hosted shell endpoint is the documented curl-bash path, the Windows PowerShell endpoint is documented as the native bootstrap, and pinned install examples now target `0.14.0` artifacts.
- **TUI activity and readability refinements.** Tool/agent headers use calmer grey styling, agent task names resolve at call time, live spinner rows stay pinned while status output clips, oversized output is capped, markdown rendering is cleaner, and shell activity indicators are more stable.
- **Release and CI hardening.** Plugin downloads are stricter, pythinker-home sync dispatch now skips when its optional repository-dispatch secret is absent instead of failing the main branch, and release documentation was refreshed for the native installer flow.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.14.0`, or use the native installer for your OS (see the README install table).

## 0.13.0 (2026-05-22)

### What changed in this release

- **Native installers for macOS and Linux.** `brew install Pythoughts-labs/pythinker/pythinker-code` (Homebrew tap) covers both macOS (Intel + Apple Silicon) and Linux brew installs from a single auto-generated formula. Debian/Ubuntu users get `pythinker-code_x.y.z_<arch>.deb` and Fedora/RHEL/openSUSE users get `pythinker-code-x.y.z.<arch>.rpm`, both attached to every GitHub Release for `x86_64` and `aarch64`. Together with the Windows `PythinkerSetup-x.y.z.exe` shipped in 0.12.0, Pythinker now ships native installers for every supported platform — no Python, Node, or `uv` prerequisite.
- **Cross-OS curl-bash native installer.** `curl -fsSL https://raw.githubusercontent.com/Pythoughts-labs/pythinker-code/main/scripts/install-native.sh | bash` detects your OS + arch, downloads the matching PyInstaller-frozen tarball from the latest Release, verifies its SHA-256, and lands the binary at `~/.local/bin/pythinker`. Supports `linux-x86_64`, `linux-aarch64`, and `macos-arm64`. Honors `--version`, `--prefix`, and `NO_COLOR`.
- **Homebrew tap auto-published on every release.** A new `.github/workflows/homebrew-tap.yml` waits for the PyPI publish to land, runs an in-tree formula generator (replaces the unmaintained `homebrew-pypi-poet` — see release notes for the why), and pushes `Formula/pythinker-code.rb` to the `homebrew-pythinker` tap repo. 132 transitive deps are enumerated automatically — no hand-curation per release.
- **Tag-triggered Linux package pipeline.** A new `.github/workflows/linux-installer.yml` matrix-builds `.deb` and `.rpm` for `x86_64` and `aarch64` (the latter via QEMU on `ubuntu-latest`), then uploads all six artifacts to the GitHub Release via `softprops/action-gh-release@v2`.
- **Frozen-binary data-files fix.** The PyInstaller specs for both the Windows and Linux pipelines now call `collect_data_files(pkg, include_py_files=False)` per package, so `pythinker_code/prompts/*.md`, `agents/default/*.yaml`, `tools/*/description.md`, `skills/*/SKILL.md`, and similar package resources are bundled into `_internal/`. Without this fix the frozen binary crashed the first time it tried to load `init.md` or an agent yaml. The Windows installer that shipped in 0.12.0 is affected; users on that build should upgrade to 0.13.0.
- **Legacy install paths deprecated.** `scripts/install.sh`, `scripts/install.ps1`, `uvx pythinker-code`, `uv tool install pythinker-code`, `pipx install pythinker-code`, and bare `pip install pythinker-code` continue to work for existing automation. The two helper scripts now print a `[DEPRECATED]` banner at startup, pause 3 s, and point at the OS-specific native installer; set `PYTHINKER_INSTALL_QUIET_DEPRECATION=1` to suppress the banner. README Quick Start now leads with the per-OS install table.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.13.0`, or use the native installer for your OS (see the README install table).

## 0.12.0 (2026-05-22)

### What changed in this release

- **Native Windows installer.** A signed `PythinkerSetup-x.y.z.exe` is now attached to every GitHub Release — install Pythinker on Windows with one download, no Python / Node / uv prerequisite. The wizard installs per-user (no UAC) into `%LOCALAPPDATA%\Programs\Pythinker`, registers `pythinker` on the user PATH, and broadcasts `WM_SETTINGCHANGE` so new shells pick the change up immediately. Uninstall reverses the PATH edit. Code-signing is wired through `signtool` and ships unsigned until the Authenticode cert lands; from that point forward the same CI job produces signed installers with no code change required.
- **In-app updates for the native build.** `pythinker update` from a native install detects the build (via a `.pythinker-native` sentinel next to `pythinker.exe`), fetches the latest GitHub Release asset, verifies its SHA-256, and re-runs the installer silently (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`). The `PYTHINKER_CLI_NO_AUTO_UPDATE` opt-out env var that the PyPI path already honors now also gates the native auto-update path — one knob, both flows. The update banner shows a human-readable `PythinkerSetup-x.y.z.exe` line instead of leaking internal markers.
- **Tag-triggered Windows build pipeline.** A new `.github/workflows/windows-installer.yml` runs on every `pythinker-code-v*` tag, freezes `pythinker` via PyInstaller (`--onedir` for faster startup and fewer AV false positives), compiles the Inno Setup script, signs the result if `WINDOWS_CERT_PFX_BASE64` / `WINDOWS_CERT_PASSWORD` secrets are populated, and uploads the `.exe` plus its `.sha256` to the corresponding Release.
- **Shell terminal rhythm refinements.** Tone tokens, motion timing, and theme palette were retuned (sky-blue `#7dd3fc` / `#93c5fd` accents) so transcript rows, motion status, and dialog surfaces breathe consistently. UI snapshot tests updated to lock the new rhythm in place.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.12.0`, or — on Windows — download `PythinkerSetup-0.12.0.exe` from the Releases page.

## 0.11.0 (2026-05-22)

### What changed in this release

- **Fixed PyPI install conflict (was failing on Windows and every other platform).** `pip install pythinker-code==0.10.0` failed with `fastmcp 3.2.0 depends on mcp<2.0 and >=1.24.0` vs `pythinker-core 1.1.0 depends on mcp<1.17 and >=1`. 0.11.0 pins the republished `pythinker-core 1.1.1`, whose widened `mcp>=1.23,<2` constraint lets the resolver pick a single `mcp` version compatible with `fastmcp==3.2.0`.
- **Blackbox-style TUI port — phase 1.** Shell design primitives, compact transcript activity rows, blackbox-style motion status, standardized shell dialogs, aligned footer status styling, and a restyled tool-result surface land together. The TUI now shares a coherent visual language across rows, dialogs, and motion.
- **Refreshed TUI accent palette.** Dark/light theme accent retuned to a cleaner sky-blue (`#7dd3fc` dark, `#0284c7` light) for better contrast against the new tool-result surfaces.
- **Markdown + report polish.** Report spacing and markdown code blocks render with improved breathing room and consistent fences.
- **Rotating thinking-word indicator restored** with a leading space before the live stream status so the spinner no longer abuts surrounding text.
- **Internal audit + smoke evaluation.** A blackbox TUI scope map, prompt/agent audit, and a recorded visual smoke evaluation join the repo to govern future TUI work.

Upgrade with `pythinker update` or `pip install --upgrade pythinker-code==0.11.0`.

## 0.10.0 (2026-05-22)

### What changed in this release

- **Tool failure recovery improvements.** The agent loop now handles malformed or empty tool-call responses more gracefully and can continue the session instead of leaving the UI stuck after a bad provider turn.
- **Safer file edits.** File write and replace tools now create restore points before mutating files, giving sessions a clearer recovery path after risky changes.
- **Session UX state tracking.** Runtime session state now records additional UX metadata so shell surfaces can provide better continuity across long-running work.
- **Shell command enhancements.** New shell slash-command plumbing improves discoverability and keeps interactive workflows smoother.
- **TUI renderer polish.** Tool cards now share more consistent status glyphs, truncation behavior, and result summaries across bash, read, write, edit, grep, find, web, subagent, background, ask-user, and think renderers.
- **Clipboard handling hardening.** Clipboard helpers now degrade more cleanly when platform clipboard access is unavailable.
- **Release and TUI specs.** The repository now includes the blackbox TUI port design and a visual smoke-test criterion for future terminal UI work.

Upgrade with `pythinker update` or `pip install --upgrade pythinker-code==0.10.0`.

## 0.9.0 (2026-05-21)

### What changed in this release

- **Cleaner TUI — tool card backgrounds removed.** The grey pending/running
  background overlay that appeared behind every tool execution card (subagents,
  bash executions, reads, etc.) has been removed. Only user-message blocks
  retain a background tint, keeping the visual hierarchy focused on your input.
- **Welcome screen enhancements.** The startup info panel now shows the current
  git branch (when inside a git repo) and the session auto-save path alongside
  the working directory and session ID. Branch name is highlighted in magenta
  for quick scanning.
- **Bash header strip styling.** The `$ command` portion of bash execution
  headers now picks up the `tool_pending_bg` token for the strip background,
  matching the reference renderer style and providing consistent visual weight
  across themes.
- **Pythinker markdown renderer wired into message components.** User messages,
  assistant messages, and custom messages now render through `pythinker_markdown`
  (the project's own Markdown renderer) instead of raw `rich.markdown.Markdown`,
  giving consistent heading, code-block, and table styling everywhere.
- **Expanded theme palette.** `theme.py` gains a full `MarkdownColors` /
  `markdown_rich_style` subsystem with dark and light palettes covering headings,
  emphasis, inline code, links, blockquotes, table borders, code-block borders
  and backgrounds, and spinner states (active/done/failed).
- **Improved tool fallback renderers.** The call fallback now emits a
  status-glyph header (`✔`/`✘`/`●`) instead of a bare label. The result
  fallback now truncates long outputs at 60 lines / 4000 chars with an
  italicised note (matching the card renderer's behaviour), and applies the
  correct theme tokens for error vs. muted output.

Upgrade with `pythinker update` or `pip install --upgrade pythinker-code==0.9.0`.

## 0.8.0 (2026-05-21)

Version-scheme reset. `pythinker-code` now ships as `0.8.0` under the new
`0.MINOR.PATCH` line.

### What changed in this release

- **Version line reset.** `pyproject.toml` `version` is `0.8.0` under the new release design.
  All prior `pythinker-code` 1.x/2.x releases have been yanked from PyPI and
  removed from the GitHub Releases page. New installs of
  `pip install --upgrade pythinker-code==0.8.0` resolve to the `0.x` line.
- **Tag scheme standardised** on `v<MAJOR>.<MINOR>.<PATCH>`. The
  `release-pythinker-cli.yml` workflow trigger now matches `v[0-9]+.[0-9]+.[0-9]+`
  and `scripts/check_version_tag.py` strips the leading `v` before comparing the
  tag to `pyproject.toml`.
- **Release gate preserved.** The `What's New in <version>` section,
  `pythinker-code==<version>` install snippet, and `## <version> (YYYY-MM-DD)`
  CHANGELOG entry are still required for every tag — only the version values
  change.
- **CHANGELOG restart.** Pre-`0.8.0` history archived to
  `docs/history/CHANGELOG-pre-0.8.0.md`; this file starts fresh at `0.8.0`.
- **README "What's New" trimmed.** The cascading 2.x "What's New" wall is
  replaced by a single `0.8.0` section. Past release notes live in the archived
  CHANGELOG and the per-tag GitHub Releases (from `v0.8.0` onward).
- **Test refactor.** `tests/telemetry/test_otel_resource.py` now reads the
  expected service version from `importlib.metadata.version("pythinker-code")`
  instead of a hard-coded string, so future version bumps don't require a test
  edit.

### Included in 0.8.0

All functionality included in `pythinker-code` 0.8.0 is preserved:
review-first workflows (`pythinker review`, `pythinker secscan`,
`pythinker security-scan`, `pythinker debug`), Reviewflow stateful
review/fix workflows, the new `code-reviewer` / `security-reviewer` /
`debugger` subagent roles, hardened review-output validation, and the
read-only PR artifact helpers (`describe`, `improve` / `suggest`, `ask`,
`labels`, `changelog`, `docs`, `compliance`, etc.).

See [`docs/history/CHANGELOG-pre-0.8.0.md`](docs/history/CHANGELOG-pre-0.8.0.md)
for the archived pre-reset release-by-release notes.

Upgrade with `pythinker update` or `pip install --upgrade pythinker-code==0.8.0`.
