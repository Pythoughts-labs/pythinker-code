# TUI Renderer Contract-Hardening — Design

- **Date:** 2026-05-29
- **Status:** Approved design — implementation plan pending (`writing-plans`)
- **Author:** Mohamed Elkholy
- **Scope:** Harden the existing Pythinker terminal UI against a known catalog of rendering bug classes, **leading with Markdown + security/code-scan report rendering**.
- **Builds on (prior art — do not contradict):**
  - `2026-05-28-standardized-report-renderer-design.md` (origin of `components/report.py`)
  - `2026-05-07-readable-terminal-reports-design.md`
  - `2026-05-21-tui-spacing-design.md`
  - `2026-05-28-pi-tui-engine-port-plan.md`, `2026-05-22-blackbox-src-tui-port-design.md`

---

## 1. Context & problem statement

We received a comprehensive spec ("Design & Build an Enhanced Terminal UI / CLI / TUI Renderer") describing a full-screen renderer hardened against ~13 subsystems' worth of bug classes harvested from a real changelog. The spec's literal instructions (Principle #1; Implementation steps 1–4) call for building a **cell-based virtual screen buffer, deterministic differ, display-width library, and ANSI normalizer from scratch**.

Pythinker Code (v0.25.0) already obtains **all** of those primitives from two mature libraries it depends on:

| Primitive the spec asks us to build | Already provided by |
|---|---|
| Virtual screen buffer of cells | **Rich** `Segment`/`Console`/`Live` |
| Deterministic diffing, idempotent frames | **Rich** `Live` |
| Display-width (CJK/emoji/combining) | **Rich** `cell_len` (its own Unicode East-Asian width tables; no `wcwidth` dep) |
| ANSI span normalization, fg/bg reset | **Rich** `Style`/`Segment` |
| Color-depth & OSC 8 capability detection | **Rich** `Console` |
| Alternate screen, cursor/keyboard restore | **prompt_toolkit** `Application` |
| Input buffer, IME, bracketed paste, key bindings | **prompt_toolkit** `Buffer`/`KeyBindings` |

Building those from scratch would reimplement Rich/Textual/prompt_toolkit, violate the project's **zero-new-bundled-dependencies** and **simplicity-first** constraints, and *introduce* the very regressions the spec exists to prevent.

The relevant rendering code already exists and is substantial: `utils/rich/markdown.py` (949 LOC), `ui/shell/components/markdown.py` (643), `ui/shell/components/report.py` (275), `ui/shell/visualize/_live_view.py` (1,301), `ui/shell/prompt.py` (3,257), with snapshot tests in `tests/ui_and_conv/` using Rich `Console.capture()` + `inline-snapshot`.

## 2. The reframe (the core decision)

**The spec is a behavioral contract, not an implementation directive.** Its statements split into two kinds, treated differently:

- **Behavioral requirements** (idempotent frames, correct CJK width, tables survive piped inline code, keyboard mode resets on every exit path) — these **bind**, expressed as automated tests.
- **Implementation directives** ("build a cell buffer", "no regex-only Markdown", "no string-prefix shell logic") — these bind **new code only**. Existing code that *passes the behavioral contract* is **pinned, not refactored**.

Consequence: the win condition is an **aggressive, deterministic, bug-class-mapped test suite**. If Rich + prompt_toolkit (plus the existing Pythinker layer) pass it, we have met the intent of the spec without writing fragile new rendering logic. We write code **only where a contract test fails.**

This reconciliation specifically governs the existing **regex-based Markdown table-repair pipeline** in `components/markdown.py`. "No regex-only Markdown" is an implementation directive; it does not license rewriting load-bearing repairs (`_repair_crammed_markdown_tables`, `_normalize_markdown_tables`, `_normalize_table_block`, the priority-matrix detector) that already handle real malformed streaming output. That pipeline is the highest-**value** surface to **pin** (characterization tests), not the highest-priority surface to **refactor**.

## 3. Goals / non-goals

### Goals
1. A regression-test suite mapped **1:1** to the spec's bug classes, tagged by test tier.
2. **Deep** hardening of Markdown + security/scan **report** rendering (the lead phase), grounded in real data.
3. Two thin architectural disciplines (screen-authority, state-isolation) layered on the existing stack.
4. A **shallow, sequenced roadmap** for the other 11 subsystems — enough to execute later, not full sub-specs.
5. A capability-matrix doc + a `/terminal-setup` stub for the emulator long tail.

### Non-goals
- No new renderer / screen buffer / differ / width engine.
- **No new bundled runtime dependencies** (hard project constraint).
- **No refactor of passing regex repairs.**
- No `/copy` Markdown→clipboard feature (does not exist today; see §6.5) unless separately requested.
- Tier-3 emulator-specific corruption is **not** mechanically tested (guarded by invariant + matrix doc).
- The other 11 areas are designed only to roadmap depth in this document.

## 4. Foundational principles → existing stack (contract mapping)

| Spec principle | Satisfied by | What *we* add (the contract) |
|---|---|---|
| 1. One authoritative screen model | Rich `Console`/`Live` | **Screen-authority discipline** (§5.1): no ad-hoc writes in the live region |
| 2. Deterministic diff + idempotent frames | Rich `Live` | **Idempotency harness** (§7): render twice → identical segments |
| 3. Self-healing repaint | pt `Application` invalidate / Rich `Live` refresh | Tier-2 pty tests for resize/refocus/attach |
| 4. Unicode-correct layout | Rich `cell_len` (Unicode width tables) | **Width-boundary harness** (§7): exact-full-width + CJK |
| 5. Parse, don't pattern-match | markdown-it-py AST (render path) + structured `parse_report_block` | Fence-aware report extraction (H1, §6.4); shell parser audit (roadmap) |
| 6. State isolation | separate modules today | **State-isolation map** (§5.2) pinned by mutation tests |
| 7. Reset modes reliably | pt exit handling | Tier-2 "every exit path resets keyboard mode" test |
| 8. Capability detection | Rich/pt detection | Capability-matrix doc + `/terminal-setup` stub (roadmap) |

## 5. Architecture — two thin disciplines, zero new renderer

### 5.1 Screen-authority discipline
All live-region output flows only through the existing `LiveView`/`Console`. No ad-hoc `print()` or raw escape writes in the live region. Enforced by a **guard test** (grep/AST check over the live-region modules) rather than a new abstraction. Static/committed scrollback continues to use Rich renderables.

### 5.2 State-isolation map (Principle #6 onto real modules)
| State owner | Module | Isolation contract (test) |
|---|---|---|
| Prompt input buffer | `ui/shell/prompt.py` (pt `Buffer`) | Async task/status updates never mutate the input buffer |
| Streaming Markdown committer | `PythinkerMarkdownStream` (`components/markdown.py`) | `push()`/`flush()` own `pending`; committed slices are immutable |
| Report state | `components/report.py` (`Report` frozen dataclass) | `parse_report_block` is pure; malformed input never mutates prior output |
| Paste payloads | `prompt.py` paste handlers + `utils/clipboard` | Paste normalization isolated from history append |
| Background sessions | `background/` | Foreground prompt state never reads/writes session state directly |

Each row becomes a test that mutates one owner and asserts the others are byte-identical.

### 5.3 Capability layer
Document (not re-implement) what Rich detects (color depth: truecolor/256/16/no-color; OSC 8 hyperlinks) and what prompt_toolkit detects (keyboard protocol, bracketed paste, clipboard mechanism). Add a **capability-matrix doc** and a `/terminal-setup` **stub** that surfaces known-problematic environments (VS Code/Cursor/Windsurf GPU acceleration, etc.). The stub is roadmap, not lead phase.

## 6. Lead Phase — Markdown + Report rendering (DEEP)

**Targets:** `utils/rich/markdown.py`, `ui/shell/components/markdown.py`, `ui/shell/components/report.py`.
**Method:** strict **pin → fail → minimal-fix**. All Tier 1 (deterministic `Console.capture()` + `inline-snapshot`).

### 6.1 Characterization snapshots (pin current correct behavior)
Snapshot the regex repair pipeline on real malformed-stream inputs *before* any change:
- glued prose+table header (`Medium| # | File |`) → `_repair_crammed_markdown_tables`
- dropped header/delimiter newline and crammed data rows → `_normalize_table_block`
- priority-matrix code blocks → `_render_priority_matrix`
- report-icon simplification outside fences → `_simplify_markdown_report_icons`

These lock in behavior so any later change that alters them is caught.

### 6.2 Table bug-class contract tests (Tier 1)
Parametrized over widths (incl. exactly-full-width and narrow) and both themes:
- table with **piped inline code** (`` `a|b` ``) and **escaped pipes** (`\|`)
- **empty header** cells; **very long** cells (wrap + reflow)
- **border color** must not inherit code-span color (color-bleed guard)
- **wrapped continuation** lines preserve inline style
- **stale bordered table** must not remain in scrollback while streaming

### 6.3 Report rendering grounded in real data
`security-scan-findings.json` holds **92 real findings** in raw scanner shape:
`filePath`, `severity` (UPPERCASE), `vulnSlug`, `title`, `description`, `lineNumbers`, `recommendation`, `confidence`, `producedByRunId`.

This is **not** the `Report`/`ReportFinding` shape (`title`, `severity` lowercase, `location`, `body`) that `parse_report_block` consumes. Therefore:
1. **Pin the raw→Report transform** (case-fold `CRITICAL`→`critical`; `filePath`+`lineNumbers`→`location`; `description`/`recommendation`→`body`). Locate or, if absent, specify it in the plan.
2. Snapshot `render_report` over the transformed fixture across **all five severities**, **both themes**, and **several widths**.
3. Snapshot `render_agent_body` promoting a ` ```report ` block embedded in surrounding Markdown.

### 6.4 Three hypotheses — written as **failing tests first**, not asserted as defects
- **H1 (looks real):** `_REPORT_FENCE_RE` in `report.py` is a flat regex that does not track outer fence nesting; a ` ```report ` block shown *inside* a documentation ` ``` ` fence may be wrongly promoted to a report. **Test proves it; fix = fence-aware extraction reusing the committer's markdown-it parser** (Principle #5 binds this *new* code).
- **H2 (may not reproduce):** the streaming committer computes commit offsets on **raw** text (`markdown_commit_boundary`) while the renderer transforms **repaired** text; line-count changes could desync → duplicate/stale rows. **Write the reproduction test; if it cannot reproduce, record that and move on** (no speculative fix).
- **H3:** render-same-state-twice **idempotency** for report + repaired-table interaction (identical segments on re-render).

### 6.5 Display-vs-copy contract (guard, not feature)
**Verified:** there is no `/copy` Markdown→clipboard command today. Clipboard handling is paste-only (`prompt_toolkit` + `pyperclip` + media grab); the only "copy" is `/fork` (session history). So the spec's "separate render paths for display vs. clipboard" and "/copy column misalignment" become a **guard for when such a path is added**:
- a separate `markdown_to_plain()` render path with its own snapshot;
- a test asserting **no ANSI/borders/OSC-8 escapes** leak into copied bytes and **no trailing whitespace** in streamed copy output.

Building the actual `/copy` feature is out of scope unless requested.

## 7. Regression-suite design

- **Location:** `tests/ui_and_conv/`. **Idioms:** Rich `Console.capture()` + `inline-snapshot` (existing), `pexpect`/pty for Tier 2.
- **One docstring-tagged test per spec bug class**, plus a **bug-class → test-id → tier registry** (§8) — the 1:1 mapping the spec demands.
- **Idempotency harness:** `render(state)` twice → assert identical segment streams. Structurally kills duplicate-scrollback / progressive style-degradation for Tier 1.
- **Width-boundary harness:** parametrized widths incl. exactly-full-width and CJK; assert no overflow via `cell_len`.
- **Theme harness:** every report/markdown snapshot runs against dark *and* light to catch contrast/color-bleed.

## 8. Bug-class → test registry (1:1 mapping, by tier)

> Lead-phase rows (areas 3–5) are specified in detail above. The full catalog is enumerated here so every bug class has an owning test id and a tier. `T1` = deterministic capture; `T2` = pty; `T3` = invariant + manual matrix.

| Spec area | Representative bug class | Test id (planned) | Tier |
|---|---|---|---|
| 1 Renderer stability | duplicate scrollback rows; style-pool leak; color bleed | `test_idempotent_frame`, `test_style_pool_stable_longsession` | T1 / T2 |
| 2 Fullscreen/alt-screen | leftover content after exit; literal markers in-progress; dialog submit-underneath | `test_altscreen_restored_on_cancel` | T2 |
| 3 **Markdown/rich text** | table breaks on piped inline code; border inherits code color; wrapped line loses style; stale streaming table; link→plain | `test_table_piped_code`, `test_border_no_codecolor_bleed`, `test_wrap_keeps_style`, `test_stale_table_streaming`, `test_osc8_link_fallback` | **T1** |
| 4 ANSI/themes/contrast | wrong-position colors; 256-bg bleed on attach; unreadable on theme mismatch; spinner color churn | `test_ansi_span_normalize`, `test_theme_contrast_both_bg` | T1 / T3 |
| 5 Wrapping/resize/width | stray leading space at exact width; CJK overflow/ghosts; spinner freeze after resize | `test_exact_full_width_no_stray_space`, `test_cjk_no_overflow` | T1 / T2 |
| 6 Scrolling/navigation | scroll breaks in attached session; offset reset after deletion | `test_scroll_offset_preserved` | T2 |
| 7 Prompt input/keyboard | typing lag large prompt; duplicate history; keyboard mode not reset on exit | `test_keyboard_mode_reset_all_exits`, `test_history_append_once` | T2 |
| 8 Paste/clipboard/images | duplicated right-click paste; lost via stash/replay; bad-image crash | `test_paste_paths_isolated`, `test_bad_image_placeholder` | T2 |
| 9 Shell/Bash/PowerShell | string-prefix permission gap; crash on malformed syntax; orphaned pty | `test_shell_permission_structured`, `test_pty_cleanup_on_eof` | T2 |
| 10 CLI/discovery | duplicate slash commands; trailing-tab cmd treated unknown; headless silent-fail | `test_slash_dedup`, `test_headless_reports_invalid_cmd` | T1 / T2 |
| 11 Background sessions | stuck blocked/running; doubled list rows; no repaint on attach | `test_session_attach_repaint` | T2 |
| 12 Spinner/progress/status | stale amber across tool calls; token counter zero; frozen elapsed time | `test_spinner_phase_derived`, `test_progress_reserved_area` | T1 / T2 |
| 13 IDE/emulator | VS Code spinner-count corruption; emulator keyboard/clipboard quirks | capability-matrix doc; `/terminal-setup` | **T3** |

## 9. Roadmap for the other 11 areas (shallow — sequenced, not full designs)

Each area gets **one row**, not a sub-spec. Sequence = recommended build order after the lead phase.

| Seq | Area | Lead guard strategy | Tier | Notes |
|---|---|---|---|---|
| 1 | Renderer stability / idempotency | Idempotency + long-session style-pool harness | T1/T2 | Cheap, high value; partly covered by lead phase |
| 2 | Wrapping/resize/width | Width-boundary harness (exact-full-width, CJK) | T1/T2 | Reuses lead-phase harness |
| 3 | ANSI/themes/contrast | Span-normalize + both-bg contrast snapshots | T1/T3 | Reuses theme harness |
| 4 | Prompt input/keyboard | pty: keyboard-mode-reset on every exit; history append-once | T2 | Highest user-visible risk |
| 5 | Paste/clipboard/images | pty: isolate paste paths; bad-image placeholder | T2 | |
| 6 | Scrolling/navigation | pty: offset/selection preserved across mutation | T2 | |
| 7 | Fullscreen/alt-screen | pty: alt-screen restored on cancel/error | T2 | |
| 8 | Background sessions | pty: attach idempotent + full repaint | T2 | |
| 9 | Spinner/progress/status | phase-derived spinner; reserved progress area | T1/T2 | |
| 10 | Shell/Bash/PowerShell parsing | audit permission analysis for structured parsing | T2 | Security-adjacent; flag for explicit review |
| 11 | IDE/emulator matrix + `/terminal-setup` | capability-matrix doc + setup flow | T3 | Not mechanically testable |

## 10. Deliverables

1. This design doc.
2. Bug-class → test-id → tier **registry** (§8) maintained alongside the suite.
3. Lead-phase **Tier-1 contract suite** (characterization + bug-class + report-on-real-data), on greenlight.
4. Capability-matrix doc + `/terminal-setup` **stub**.
5. Shallow roadmap (§9) for the remaining areas.

## 11. Acceptance gate (maps to the spec's Required Test Matrix)

- **Lead phase done when:** all §6 Tier-1 tests pass; the three hypotheses (§6.4) are each resolved (fixed-with-test, or recorded-as-non-reproducing); idempotency + width-boundary + theme harnesses are green; the raw→Report transform is pinned against the real 92-finding fixture.
- **Long-session streaming**, **layout boundaries**, **Markdown stress** rows of the spec matrix are covered by Tier 1 here. **Input / Shell / Paste / Emulator** rows are explicitly deferred to the roadmap with their tiers, so coverage is never silently over-claimed.

## 12. Risks & open questions

- **R1 — characterization brittleness:** pinning the regex pipeline locks current behavior, including any current *wrong* output. Mitigation: review each characterization snapshot at creation; mark known-imperfect ones with a `# pinned: imperfect` note and a follow-up test.
- **R2 — raw→Report transform location:** RESOLVED during execution — **no in-repo transform exists**; the external scanner emits canonical ` ```report ` JSON directly, and `parse_report_block` rejects any non-canonical severity. So the test-local adapter in `test_report_realdata.py` *is* the documented contract. The raw fixture (`security-scan-findings.json`, 92 findings) carries scanner-native severities including two outside the canonical five — `BUG` (4) and `HIGH_BUG` (3); the adapter folds them (`HIGH_BUG→high`, `BUG→medium`) with a documented map.
- **R3 — H2 may not reproduce:** acceptable; the methodology records non-reproduction rather than inventing a fix. **Execution result: H2 did NOT reproduce** (the glued prose+table case reassembles with each row rendered exactly once); kept as a guard. H3 (idempotency) also passed.
- **OQ1:** Should `/copy` actually be built (turns §6.5 from guard into feature)? Default: no.
- **OQ2:** Tier-2 pty harness — adopt `pexpect` (test-only dev dep) or extend existing `tests_e2e` subprocess approach? Lead phase is Tier 1, so this is deferred to roadmap seq 4.

### Deferred defects (found during execution — tracked, not fixed in lead phase)

- **D1 — narrow stacked-table mid-word fold + missing continuation indent.** Location: `src/pythinker_code/utils/rich/markdown.py` → `TableElement` stacked-record path (triggered for ≥4 columns or any cell >48 chars). At viewport widths < ~40 a long cell value folds **mid-word** (`theta` → `t\nheta`) and continuation lines lose the leading `  ` indent. **No data loss** — every character survives, it only looks ragged; `test_table_long_cell_wraps_without_dropping_content` guards the data-integrity contract (whitespace-insensitive survival), not the cosmetics. Deferred fix: word-wrap the cell value with a hanging/`subsequent_indent` (e.g. `rich.text.Text.wrap` or a `textwrap` pass) in the cell-emission loop. Roadmap polish, not lead phase.

## 13. Working method

Before each subsystem: state which bug classes it must structurally prevent and how the design makes them impossible (not merely unlikely). After each subsystem: run its regression tests before moving on. If a proposed enhancement could reintroduce any guarded bug class, redesign rather than patch. Never bypass the screen-authority discipline for "quick" writes; never add regex-only Markdown or string-prefix shell permission logic in **new** code.
