from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from pythinker_code.models_dev import refresh_catalog as _refresh_catalog
from pythinker_code.ui.shell.console import console
from pythinker_code.ui.shell.slash import registry
from pythinker_code.ui.shell.stats_collector import (
    AllStats,
    PeriodStats,
    ProviderStats,
    load_all_stats,
)

if TYPE_CHECKING:
    from pythinker_code.ui.shell import Shell

type _LineFn = Callable[[str, str], None]

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_TAB_KEYS = ["today", "this_week", "last_week", "all_time"]
_TAB_LABELS = {
    "today": "Today",
    "this_week": "This Week",
    "last_week": "Last Week",
    "all_time": "All Time",
}


def _fmt_cost(v: float) -> str:
    if v == 0:
        return "-"
    if v < 0.01:
        return f"${v:.4f}"
    if v < 1:
        return f"${v:.2f}"
    if v < 10:
        return f"${v:.2f}"
    return f"${v:.1f}"


def _fmt_tokens(n: int) -> str:
    if n == 0:
        return "-"
    if n < 1_000:
        return str(n)
    if n < 10_000:
        return f"{n / 1000:.1f}k"
    if n < 1_000_000:
        return f"{n // 1000}k"
    return f"{n / 1_000_000:.1f}M"


def _fmt_num(n: int) -> str:
    if n == 0:
        return "-"
    return f"{n:,}"


# ---------------------------------------------------------------------------
# Dashboard model
# ---------------------------------------------------------------------------


class StatsApp:
    """Interactive usage statistics dashboard."""

    def __init__(self, data: AllStats) -> None:
        self._data = data
        self._periods = data.periods
        self._tab_idx = 0
        self._view = "table"
        self._selected_idx = 0
        self._expanded: set[str] = set()
        self._app = self._build_app()

    @property
    def _tab(self) -> str:
        return _TAB_KEYS[self._tab_idx]

    @property
    def _current(self) -> PeriodStats:
        return self._periods[self._tab]

    def _providers_sorted(self) -> list[tuple[str, ProviderStats]]:
        return sorted(
            self._current.providers.items(),
            key=lambda kv: kv[1].cost,
            reverse=True,
        )

    def _render(self) -> StyleAndTextTuples:
        parts: StyleAndTextTuples = []

        def line(text: str, style: str = "") -> None:
            parts.append((style, text))
            parts.append(("", "\n"))

        def txt(text: str, style: str = "") -> None:
            parts.append((style, text))

        # Title
        title = "Usage Insights" if self._view == "insights" else "Usage Statistics"
        line(title, "bold ansicyan")
        line("")

        # Tabs
        tab_parts: list[str] = []
        for i, key in enumerate(_TAB_KEYS):
            label = _TAB_LABELS[key]
            if i == self._tab_idx:
                tab_parts.append(f"[{label}]")
            else:
                tab_parts.append(f" {label} ")
        line("  ".join(tab_parts), "ansiblue")
        line("")

        cur = self._current

        if self._view == "insights":
            self._render_insights(parts, line, txt, cur)
        else:
            self._render_table(parts, line, txt, cur)

        # Help line
        if self._view == "insights":
            line("[Tab/←→] period  [v] table view  [q] close", "ansigray")
        else:
            line(
                "[Tab/←→] period  [↑↓] select  [Enter] expand  [v] insights  [q] close",
                "ansigray",
            )

        return parts

    def _render_table(
        self,
        parts: StyleAndTextTuples,
        line: _LineFn,
        txt: _LineFn,
        cur: PeriodStats,
    ) -> None:
        col_w = {"sessions": 9, "msgs": 9, "cost": 9, "tokens": 9, "in": 8, "out": 8}
        name_w = 26

        def _pad_right(s: str, w: int) -> str:
            return s[:w].ljust(w)

        def _pad_left(s: str, w: int) -> str:
            return s[:w].rjust(w)

        # Header
        hdr = _pad_right("Provider / Model", name_w)
        hdr += _pad_left("Sessions", col_w["sessions"])
        hdr += _pad_left("Msgs", col_w["msgs"])
        hdr += _pad_left("Cost", col_w["cost"])
        hdr += _pad_left("Tokens", col_w["tokens"])
        hdr += _pad_left("↑In", col_w["in"])
        hdr += _pad_left("↓Out", col_w["out"])
        parts.append(("ansigray", hdr + "\n"))
        parts.append(("ansigray", "─" * (name_w + sum(col_w.values())) + "\n"))

        providers = self._providers_sorted()
        if not providers:
            parts.append(("ansigray", "  No usage data for this period\n"))
        else:
            for i, (pname, pstats) in enumerate(providers):
                is_sel = i == self._selected_idx
                is_exp = pname in self._expanded
                arrow = "▾" if is_exp else "▸"
                style = "bold ansicyan" if is_sel else ""

                row = f"{arrow} {_pad_right(pname, name_w - 2)}"
                row += _pad_left(_fmt_num(len(pstats.sessions)), col_w["sessions"])
                row += _pad_left(_fmt_num(pstats.messages), col_w["msgs"])
                row += _pad_left(_fmt_cost(pstats.cost), col_w["cost"])
                row += _pad_left(_fmt_tokens(pstats.tokens), col_w["tokens"])
                in_tokens = pstats.input_other + pstats.input_cache_creation
                row += _pad_left(_fmt_tokens(in_tokens), col_w["in"])
                row += _pad_left(_fmt_tokens(pstats.output), col_w["out"])
                parts.append((style, row + "\n"))

                if is_exp:
                    for mname, mstats in sorted(
                        pstats.models.items(), key=lambda kv: kv[1].cost, reverse=True
                    ):
                        mrow = "    " + _pad_right(mname, name_w - 4)
                        mrow += _pad_left(_fmt_num(len(mstats.sessions)), col_w["sessions"])
                        mrow += _pad_left(_fmt_num(mstats.messages), col_w["msgs"])
                        mrow += _pad_left(_fmt_cost(mstats.cost), col_w["cost"])
                        mrow += _pad_left(_fmt_tokens(mstats.tokens), col_w["tokens"])
                        m_in = mstats.input_other + mstats.input_cache_creation
                        mrow += _pad_left(_fmt_tokens(m_in), col_w["in"])
                        mrow += _pad_left(_fmt_tokens(mstats.output), col_w["out"])
                        parts.append(("ansigray", mrow + "\n"))

        # Totals
        parts.append(("ansigray", "─" * (name_w + sum(col_w.values())) + "\n"))
        tot = _pad_right("Total", name_w)
        tot += _pad_left(_fmt_num(cur.total_sessions), col_w["sessions"])
        tot += _pad_left(_fmt_num(cur.total_messages), col_w["msgs"])
        tot += _pad_left(_fmt_cost(cur.total_cost), col_w["cost"])
        parts.append(("bold", tot + "\n"))
        parts.append(("", "\n"))

    def _render_insights(
        self, parts: StyleAndTextTuples, line: _LineFn, txt: _LineFn, cur: PeriodStats
    ) -> None:
        insights = self._data.insights.get(self._tab)
        if cur.total_messages == 0:
            parts.append(("ansigray", "  No usage recorded for this period.\n\n"))
            return
        if cur.total_cost == 0 or insights is None or not insights.insights:
            parts.append(
                ("ansigray", "  No cost data available (models not yet priced or no sessions).\n\n")
            )
            return
        label = _TAB_LABELS[self._tab]
        parts.append(("ansigray", f"  {label} · weighted by cost (USD)\n\n"))
        for insight in insights.insights:
            pct_fmt = ".0f" if insight.percent >= 10 else ".1f"
            pct_str = f"{insight.percent:{pct_fmt}}%"
            parts.append(("bold ansicyan", f"  {pct_str} "))
            parts.append(("", insight.headline + "\n"))
            parts.append(("ansigray", f"     {insight.advice}\n\n"))

    def _build_app(self) -> Application[None]:
        kb = KeyBindings()

        @kb.add("q")
        @kb.add("escape")
        def _quit(event: KeyPressEvent) -> None:
            event.app.exit()

        @kb.add("tab")
        @kb.add("right")
        def _next_tab(event: KeyPressEvent) -> None:
            self._tab_idx = (self._tab_idx + 1) % len(_TAB_KEYS)
            self._selected_idx = 0
            event.app.invalidate()

        @kb.add("s-tab")
        @kb.add("left")
        def _prev_tab(event: KeyPressEvent) -> None:
            self._tab_idx = (self._tab_idx - 1) % len(_TAB_KEYS)
            self._selected_idx = 0
            event.app.invalidate()

        @kb.add("up")
        def _up(event: KeyPressEvent) -> None:
            if self._view == "table" and self._selected_idx > 0:
                self._selected_idx -= 1
                event.app.invalidate()

        @kb.add("down")
        def _down(event: KeyPressEvent) -> None:
            if self._view == "table":
                providers = self._providers_sorted()
                if self._selected_idx < len(providers) - 1:
                    self._selected_idx += 1
                    event.app.invalidate()

        @kb.add("enter")
        @kb.add("space")
        def _toggle_expand(event: KeyPressEvent) -> None:
            if self._view == "table":
                providers = self._providers_sorted()
                if providers and self._selected_idx < len(providers):
                    pname = providers[self._selected_idx][0]
                    if pname in self._expanded:
                        self._expanded.discard(pname)
                    else:
                        self._expanded.add(pname)
                    event.app.invalidate()

        @kb.add("v")
        def _toggle_view(event: KeyPressEvent) -> None:
            self._view = "insights" if self._view == "table" else "table"
            event.app.invalidate()

        # Mark handlers as used
        _ = (_quit, _next_tab, _prev_tab, _up, _down, _toggle_expand, _toggle_view)

        ctrl = FormattedTextControl(self._render, focusable=False)
        layout = Layout(HSplit([Window(content=ctrl)]))

        return Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            style=Style.from_dict(
                {
                    "": "bg:#1e1e1e fg:#d4d4d4",
                }
            ),
            mouse_support=False,
        )

    async def run(self) -> None:
        await self._app.run_async()


# ---------------------------------------------------------------------------
# Slash command
# ---------------------------------------------------------------------------


@registry.command(name="stats", aliases=["history"])
async def stats(app: Shell, args: str) -> None:
    """Show usage statistics dashboard (tokens and cost by provider/model)."""
    await _refresh_catalog()
    from pythinker_code.ui.theme import get_tui_tokens as _get_tui_tokens

    _t = _get_tui_tokens()

    try:
        data = await asyncio.to_thread(load_all_stats)
    except Exception as e:
        from pythinker_code.utils.logging import logger as _logger

        _logger.exception("Failed to load stats: {error}", error=e)
        console.print(f"[{_t.error}]Failed to load stats: {e}[/]")
        return

    if data.periods["all_time"].total_messages == 0:
        console.print(f"[{_t.warning}]No usage data found in ~/.pythinker/sessions/[/]")
        return

    dashboard = StatsApp(data)
    await dashboard.run()
