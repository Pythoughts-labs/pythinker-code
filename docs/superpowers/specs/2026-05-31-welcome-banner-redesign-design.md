# Welcome Banner Redesign — Design Spec

**Date:** 2026-05-31
**Branch:** `feat/welcome-banner-redesign`
**Scope:** Visual redesign of the startup welcome banner only. The robot logo art and its colors are unchanged.

---

## 1. Goal

Make the startup banner cleaner, more readable, and more professional, without changing
the robot logo glyphs or palette. Success = the banner renders as the approved
"footer chip" layout, all existing banner tests pass, and the contiguous welcome
string e2e tests depend on is preserved.

**One-sentence success criterion:** `pytest tests/ui_and_conv/test_shell_welcome_info.py`
stays green, the e2e substring `"Welcome to Pythinker — think first, then code."`
still appears verbatim, and the rendered panel matches the approved mock below.

---

## 2. Current vs. Proposed

### Current (v0.27.0)

```
╭─ Pythinker Code v0.27.0 ───────────────────────────────────────────╮
│         ●       ✦ What's new in v0.27.0 · /changelog               │
│         │                                                           │
│     ▛▀▀▀▀▀▀▀▜                                                       │
│    ◖█ ◉   ◉ █◗  Welcome to Pythinker — think first, then code.      │
│     ▙▄▄▄≡▄▄▄▟   Review · Secure · Diagnose · then Create. Send /help│
│                                                                    │
│   Directory  │  ~                                                  │
│     Session  │  be1c9425-...                                       │
│   Auto-save  │  ~/.pythinker/sessions/.../context.jsonl           │
│       Model  │  MiniMax M2.7                                       │
│  Tips ...                                                          │
╰────────────────────────────────────────────────────────────────────╯
```

Problems: the "What's new" chip sits awkwardly above the antenna and competes with the
logo for the top-left; the strapline overflows past `/help`; the `│` separator column
adds visual noise to the info grid.

### Proposed ("Footer chip")

```
╭─ Pythinker Code v0.27.0 ─────────────────────────────────────────╮
│                                                                  │
│         ●                                                        │
│         │                                                        │
│     ▛▀▀▀▀▀▀▀▜   Welcome to Pythinker — think first, then code.   │
│    ◖█ ◉   ◉ █◗  Review · Secure · Diagnose · then Create.        │
│     ▙▄▄▄≡▄▄▄▟   Send /help for help.                             │
│                                                                  │
│   Directory  ~                                                   │
│     Session  be1c9425-6f1f-47d5-8e33-01d2d13c44c9                │
│   Auto-save  ~/.pythinker/sessions/…/context.jsonl              │
│       Model  MiniMax M2.7                                        │
│                                                                  │
│   Tips                                                           │
│     • send /login to use Pythinker for Coding                    │
│     • Pythinker reviews before it writes …                       │
│     • Spot a bug? Type /feedback …                               │
│                                                                  │
╰─────────────────── ✦ What's new in v0.27.0 · /changelog ────────╯
```

(Verbatim-reproduced output of this layout was generated against the installed Rich
15.0.0 during design; see §6 verification.)

---

## 3. Approved Changes

1. **Chip → footer.** The "What's new" / "↑ Update available" chip moves from a
   top-right inline cell to the **Panel subtitle** (bottom border), right-aligned.
   It keeps its own accent color (info-cyan or warning-yellow) — confirmed it does
   not collapse to the border grey.

2. **Headline block aligned to the robot body.** The right-hand cell holds three lines —
   headline / strapline / help — bottom-aligned against the 5-line logo
   (`vertical="bottom"`), so the antenna (`●` / `│`) floats above and the three text
   lines sit beside the robot's face/body/mouth rows.

3. **Strapline on its own line.** `"Review · Secure · Diagnose · then Create."` and
   `"Send /help for help."` become two separate lines instead of one overflowing line.
   The headline `"Welcome to Pythinker — think first, then code."` remains a single
   contiguous line (e2e dependency).

4. **Drop the `│` separator** in the info grid. Two columns: right-aligned label,
   left-aligned value, separated by a 2-space gutter (`padding=(0, 1)` on a 2-col table).

5. **Theme-token border (light-mode polish).** Replace the raw `_PYTHINKER_BORDER =
   "grey39"` literal and the per-label grey fallbacks with the active theme's `border` /
   `muted` / `dim` tokens, so the frame reads correctly in light mode too. No test
   asserts border or title color, so this is safe. The brand title text
   ("Pythinker Code") and version suffix keep their muted/dim treatment via tokens.

**Out of scope (logged, not changed):** the robot glyphs and palette; the Tips strings
(owned by `app.py`); `_welcome_banner_chip()` precedence logic; the `WelcomeInfoItem`
data shape; anything in `app.py`.

---

## 4. Architecture & Touched Code

Single function, single file: **`src/pythinker_code/ui/shell/__init__.py`**.

| Unit | Lines (current) | Change |
|------|-----------------|--------|
| `_LOGO`, `_LOGO_*` color consts | 1859–1874 | **Unchanged.** |
| `_PYTHINKER_BORDER` | 1864 | Replaced by a theme-token lookup (helper or inline `_t.border`). |
| `WelcomeInfoItem` | 1877–1886 | **Unchanged** (public-ish; gated by tests). |
| `_value_style_for_label` | 1889–1907 | **Unchanged** (Directory→info token gated by test). |
| `_welcome_banner_chip` | 1910–1931 | **Unchanged** (precedence gated by test). |
| `_print_welcome_info` | 1934–2008 | **Rewritten body** per §3. Signature unchanged: `(name, info_items, *, banner: Text \| None = None)`. |

### `_print_welcome_info` new structure

- Build `logo = Text.from_markup(_LOGO)` (unchanged).
- Build the header `Table` with two columns: `[logo]` (top), `[Group(head, strapline, help)]`
  with `vertical="bottom"`. One row. The previous `banner is not None` top/bottom-padding
  branch is **removed** — the chip no longer lives in this table.
- `head = Text.from_markup("Welcome to Pythinker — think first, then code.")` (contiguous).
- `strapline` + `help_text` become two separate `Text` renderables; `/help` keeps its
  bold-warning highlight.
- Info grid: 2-column `Table` (right label / left value), label style `muted`, value style
  via `_value_style_for_label`. No separator column.
- Tips: **unchanged** 2-column hang-indent table.
- `Panel(Group(*rows), title=version_title, title_align="left",
  subtitle=banner, subtitle_align="right", border_style=<token>, box=box.ROUNDED,
  expand=False, padding=(1, 2))`. When `banner is None`, `subtitle` is `None` →
  byte-identical to omitting it (verified).

### Data flow (unchanged)

`app.run_shell()` builds `welcome_info: list[WelcomeInfoItem]` → `Shell.run()` calls
`_print_welcome_info(name, self._welcome_info, banner=_welcome_banner_chip())`. No
changes to `app.py` or the call site.

---

## 5. Test Impact

**Gating tests — `tests/ui_and_conv/test_shell_welcome_info.py` (5):**

| Test | Holds because |
|------|---------------|
| `test_shell_welcome_uses_pythinker_code_copy` | title, "Welcome to Pythinker", "think first" all still rendered. |
| `test_directory_label_uses_brand_info_token` | `_value_style_for_label` unchanged. |
| `test_welcome_banner_chip_shown_in_output` | chip passed via `banner=` now renders in the **subtitle**; verified its text (incl. `/update`) appears in `export_text()`. |
| `test_welcome_banner_chip_update_wins_over_whats_new` | `_welcome_banner_chip()` unchanged. |
| `test_welcome_banner_no_chip_unchanged` | `subtitle=None` is byte-identical to omitting subtitle (verified on Rich 15.0.0). |

**e2e tests** (`test_shell_pty_e2e.py`, `test_shell_modal_e2e.py`,
`test_subagent_smoke_e2e.py`, `test_slash_completion_enter_tmux.py`): assert only the
contiguous substring `"Welcome to Pythinker — think first, then code."` → preserved.

**New tests to add** (to lock the redesign so it can't silently regress):

1. `test_welcome_chip_renders_in_footer_not_header` — with a chip, the chip text appears
   in the **last** non-empty rendered line and **not** in the first three lines.
2. `test_welcome_info_grid_has_no_pipe_separator` — render with info items; assert the
   `" │ "` separator no longer appears between a label and its value (guard the cleanup).
3. `test_welcome_strapline_and_help_on_separate_lines` — assert no single rendered line
   contains both "then Create." and "Send /help".

No snapshot/golden files exist, so none to regenerate.

---

## 6. Verification Plan

1. **Unit:** `pytest tests/ui_and_conv/test_shell_welcome_info.py -q` → green (5 existing + 3 new).
2. **Visual:** a throwaway script renders `_print_welcome_info` with the real
   `welcome_info` shape at widths 80 / 100 / 120 and with each chip variant
   (none / what's-new / update) — eyeball against the §2 mock. (Already prototyped in
   design; will re-run against final code.)
3. **Lint/type:** `ruff check` + the project's type gate on the changed file.
4. **e2e smoke (if feasible):** confirm the welcome substring still trips
   `read_until_contains` — covered transitively by keeping the headline contiguous.

### Design-time facts established (Rich 15.0.0, the installed version)

- `Panel` supports `subtitle`, `subtitle_align`; `Table.add_column(vertical=...)` supports
  `top|middle|bottom` — confirmed by introspecting the installed package and Context7 docs.
- `subtitle=None` ≡ subtitle omitted (byte-identical export). ✔ invariant for the no-chip test.
- A styled chip keeps its accent color when used as a subtitle (does not inherit border grey). ✔
- The chip never clips: the fixed headline line forces a panel wider than the longest chip. ✔
- The blank spacer between the header block and info grid survives. ✔

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Subtitle text not captured by `export_text()` → breaks `chip_shown_in_output`. | Verified it **is** captured on Rich 15.0.0. |
| Light-mode border token regresses a color test. | No test asserts border/title color; `color_system=None` in unit tests ignores color. |
| Splitting the strapline breaks an unseen assertion. | grep across `tests/`, `tests_e2e/`, docs found **no** assertion on strapline contiguity or `/help` adjacency. |
| Narrow terminal (<64 cols) wrapping. | Same `expand=False` behavior as today; not a regression. Logged, not solved. |
```
