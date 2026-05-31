# Welcome Banner Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the startup welcome banner to the approved "footer chip" layout — cleaner, more readable, more professional — without changing the robot logo glyphs or its colors.

**Architecture:** All changes live in one function, `_print_welcome_info`, in `src/pythinker_code/ui/shell/__init__.py`. The "What's new / Update available" chip moves from a top-right inline cell to the Rich `Panel` **subtitle** (bottom border). The headline/strapline/help block bottom-aligns beside the 5-line robot logo. The info grid drops its `│` separator column. The panel border and title switch from a raw `grey39` literal to theme tokens so they adapt to light mode.

**Tech Stack:** Python 3.12, Rich 15.0.0 (`Panel`, `Table`, `Text`, `Group`, `box.ROUNDED`), pytest, ruff (line-length 100), `uv`.

---

## Background facts (already verified against the installed Rich 15.0.0)

- `Panel(subtitle=, subtitle_align='right', title_align='left', border_style=<Style>, box=box.ROUNDED, expand=False, padding=(1,2))` — all supported.
- `Table.add_column(vertical='bottom')` — supported; bottom-aligns a short cell against a taller sibling cell in the same row.
- `subtitle=None` renders byte-identically to omitting `subtitle`.
- A styled chip (e.g. `[#AFE3F1]✦ …[/]`) keeps its own color when used as a subtitle; it does not inherit the border grey.
- The chip cannot clip: the fixed headline line forces the panel wider than the longest chip.
- Theme helpers already imported in the target file: `tui_rich_style(token_name) -> Style` and `_get_tui_tokens() -> TuiTokens`. `tui_rich_style("border")` resolves (dark `#3A506D`, light `#495F7C`).

## Test command

```bash
uv run pytest tests/ui_and_conv/test_shell_welcome_info.py -q
```

(CI runs `uv run pytest tests/ -q`. Local fallback if `uv` is unavailable: `.venv/bin/python -m pytest tests/ui_and_conv/test_shell_welcome_info.py -q`.)

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `src/pythinker_code/ui/shell/__init__.py` | Renders the welcome banner | Rewrite `_print_welcome_info` body (lines ~1934–2008); remove the now-unused `_PYTHINKER_BORDER` constant (line 1864). `_LOGO`, `_LOGO_*`, `WelcomeInfoItem`, `_value_style_for_label`, `_welcome_banner_chip` stay untouched. |
| `tests/ui_and_conv/test_shell_welcome_info.py` | Banner unit tests | Add 3 tests that lock the redesign. The 5 existing tests stay unchanged and must keep passing. |

---

## Task 1: Add failing tests that lock the redesign

**Files:**
- Test: `tests/ui_and_conv/test_shell_welcome_info.py`

- [ ] **Step 1: Add the three new tests**

Append to `tests/ui_and_conv/test_shell_welcome_info.py` (the file already imports `Console`, `Text`, and `shell_module`):

```python
def test_welcome_chip_renders_in_footer_not_header(monkeypatch):
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    chip = Text("✦ What's new in v9.9.9 · /changelog")
    shell_module._print_welcome_info("Pythinker Code", [], banner=chip)

    lines = [ln for ln in console.export_text().splitlines() if ln.strip()]
    # Chip sits on the bottom border (footer), not in the header.
    assert "changelog" in lines[-1]
    assert all("changelog" not in ln for ln in lines[:3])


def test_welcome_info_grid_has_no_pipe_separator(monkeypatch):
    from pythinker_code.ui.shell import WelcomeInfoItem

    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    items = [WelcomeInfoItem(name="Directory", value="/tmp/proj")]
    shell_module._print_welcome_info("Pythinker Code", items)

    out = console.export_text()
    dir_line = next(ln for ln in out.splitlines() if "Directory" in ln)
    # Only the two panel-edge pipes remain; the separator column is gone.
    assert dir_line.count("│") == 2
    assert "/tmp/proj" in dir_line


def test_welcome_strapline_and_help_on_separate_lines(monkeypatch):
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    shell_module._print_welcome_info("Pythinker Code", [])

    out = console.export_text()
    assert "Build with confidence." in out
    assert "Type /help for commands." in out
    # The strapline and the help line must not share one rendered line.
    assert not any(
        "Build with confidence." in ln and "Type /help" in ln for ln in out.splitlines()
    )
```

- [ ] **Step 2: Run the new tests and confirm they fail against the current banner**

Run:
```bash
uv run pytest tests/ui_and_conv/test_shell_welcome_info.py -q -k "footer or pipe_separator or separate_lines"
```

Expected: all three FAIL.
- `test_welcome_chip_renders_in_footer_not_header` fails because today the chip is in the header (top), so `lines[-1]` has no "changelog" and `lines[:3]` contains it.
- `test_welcome_info_grid_has_no_pipe_separator` fails because today the row is `│ Directory │ /tmp/proj │` → 3 pipes, not 2.
- `test_welcome_strapline_and_help_on_separate_lines` fails if "Build with confidence." and "Type /help for commands." share one line.

- [ ] **Step 3: Confirm the 5 existing tests still pass (no regression introduced by the new tests)**

Run:
```bash
uv run pytest tests/ui_and_conv/test_shell_welcome_info.py -q -k "not (footer or pipe_separator or separate_lines)"
```

Expected: 5 passed.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/ui_and_conv/test_shell_welcome_info.py
git commit -m "test: lock welcome banner redesign (footer chip, no pipe, split strapline)"
```

---

## Task 2: Rewrite `_print_welcome_info` to the footer-chip layout

> **Note (post-implementation):** the shipped `_print_welcome_info` evolved
> beyond the skeleton below. The source is the source of truth; it adds
> responsive width handling (`_welcome_panel_width`, `_WELCOME_MAX_WIDTH`,
> `_WELCOME_PANEL_CHROME_WIDTH`), cell-aware truncation helpers
> (`_truncate_middle_to_width`, `_welcome_value`, `_welcome_tip_lines`), a
> `Table.grid(...)` build, and a `width >= 68` logo-beside-text vs stacked
> branch. Read the block below as the original footer-chip intent, not the
> literal final code.

**Files:**
- Modify: `src/pythinker_code/ui/shell/__init__.py` (function `_print_welcome_info`, lines ~1934–2008; constant `_PYTHINKER_BORDER`, line 1864)

- [ ] **Step 1: Replace the entire `_print_welcome_info` function body**

Find the current function (starts at `def _print_welcome_info(` ~line 1934, ends at the closing of the `console.print(Panel(...))` block ~line 2008) and replace the whole function with:

```python
def _print_welcome_info(
    name: str, info_items: list[WelcomeInfoItem], *, banner: Text | None = None
) -> None:
    _t = _get_tui_tokens()
    head = Text.from_markup("Welcome to Pythinker — think first, then code.")
    strapline = Text.from_markup(
        f"[{_t.muted}]Review · Secure · Diagnose · Build with confidence.[/]"
    )
    help_text = Text.from_markup(f"[{_t.muted}]Type /help for commands.[/]")
    help_text.highlight_regex(r"/help\b", f"bold {_t.warning}")

    # Logo on the left; the 3-line text block bottom-aligns against the 5-line
    # robot so the antenna floats above and the lines sit beside the body.
    logo = Text.from_markup(_LOGO)
    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1), expand=False)
    table.add_column(justify="left")
    table.add_column(justify="left", vertical="bottom")
    table.add_row(logo, Group(head, strapline, help_text))

    rows: list[RenderableType] = [table]

    facts = [item for item in info_items if item.name.strip() != "Tip"]
    tips = [item for item in info_items if item.name.strip() == "Tip"]

    if facts:
        rows.append(Text(""))  # empty line
        info_table = Table(
            show_header=False, show_edge=False, box=None, padding=(0, 1), expand=False
        )
        info_table.add_column(justify="right", style=tui_rich_style("muted"))
        info_table.add_column(justify="left")
        for item in facts:
            value_style = _value_style_for_label(item.name, item.level)
            info_table.add_row(item.name, Text(item.value, style=value_style))
        rows.append(info_table)

    if tips:
        rows.append(Text(""))  # empty line
        rows.append(Text("Tips", style=tui_rich_style("muted")))
        # 2-col table → wrapped tip lines hang-indent under the text column,
        # not under the bullet.
        tips_table = Table(
            show_header=False, show_edge=False, box=None, padding=(0, 0), expand=False
        )
        tips_table.add_column(style=tui_rich_style("muted"), no_wrap=True, width=4)
        tips_table.add_column(justify="left", overflow="fold")
        for item in tips:
            tip_text = Text(item.value, style=item.level.value)
            tip_text.highlight_regex(r"/[A-Za-z][A-Za-z0-9_-]*", "yellow bold")
            tips_table.add_row("  • ", tip_text)
        rows.append(tips_table)

    version_title = Text.assemble(
        ("Pythinker Code", tui_rich_style("muted")),
        (f" v{get_version()}", tui_rich_style("dim")),
    )

    console.print(
        Panel(
            Group(*rows),
            title=version_title,
            title_align="left",
            subtitle=banner,
            subtitle_align="right",
            border_style=tui_rich_style("border"),
            box=box.ROUNDED,
            expand=False,
            padding=(1, 2),
        )
    )
```

Notes on what changed vs. the original (do not skip any):
- The `if banner is not None:` top/bottom-padding branch in the header table is **removed** — the chip is no longer in this table.
- `head`/`strapline`/`help_text` are now three separate `Text` lines (was: head + combined strapline-and-help).
- The header table's second column gains `vertical="bottom"`.
- The info-grid table drops the middle `│` separator column (was 3 columns, now 2).
- `version_title` and `border_style` use `tui_rich_style(...)` tokens instead of the `_PYTHINKER_BORDER` / `"grey50"` literals.
- `subtitle=banner` + `subtitle_align="right"` are added to the `Panel`.
- The `name` parameter remains unused (it was unused before too); leave it to avoid breaking the call site.

- [ ] **Step 2: Remove the now-unused `_PYTHINKER_BORDER` constant**

Delete line 1864:

```python
_PYTHINKER_BORDER = "grey39"
```

Leave the surrounding `_LOGO_*` color constants and `_LOGO` exactly as they are.

- [ ] **Step 3: Confirm `_PYTHINKER_BORDER` has no remaining references**

Run:
```bash
grep -rn "_PYTHINKER_BORDER" src/ tests/ tests_e2e/
```

Expected: no output (zero matches). If any match remains, you removed the constant too early — restore until those references are gone.

- [ ] **Step 4: Run the full banner test file**

Run:
```bash
uv run pytest tests/ui_and_conv/test_shell_welcome_info.py -q
```

Expected: 8 passed (5 existing + 3 new).

If `test_welcome_banner_chip_shown_in_output` fails: confirm you passed `subtitle=banner` (not dropped it). If `test_welcome_banner_no_chip_unchanged` fails: confirm both no-arg and `banner=None` paths reach `subtitle=None` (they do, since the parameter defaults to `None`).

- [ ] **Step 5: Commit the implementation**

```bash
git add src/pythinker_code/ui/shell/__init__.py
git commit -m "feat(shell): redesign welcome banner with footer chip layout"
```

---

## Task 3: Visual + lint + type verification

**Files:** none modified (verification only). Uses a throwaway script that is **not** committed.

- [ ] **Step 1: Render the banner at three widths and all chip states for visual confirmation**

Create `/tmp/verify_banner.py`:

```python
import pythinker_code.ui.shell as sm
from rich.console import Console
from rich.text import Text

Item = sm.WelcomeInfoItem
info = [
    Item(name="Directory", value="~"),
    Item(name="Session", value="be1c9425-6f1f-47d5-8e33-01d2d13c44c9"),
    Item(name="Auto-save", value="~/.pythinker/sessions/abcd/be1c/context.jsonl"),
    Item(name="Model", value="MiniMax M2.7"),
    Item(name="Tip", value="send /login to use Pythinker for Coding", level=Item.Level.WARN),
    Item(name="Tip", value="Pythinker reviews before it writes. Try \"review this diff\"."),
    Item(name="Tip", value="Spot a bug or have feedback? Type /feedback."),
]
chips = {
    "no chip": None,
    "whats-new": Text.from_markup("[#AFE3F1]✦ What's new in v0.27.0 · /changelog[/]"),
    "update": Text.from_markup("[#E6B450]↑ Update available — v0.28.0 · /update[/]"),
}
for width in (80, 100, 120):
    for label, chip in chips.items():
        c = Console(width=width)
        sm.console = c  # render through a width-pinned console
        print(f"\n===== width={width}  {label} =====")
        sm._print_welcome_info("Pythinker Code", info, banner=chip)
```

Run:
```bash
uv run python /tmp/verify_banner.py
```

Expected: the antenna (`●`/`│`) floats above the headline; headline/strapline/help sit beside the robot body; the info grid has no `│` separator; the chip (when present) appears on the bottom border, right-aligned, in its own color; nothing clips at width 80.

- [ ] **Step 2: Lint the changed file**

Run:
```bash
uv run ruff check src/pythinker_code/ui/shell/__init__.py
```

Expected: no errors. (Line-length limit is 100; the code blocks above are within it.) Fix any reported issue and re-run.

- [ ] **Step 3: Type-check the changed file (project type gate)**

Run:
```bash
uv run pyright src/pythinker_code/ui/shell/__init__.py
```

Expected: no new errors introduced by this change. If `pyright` is not the configured checker, run the project's standard type gate instead. Fix any new error and re-run.

- [ ] **Step 4: Run the broader UI test directory to catch unexpected fallout**

Run:
```bash
uv run pytest tests/ui_and_conv/ -q
```

Expected: all pass. If an unrelated pre-existing failure appears, confirm it also fails on `main` before treating it as out of scope.

- [ ] **Step 5: Clean up the throwaway script**

```bash
rm -f /tmp/verify_banner.py
```

(Nothing to commit in this task.)

---

## Self-review notes

- **Spec coverage:** §3 changes 1–5 each map to a Task-2 step (chip→footer = `subtitle=`; bottom-align = `vertical="bottom"`; split strapline = three `Text` lines; drop pipe = 2-col info grid; token border = `tui_rich_style`). §5 new tests = Task 1. §6 verification = Task 3.
- **Placeholder scan:** no TBD/TODO; every code step shows complete code; every command shows expected output.
- **Type/name consistency:** `WelcomeInfoItem`, `_value_style_for_label`, `_get_tui_tokens`, `tui_rich_style`, `get_version`, `Group`, `RenderableType`, `Table`, `Text`, `Panel`, `box` are all already imported in the target file; no new imports needed. `_print_welcome_info` keeps its exact signature, so the `Shell.run()` call site is unaffected.
