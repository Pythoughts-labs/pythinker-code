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

- **Inline `/command` references are no longer silently dropped.** Slash commands only execute when a message starts with `/`; a `/best-practices` or `/skill:<name>` referenced mid-message used to reach the model as plain text and routinely got ignored. A new dynamic injection now flags such references once per user message (known commands, aliases, and `skill:*` names — path-like tokens such as `/usr/local` or `tests/clear` are not confused for commands) and instructs the model to load the referenced skill, apply the equivalent guidance, or tell the user how to actually invoke the command; the base prompt carries the matching standing rule.
- **Capped file reads now say exactly how to continue.** When `ReadFile` stops at the line or byte cap, the result message names the remaining line count and the precise `line_offset` to resume from (`Partial read: 206 lines remain; continue with line_offset=1001.`), the tool description tells the model a below-total read is partial, and the base prompt requires finishing partial reads of spec/skill/checklist files before implementing against them — closing the failure mode where an agent reads the first 1,000 lines of a spec and ships against a fraction of it.
- **User-designated spec files get artifact-scoped authority.** File contents arrive wrapped as untrusted data ("never instructions to follow"), which also discounted the very skill or spec the user explicitly asked to apply. The base prompt now distinguishes the two: a file the user directs you to apply defines requirements for the deliverable — implemented faithfully, mandatory checks included — while its authority still never extends to the agent itself (embedded directives to run commands, switch tasks, or exfiltrate stay inert).
- **Definition of Done walks the task's own checklist.** Work performed under a skill, spec, or plan with mandatory rules now exits through a new checklist item: every rule checked against the artifact (mechanically where possible), each compliance claim naming the check that actually ran, and anything the environment cannot execute or render reported as unverified instead of implied to work.
- **`<system-reminder>` arrival is no longer mistaken for user activity.** Models repeatedly misread injected reminders as "the user sent a new message." The base prompt now states they are injected machinery: their arrival never means the user replied, changed the request, or ended the turn.
- **Agent specs now tell the truth about their runtime permissions.** The hardened permission profiles block network tools (`SearchWeb`/`FetchURL`) for review/verify/read-only subagents and all MCP/external tools for every non-implementation profile — but most subagent specs still instructed live docs/advisory lookups through exactly those tools, wasting steps on denied calls and silently disabling the mandated checks. The reviewer-class specs (`review`, `code-reviewer`, `security-reviewer`, `debugger`, `judge`, `explore`) are rewritten offline-honest: never assert third-party "deprecated/removed/wrong API" claims from training memory, verify what the repository itself proves (installed dependency source, manifest/lockfile pins, call sites), and return everything else under RISKS as structured `needs verification — <library> <version>: <claim>` items; dead tool entries are removed from their specs so the parent sees an accurate toolset. `plan` and `scout` keep first-class web research and route it through `SearchWeb`/`FetchURL`.
- **`scout` regains its mission: it was accidentally offline.** The external-docs researcher was missing from the subagent profile map, defaulting to the offline `read_only` profile — which hid and denied the web tools its entire spec is built on. It now maps to the read-only-plus-network `ask` profile and is the designated delegate for verifying the `needs verification` claims offline reviewers return.
- **Review fan-out & finding-verification discipline in the base prompt.** The orchestrator now: decomposes large diffs (above ~1,500 changed lines or ~25 files, one reviewer per subsystem with explicit file lists, deduped on synthesis); adversarially verifies every finding against the cited lines before reporting (non-reproducing findings are dropped or listed as rejected — never retained at a laundered lower severity); re-anchors exact `path:line` references and re-derives severity counts itself instead of transcribing child tallies; and resolves reviewers' needs-verification third-party claims — and only those — against live docs, directly or via `scout`, with query hygiene enforced at the layer that actually has network access.
- **Workspace-jail shell denials now name the jail.** The escape denial tells the agent the actual workspace root it must stay within, so a blocked reviewer corrects the path instead of retrying blind variations; reviewer specs also gain explicit command-timeout discipline (narrow scope on timeout, never re-run bigger).
- **Workspace jail closes the expansion/glob/cwd bypass family.** Read-style commands under restricted profiles can no longer smuggle paths past the boundary check: path arguments containing unexpanded `$` variables are rejected outright (shlex strips quotes, so a runtime expansion is indistinguishable from a quoted literal — regex and program arguments are unaffected because pattern extractors never treat them as paths); glob arguments are validated by their literal prefix instead of being skipped (`rg x /etc/*` and `ls ../*` are denied, `rg x src/**/*.py` stays allowed, and glob-then-`..` traversal like `src/*/../..` is rejected); and `cd`/`pushd` moves are tracked across command segments so `cd .. && rg x .` is judged against the directory the shell will actually be in (`popd`, `cd -`, bare `cd`, and `(`/`{` command grouping are rejected as untrackable). ReadFile parity for absolute file reads is preserved (`cat /etc/hosts` and `cat /etc/*` stay legal).
- **Statusline execution knobs are user-scope-only.** A repo-controlled project config could flip `tui.statusline.enabled` plus `segments=["command"]` to trigger the user's pre-configured external status command and observe its output. `enabled`, `segments`, and `command_timeout_ms` now join `command` in the scope locks (cosmetic fields like `style`/`bar_width` stay project-configurable), and `command_timeout_ms` gains a 60s upper bound so a runaway value cannot park a subprocess for days.
- **Secret env scrub covers more credential shapes.** Bare `PRIVATE_KEY`/`JWT`/`COOKIE`/`BEARER` and the `_JWT`/`_COOKIE`/`_BEARER` suffixes are now scrubbed from restricted-profile subprocess environments; cookie-adjacent non-credentials (`COOKIE_JAR_PATH`) survive.
- **Restricted-profile retry cap is whitespace-insensitive.** The two-failures hard stop now keys on the whitespace-normalized command string, so trailing-space padding can no longer mint a fresh counter and bypass the cap; semantically different commands stay distinct.
- **TaskOutput steers to notification-driven waiting.** A timed-out blocking wait now leads with "return control and rely on the completion notification" (retrying with a longer timeout is the explicit exception); consecutive blocking timeouts escalate to a firm STOP-waiting hint with a per-task streak; and a timed-out blocking attempt no longer resets the non-blocking "STOP polling" escalation — interleaving one blocking call between polls used to absolve the streak indefinitely.
- **Review-scope measurement and judge-gate reinforcement in the base prompt.** Review fan-out scope is measured against the merge base (committed plus worktree changes), not the uncommitted-only diff stat that made a ~140-file branch review look like 17 files; the dual-destination rule now names severity-scored findings reports as judge-gate triggers and forbids silently re-grading a child reviewer's severities during synthesis.
- **No more transient red `<invalid>` flash while tool calls stream.** While a tool call's arguments stream in, the partial-JSON repair turns a key-without-value into `null`, and card renderers (shell, agent, edit, write, ...) treated "key present, non-string value" as invalid for a frame or two. While args are incomplete, `None`-valued keys are now dropped before rendering so every card shows its pending state; finished calls with genuinely invalid args still show `<invalid>`.
- **Flicker-free streaming on terminals with synchronized output.** Every redraw frame — renderer updates and scrollback prints alike — is now bracketed in DEC mode 2026 synchronized-update marks so supporting terminals paint atomically instead of mid-frame. Capability-gated (off for `TERM=dumb`; kill switch `PYTHINKER_NO_SYNC_OUTPUT=1`) and harmlessly ignored by terminals without support.
- **Parallel subagents get distinctive instance codenames.** Children launched via `RunAgents` whose name merely echoes their type (the common `code-reviewer:code-reviewer` degenerate case), or that duplicate a sibling's name, are now assigned a generated `adjective-noun` codename (`amber-falcon`, `tidal-wren`, ...) unique within the batch. The codename flows through the result tree, TaskList, TaskOutput, and completion notifications (as `codename (type)` when the caller gave no title), so simultaneous same-type agents are finally distinguishable; caller-chosen distinct names and titles pass through untouched.
- **Background agent task ids are codenames too.** A background agent task was previously handled by an opaque random id (`agent-kzsr0h9a`) — the one token that stays visible in `TaskOutput`/`TaskStop` headers, the task list, and notifications, which made single background launches indistinguishable at a glance even after the codename work. Generated agent task ids now use the same codename vocabulary (`agent-tidal-wren`), unique against every id already in the session's task store; bash task ids keep the opaque random suffix.
- **Slash commands ghost-complete inline; Tab accepts.** Typing a root `/comm…` token now renders the remainder of the best-matching command as dim ghost text after the cursor (mode-aware, same command set as the completion menu); Tab — or the standard right-arrow/ctrl-e suggestion keys — completes it in place without submitting. The existing completion menu, Enter-to-run, and Escape-to-discard behaviors are unchanged.
- **Workspace jail for read-style shell commands in restricted profiles.** Read-only/plan/review/verify permission profiles now apply the same boundary the first-class file tools enforce to raw shell path arguments: discovery/search commands (`find <root>`, `rg`/`grep` paths, `ls`/`du`/`tree`, `git -C`/`--git-dir`/`--work-tree`, generic `--directory`/`--project`) are denied when a path argument resolves outside the workspace and approved additional directories (symlinks and `~` are resolved first), while file-read commands (`cat`/`head`/`tail`/`sed`/...) keep ReadFile parity — absolute paths outside the workspace stay readable, relative `..` escapes are denied. Closes the gap where `find .. -name AGENTS.md` from a review subagent passed every gate; foreground and background shell share the same decision path, and every denial is an explicit error naming the offending argument.
- **Review/read-only subagents are offline by default, enforced — not prompted.** `PermissionProfile` gains an explicit `allow_network` field: review/verify/read-only profiles deny the first-class network tools (`SearchWeb`/`FetchURL`) at execution time (in addition to hiding them from the model), and the existing invariant that a root `yolo` flag never broadens a subagent's hard profile is now locked by tests. Plan/ask modes keep network access for interactive research.
- **Secret env scrubbing for restricted-profile shell.** Shell subprocesses spawned under profiles without shell-mutation rights (review/verify/read-only/plan subagents) no longer inherit credential-looking environment variables (`*_API_KEY`, `*_TOKEN`, `*_SECRET*`, `*_PASSWORD`, `AWS_*`, `GOOGLE_APPLICATION_*`, ...). Those profiles already block network access; inherited secrets were pure downside. Applies to foreground and background shell (the background task spec persists only a boolean, never the environment).
- **Retry-loop hard stop for restricted profiles.** Under review/read-only profiles, a verbatim shell command that has already failed twice is denied outright with guidance to change approach or report the blocker, instead of letting an agent flag-thrash the same failing invocation across steps. Implementation profiles are unaffected (re-running a failing test command while iterating stays legal).
- **Review diff base fallback is now loud.** `pythinker review`/`secscan` recorded only the *chosen* base ref, hiding the silent `origin/main` → `main`/`master` fallback. `ResolvedDiff` and `RunMeta` now carry `requested_base_ref` and `fallback_reason`; JSON output includes both, the pretty renderer prints a fallback warning, and PR-artifact metadata exposes them — so every report states exactly which base was reviewed and whether it was the one asked for.
- **Subagent todo lists are normalized to a single `in_progress` item.** A subagent is one sequential worker: extra `in_progress` items are demoted to pending (first wins, order preserved) with a corrective note in the tool output. The root list keeps the parallel-batch allowance (one `in_progress` sub-todo per running child).
- **Tool-call rows in the TUI are monotonic.** A finished row ignores late/duplicated wire events: a replayed `ToolResult` can no longer flip a failed row to successful (retries are separate rows), and a stray `ToolExecutionStarted`/output chunk after completion no longer restyles or mutates a committed row.
- **Statusline v2: full visual redesign of the shell footer.** The footer now renders colored segments separated by `│`/`·`, with a smooth gradient context bar (`ctx 36k/200k ████▌░░░░░ 18%`, green→gold→orange→red by fill, blinking `⚠ CTX LOW` past 90%), a working spinner, live `in N out M t/s` token speed, session cost (`$1.84`, or `$spent/$budget` once `/statusline budget` is set), a thinking-effort badge, git `+added/-removed` diff counts, session elapsed time, and a clock. Segments are fail-closed — each renders only when its data source has real data for the active provider/model, so the same default config is correct on Anthropic, OpenAI-compatible, and local Ollama/MLX setups (no `$0.00`, no empty bars). Everything is tunable via `/statusline`: `segments <ids>` (bare `segments` now lists every available segment with its zone and on/off state), `style fancy|plain`, `bar-width <4-20>`, `budget <usd|none>`, plus the existing `on|off` and external `command`; all settings persist under `[tui.statusline]`. ASCII-only terminals degrade glyphs automatically, and narrow widths drop low-priority segments (speed, diff, cost, effort) instead of truncating the essentials. Disabling customization (`/statusline off`) reproduces the plain pre-v2 footer.
- **Foreground `RunAgents` batches now run children concurrently.** Previously only background batches parallelized; foreground children executed one at a time. Children now overlap (bounded by `background.max_running_tasks` so a large batch cannot fork-bomb the session), results keep request order, and a crashing child reports its own error entry instead of aborting its siblings.
- **`RunAgents` rolls up child RISKS/BLOCKERS.** Foreground batch results now end with `batch_risks:`/`batch_blockers:` blocks that deduplicate findings raised by multiple children and attribute each finding to its reporters, so the orchestrating agent sees cross-child issues without re-parsing every report body.
- **New `/statusline` command: customizable status line.** The footer under the prompt is now configurable: pick which segments show (`cwd`, `git`, `flags`, `context`, `tokens`, `model`) with `/statusline segments <id,...>`, toggle customization with `/statusline on|off`, and optionally surface your own info with `/statusline command <argv...>` — an external command whose first stdout line is rendered in the footer (refreshed on a cadence, run without a shell, killed on timeout, and failing closed so a broken command never breaks the footer). Settings persist under `[tui.statusline]`; defaults reproduce the previous footer exactly.
- **Shell error briefs now show the trailing output of a failed command.** When a `Shell`/`Terminal` command exits non-zero, times out, or is killed by a signal, the collapsed worklog card appended only `Failed with exit code: N`; you had to expand the result to see *why*. The brief now includes the last few non-empty output lines (e.g. the stderr message), rendered as plain text so shell metacharacters (backticks, `#`, `*`) and line breaks are preserved verbatim instead of being reflowed as Markdown.
- **Subagents no longer receive plan-mode workflow reminders.** Plan mode is a session-wide flag shared with subagents (so it persists across resume), but subagent toolsets usually exclude `EnterPlanMode`/`ExitPlanMode`. Injecting the plan-mode reminder into a subagent only invited hallucinated calls to tools it doesn't have; the reminder is now root-only.
- **Terminal no longer risks hanging in raw mode on exit.** The cursor-position probe left `stdin` in cbreak mode and could block in an uninterruptible `os.read()` if cancelled mid-probe (e.g. a race with prompt_toolkit's reader on shutdown). Reads are now non-blocking during the probe and `VMIN`/`VTIME` are restored to canonical defaults, so a hang or crash can't leave the terminal wedged.
- **New `/goal` command: goal-driven execution ported from Codex CLI.** `/goal <objective>` sets a persistent thread goal the agent pursues across turns until it is verifiably complete. The objective is stored in session state (survives restarts and context compaction), kicks off work immediately with a success-criteria derivation prompt, and is re-injected on later turns as a continuation reminder carrying Codex's fidelity rules (no scope-shrinking, no easier-to-test substitutes) and evidence-based completion audit — the agent may only claim completion after proving every requirement against current state, and the user confirms with `/goal clear`. Subcommands: `view`, `pause`, `resume`, `clear`. Objectives are injected as untrusted data (`<objective>` framing), never as higher-priority instructions.
- **New `/best-practices` command (alias `/bp`).** Injects opt-in engineering best-practice guidance distilled from the Codex CLI system prompts — code-change discipline, dirty-worktree safety (never revert changes you didn't make), specific-to-broad testing strategy, todo hygiene, progress-update cadence, debugging methodology, and final-answer style — into the session context without consuming a turn, and extends them with generalized sections on scoping and assumptions, subagent orchestration (scoped prompts, single blocking waits, verify findings against real code), security and secrets, and verification before done. `/best-practices <section>` injects a single section, and the working-spinner tips now advertise the command.
- **Best-practices guidance is now a default, not just an opt-in.** The default system prompt ships a condensed always-on best-practices profile — smallest-complete-change ownership, environment detection from artifacts, blast-radius mapping, never-invent-APIs with dependency-name verification, dirty-worktree and git safety, honest testing (no verification gaming, deterministic tests), debugging method, migration/concurrency conformance, secrets and boundary parameterization, idempotent operations with a three-failures escalation rule, and answer-shape guidance — inherited by the root agent and every subagent role. The full `/best-practices` profile is expanded to match, gaining five new sections (operating principles, context gathering, design and implementation, version control, agent operational discipline) and sharper rules throughout.
- **New `/learn` command: session lesson extraction.** Reviews the session for user corrections, non-obvious error resolutions, and hard-won conventions, distills each into a trigger rule ("when X, do Y"), and persists it via the Memory tool to per-project memory (consolidating near-duplicates instead of stacking them). `/learn <focus>` steers extraction; an empty result is explicitly valid. This makes the working-spinner tip about `/learn` real.
- **TaskOutput escalates its hint on repeated non-blocking polls.** Polling a still-running task without `block=true` more than once now returns a firm "non-blocking poll #N … STOP polling" hint instead of the gentle default, steering the agent toward one blocking wait or the completion notification. The counter resets after any blocking attempt or once the task reaches a terminal state.
- **SetTodoList nudges the single-`in_progress` discipline.** Todo lists with more than one `in_progress` item now get a corrective notice (ported from Codex's plan-tool contract, softened because parallel-subagent fan-out legitimately tracks one `in_progress` sub-todo per running child), and the system prompt gains matching status-discipline guidance: no single-step lists, no `pending`→`done` jumps, no batch-completing after the fact.
- **`UpdateGoal` tool + opt-in goal auto-continuation: the full "loop until verified".** The agent can now mark the active `/goal` `complete` (only after the evidence-based completion audit) or `blocked` (only after Codex's strict three-strike blocked audit) via the new root-only `UpdateGoal` tool, which stops goal reminders and continuations; `/goal resume` reactivates either state. With `goal.auto_continue = true` (new config table, default off, `max_continuations` 1–10 capped at 3 by default), each user message is followed by automatic continuation turns toward the active goal — carrying the Codex continuation prompt — until the goal is marked, a tool call is rejected, or the cap is reached, with a budget-style wrap-up instruction on the final continuation.
- **Approval-mode-aware validation guidance.** Auto/yolo-mode injections now tell the agent to proactively run tests and lint before finishing (no user present to confirm), while the back-to-interactive reminder defers slow test/lint commands to user confirmation except for test-related tasks — ported from the Codex CLI validation philosophy.
- **`compact_prompt` config override.** A new optional top-level config key replaces the built-in compaction summarization prompt for both manual and automatic compaction; a `/compact` focus argument is still appended on top, and leaving it unset preserves current behavior.
- **Progress-update cadence in the system prompt.** Ported the Codex User Updates spec: short Progress notes on meaningful insights, a goal/constraints/next-steps statement before the first tool call of substantial work, heads-down announcements, and explicit plan-change callouts.
- **Reviewer subagents adopt Codex's review rubric.** The `review` and `code-reviewer` specs gain an explicit finding bar (only discrete, actionable issues the author would fix; rigor matched to the codebase; provable ripple effects; prefer zero findings over speculation), comment-construction rules (severity honesty, trigger conditions, one matter-of-fact paragraph), and an overall-correctness verdict (`patch is correct`/`patch is incorrect`) in the review summary.

## 0.40.1 (2026-06-10)

- **Windows/Linux native installers: web UI no longer 404s on `/`.** The installer CI froze the app without building the gitignored web/vis frontend bundles, so `pythinker web` opened a browser onto `GET /?token=… → 404 Not Found`. Both installer workflows now build the bundles before PyInstaller (matching the PyPI release flow — pip/wheel installs were never affected), every PyInstaller spec refuses to freeze when the bundles are missing, and a build that still lacks them serves an explanatory page on `/` (with the REST API still reachable under `/api`) instead of a bare 404.
- **Startup banner renders on legacy Windows consoles.** The `pythinker web` / `pythinker vis` PYTHINKER banner raw-printed Unicode block art, which garbled on legacy code pages (e.g. PowerShell with cp1252) and raised `UnicodeEncodeError` when output was redirected. The banner now honors the existing ASCII-glyph detection (`PYTHINKER_ASCII_UI` / `PYTHINKER_TUI_GLYPHS=ascii` opt-ins included) with width-preserving ASCII fallbacks, and degrades per line instead of crashing when a stream rejects Unicode.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.40.1`, or use the native installer for your platform from the [Releases page](https://github.com/Pythoughts-labs/pythinker-code/releases/latest).

## 0.40.0 (2026-06-10)

- **Web: same-origin WebSockets accepted, version banner synced to the backend, and token bootstrap race fixed.** The local-mode web server now auto-populates the allowed-origin list (an empty allowlist rejects every `Origin`-bearing request, which previously broke all WebSocket handshakes with a 403). The UI version banner prefers the version the running backend reports (via the config API) over the stale build-time constant, and a transient version-fetch failure no longer permanently disables the backend banner for the session. The initial auth-token bootstrap race that could fail the first request is resolved. `ESC` now reliably terminates only the background tasks spawned by the interrupted turn, and recall context is re-framed so prior-session snippets can't be misread as new instructions.
- **Deep-audit remediation: security, correctness, and multi-instance robustness.** Permission gate: awk programs that shell out via `print | "cmd"` / `getline` are now classified as mutating AND destructive (previously only `system(`/`>` and only mutating), and `xargs -L N` no longer hides its payload from classification. Glob resolves symlinks before its workspace-boundary check (an in-workspace symlink could previously list outside content); progress-note titles are ANSI-sanitized like every other transcript field. Grep content lines are parsed with unambiguous field separators, so paths like `utf-8-codec.py` are no longer mangled with `-n=false` and sensitive-file attribution is exact. Multi-line edits on CRLF files work again (LF-joined old strings are CRLF-translated when needed). `/import` preserves paths byte-for-byte (only a standalone leading/trailing `--force` is treated as the flag). Post-compaction file reminders include `--add-dir` files. Double-interrupt can no longer orphan the interruption-marker write (unanswered tool_calls). Background web replay falls back to full history (not empty) when the watermark stat fails, and a malformed Agent resume id returns a clean "Agent not found". OAuth: login fails loud when the token response lacks a `refresh_token`; a refresh response without `expires_in` carries the previous lifetime forward instead of refreshing every tick; the device-id file can no longer be read empty mid-creation. A failed `theme="auto"` background probe can be retried by re-selecting auto via `/theme`. Multi-instance: sessions now take a per-session writer lock (a second `pythinker -r <id>`/web worker on the same session is refused instead of interleaving turns), the shared `pythinker.json` index uses a locked read-modify-write (no more lost work-dir registrations), JSONL appenders repair torn final lines after a crash, forks materialize atomically, project-memory mutations abort on read failure instead of wiping the file, the journal is capped at 100 recaps, inbox approve/reject claims candidates atomically, and recall re-arms when another instance writes new memory. Subagents: a failed summary continuation no longer discards a completed agent's work, hallucinated subagent types fail fast with the valid-type list (before any RunAgents child launches), background failures carry an `Agent ID:` + resume hint, and a crash inside the runner's own error handling is logged instead of silently lost.
- **Breaking (CLI flags): `pythinker web` / `pythinker vis` host short flag is now `-H`.** `-h` is a help alias on both subcommands (matching the root CLI); previously `-h <ip>` bound the host. Scripts using `-h 0.0.0.0` now print help and exit 0 without starting a server — switch to `-H <ip>` or `--host <ip>`. Part of the security/correctness audit (which also confined Grep to the workspace, gated non-HTTPS provider URLs in the web config API to loopback, and stopped saving OpenAI keys on 401/403).
- **Thinking effort moved to a single top-right label on the input border.** The input box border is now one static frame grey at every effort level instead of recoloring the whole bar cold→hot, and the effort is no longer duplicated in the footer line. It's shown once, as a small label flushed to the right of the input's top border — a level-colored dot (slate→blue→teal→amber→orange→red as `off→max`) plus the muted level word — so the dial stays glanceable without tinting the typing area or cluttering the footer. The label is hidden entirely for native-thinking models (`always_thinking`, no user dial) and non-thinking models, and the rule auto-shortens by the label width so the line never wraps.
- **Alibaba login: correct plan-key routing, full live model discovery, and `qwen3.7-plus` default.** Subscription "plan" keys — `sk-sp-`, `sk-tok-`, and `sk-ws-` — now route to the shared international Token Plan endpoint (`token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`), fixing a bug where `sk-sp-` keys were sent to the Coding Plan host (`coding-intl`) and every chat then failed with `401 invalid_api_key`. Generic `sk-` keys remain pay-as-you-go Cloud (DashScope) keys. Model discovery no longer filters the live `/models` response down to a hardcoded allowlist — every chat model the endpoint returns now appears (known models keep curated capabilities/context; the rest get sensible defaults), while text-to-image models (Wan, Qwen-Image) are excluded since they can't serve as the agent's LLM. The catalog therefore reflects the key's tier: a Token Plan key surfaces the multi-vendor set (Qwen, DeepSeek, GLM, Kimi, MiniMax), a pay-as-you-go key surfaces that account's Qwen line. The first-login default model is now `qwen3.7-plus` (falling back to the first available model when an endpoint doesn't offer it). The usage panel detects endpoints with no quota API and shows a clear note pointing to the Model Studio console alongside Pythinker's local token tally instead of probing a 404 quota endpoint. The built-in catalog remains the offline fallback when discovery is unavailable. For the Token Plan, whose usage policy forbids automated balance polling and exposes no quota API, `/usage` shows Pythinker's local token tally plus a note pointing to the Model Studio console (My Subscriptions / Usage Analysis) for the Credits balance.
- **Qwen models treated as native-thinking across both plans.** Qwen3.x/3.7 (e.g. `qwen3.7-max`, `qwen3.6-plus`, the Qwen3 Coder models) now carry the `always_thinking` capability on both the Alibaba Model Studio and OpenCode Go plans, matching GLM/MiniMax: reasoning is built in and always on, with no user effort dial and no top-border effort label. Reasoning still flows over the Anthropic `thinking` block that both Anthropic-compatible routes accept.
- **TUI enhancements: adaptive theme, layout, and agent prompt overhaul.** Adaptive terminal-background probe + color-depth blending; reference-CLI layout and palette refinements; unified todo-list renderer; white running-task titles with consistent diff palette; elapsed/tokens/t-s metadata on the background status line; transcript-row bullet fix; renderer guards and markdown fence table unwrapping. All default agent prompts restructured with explicit Mission / Hard Constraints / Workflow / Output Contract sections. Background manager and subagent runner hardened with stale-record reconciliation and resume contract enforcement. Automatic turn recaps disabled by default.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.40.0`, or use the native installer for your platform from the [Releases page](https://github.com/Pythoughts-labs/pythinker-code/releases/latest).

## 0.39.0 (2026-06-09)

- **Refreshed TUI theme and Catppuccin syntax highlighting.** The interface adopts a brand periwinkle/indigo accent (`#B3B9F4` dark / `#0B114E` light) with a reharmonized selection tint, and code blocks now highlight with Catppuccin Mocha (dark) / Latte (light), adaptive to the active theme — implemented as foreground-only Pygments styles with no new dependency. Markdown inline code and links render terminal-native cyan, blockquotes green, and ordered-list markers bright blue (so they adapt per terminal), and user messages sit on a neutral grey block instead of the prior blue tint.
- **Homebrew updater no longer no-ops or false-reports success.** `pythinker update` on a Homebrew install now runs `brew update` to refresh the tap before `brew upgrade`, so a stale local tap clone can't pin the old formula and silently no-op ("0.38.0 already installed"). After upgrading it re-checks the installed version via `brew list --versions` and reports a clear failure instead of "Updated successfully!" when the version did not actually advance.
- **Friendlier usage-limit (429) messages and ChatGPT account switching.** When a provider returns a 429, Pythinker now renders a human-readable notice — the plan name, the reset window, and a dimmed `Server:` detail line (all markup-escaped) — instead of a raw error string. `/login` for ChatGPT now uses `prompt=login`, so you can switch between ChatGPT accounts instead of being silently kept on the previous session.
- **Agent phase-0 enhancements.** Adds a model-invocable cross-session Recall tool (search and read prior sessions on demand, sanitized and read-only for subagents), read-only MCP resources/prompts surfaced as tools, project-scoped `.pythinker/mcp.json` layering, subagent token/cost roll-up to the orchestrator, and truncated tool output that spills to disk with a recovery hint instead of being lost.
- **No more spurious `coroutine … was never awaited` warnings.** Dropped Sentry's `AsyncioIntegration`, whose `create_task` monkeypatch wrapped every coroutine and — when a task was cancelled before its first step during turn/prompt teardown — orphaned the inner coroutine, printing `WireUISide.receive` and prompt_toolkit "never awaited" `RuntimeWarning`s to the console. The integration added no spans (tracing/profiling are off), and exception capture for async tasks is preserved by the existing asyncio exception handler.
- **Read-only profile guard hardened against version-pinned interpreters.** Inline-code interpreter invocations that use a version-suffixed or absolute binary (`python3.14 -c …`, `/usr/bin/python3.12 -c …`, `node20 -e …`) are now classified as mutating/destructive just like the bare `python`/`node` forms, so they can no longer bypass a read-only subagent profile or skip destructive deliberation.
- **The agent sets up and removes MCP servers on request instead of refusing.** Asked to add, remove, or set up an MCP server, the default agent now knows it runs in Pythinker: it configures the server with the `pythinker mcp add`/`remove` CLI (or by editing `~/.pythinker/mcp.json` / `./.pythinker/mcp.json`), verifies with `pythinker mcp list`/`test`, and tells you to restart or `/reload` to load the change — rather than refusing or citing Claude Code/Desktop config paths (`~/.claude.json`) it cannot use. The prompt now also hard-steers the agent away from writing `mcpServers` into `~/.pythinker/config.yaml` (YAML is never parsed for MCP, so such an entry is silently dropped and the server never appears in `/mcp`). As a backstop, MCP config loading now logs a warning when it finds an `mcpServers` block in a `config.yaml` (global or project), so a human or agent that misplaces it gets a diagnosable trace instead of a silent drop.
- **Security: dependency vulnerability remediation.** Cleared the open Dependabot advisories across all manifests. Python: `asyncssh` 2.22.0 → 2.23.0 (path-traversal in `AuthorizedKeysFile %u`) in the `pythinker-host` pin and both lockfiles, and `starlette` 1.0.0 → 1.2.1 (Host-header path poisoning). JS: regenerated the `web`, `vis`, and `install-counter-worker` lockfiles and bumped the worker's `vitest` to `^3.2.6` (critical Vitest UI arbitrary file read/exec), clearing all critical/high/moderate advisories. The only residual is a handful of low-severity transitive `elliptic`/`bn.js` advisories in `web`'s browser crypto polyfill chain, left unforced because the fix downgrades `vite-plugin-node-polyfills` and majors `ai`, breaking the build for marginal benefit.

Upgrade with `pythinker update`, `pip install --upgrade pythinker-code==0.39.0`, or use the native installer for your platform from the [Releases page](https://github.com/Pythoughts-labs/pythinker-code/releases/latest).

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
