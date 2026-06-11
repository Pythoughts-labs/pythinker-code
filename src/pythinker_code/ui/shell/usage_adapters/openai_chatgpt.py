from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import aiohttp

from pythinker_code.auth import OPENAI_CHATGPT_PLATFORM_ID
from pythinker_code.ui.shell.usage_adapters.base import UsageReport, UsageRow
from pythinker_code.utils.aiohttp import new_client_session
from pythinker_code.utils.datetime import format_duration

if TYPE_CHECKING:
    from pythinker_code.auth.oauth import OAuthManager
    from pythinker_code.config import LLMProvider

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class OpenAIChatGPTAdapter:
    platform_id = OPENAI_CHATGPT_PLATFORM_ID
    requires_admin_key = False
    provider_label = "ChatGPT Codex"

    async def fetch(
        self,
        provider: LLMProvider,
        oauth_mgr: OAuthManager,
    ) -> UsageReport:
        if provider.oauth is None:
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=["Codex usage requires an OAuth login (`/login openai-chatgpt`)."],
                unit_hint="quota",
            )

        access_token = oauth_mgr.resolve_api_key(provider.api_key, provider.oauth)
        account_id = oauth_mgr.get_chatgpt_account_id(provider.oauth)
        if not account_id:
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=["Missing ChatGPT account_id in OAuth token."],
                unit_hint="quota",
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "ChatGPT-Account-Id": account_id,
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
            "User-Agent": "pythinker-code",
        }
        try:
            async with (
                new_client_session() as session,
                session.get(
                    CODEX_USAGE_URL,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                    raise_for_status=True,
                ) as resp,
            ):
                payload = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as e:
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=[f"Codex usage fetch failed: HTTP {e.status}"],
                unit_hint="quota",
            )
        except (aiohttp.ClientError, TimeoutError) as e:
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=[f"Codex usage fetch failed: {e}"],
                unit_hint="quota",
            )

        return parse_codex_usage_payload(payload)


def parse_codex_usage_payload(payload: object) -> UsageReport:
    if not isinstance(payload, Mapping):
        return UsageReport(
            OpenAIChatGPTAdapter.provider_label,
            None,
            [],
            notes=["Unexpected Codex response shape."],
            unit_hint="quota",
        )

    payload_map = cast(Mapping[str, Any], payload)
    rate_limit = payload_map.get("rate_limit") or payload_map.get("rate_limits")
    if not isinstance(rate_limit, Mapping):
        return UsageReport(
            OpenAIChatGPTAdapter.provider_label,
            None,
            [],
            notes=["No rate_limit data in Codex response."],
            unit_hint="quota",
        )

    rate_map = cast(Mapping[str, Any], rate_limit)
    notes: list[str] = []

    # `allowed` / `limit_reached` are top-level booleans on the current shape.
    if rate_map.get("limit_reached") is True:
        notes.append("Rate limit reached.")
    elif rate_map.get("allowed") is False:
        notes.append("Requests currently not allowed by the rate limiter.")

    # The ChatGPT wham/usage response carries up to two windows under
    # `primary_window` / `secondary_window` (older releases used `five_hour` /
    # `weekly`). Accounts on some plans only return one of them — and the slot
    # name is NOT a reliable indicator of which window is shorter (e.g. free
    # accounts can put a 7-day window in `primary_window`). Classify by
    # `limit_window_seconds` instead, then sort smallest first.
    rows: list[tuple[int, UsageRow]] = []
    for slot in ("primary_window", "secondary_window", "five_hour", "weekly"):
        window = rate_map.get(slot)
        if not isinstance(window, Mapping):
            continue
        if pair := _row_for_codex_window(cast(Mapping[str, Any], window)):
            rows.append(pair)

    rows.sort(key=lambda item: item[0] or 10**12)
    summary = rows[0][1] if rows else None
    limits = [row for _, row in rows[1:]]

    if summary is None and not limits:
        # Surface what we did see so a future rename is obvious.
        outer = ", ".join(sorted(rate_map.keys())) or "<empty>"
        inner_hint = ""
        for slot in ("primary_window", "secondary_window", "five_hour", "weekly"):
            window = rate_map.get(slot)
            if isinstance(window, Mapping):
                inner_keys = ", ".join(sorted(cast(Mapping[str, Any], window).keys()))
                inner_hint = f" Inner `{slot}` keys: {inner_keys}."
                break
        notes.append(
            f"Codex returned rate_limit with no recognized quota fields "
            f"(outer keys: {outer}).{inner_hint} "
            f"Adapter expects a window object with `used_percent` (or "
            f"`percent_left`) and `limit_window_seconds`."
        )

    return UsageReport(
        OpenAIChatGPTAdapter.provider_label,
        summary,
        limits,
        notes=notes,
        unit_hint="quota",
    )


def _row_for_codex_window(window: Mapping[str, Any]) -> tuple[int, UsageRow] | None:
    """Build a UsageRow from a single Codex rate-limit window object.

    Returns (window_seconds, row) so the caller can sort windows shortest-
    first. Handles both the current snake_case shape (`used_percent`,
    `limit_window_seconds`, `resets_at`) and the older shape (`percent_left`,
    `limit_window_seconds`, `reset_at`).
    """
    if "used_percent" in window:
        used_percent = window.get("used_percent")
        if not isinstance(used_percent, int | float):
            return None
        percent_left = max(0, 100 - int(used_percent))
    elif "percent_left" in window:
        raw_percent_left = window.get("percent_left")
        if not isinstance(raw_percent_left, int | float):
            return None
        percent_left = int(raw_percent_left)
    else:
        return None

    raw_window_seconds = window.get("limit_window_seconds")
    window_seconds = int(raw_window_seconds) if isinstance(raw_window_seconds, int | float) else 0

    return window_seconds, UsageRow(
        label=_label_for_codex_window(window_seconds),
        used=percent_left,
        limit=100,
        unit="%",
        reset_hint=_codex_reset_hint(window),
    )


def _label_for_codex_window(seconds: int) -> str:
    if seconds <= 0:
        return "Rate limit"
    if seconds <= 24 * 3600:
        hours = seconds / 3600
        return f"{hours:g}h window"
    days = seconds // 86400
    if 6 <= days <= 8:
        return "Weekly window"
    return f"{days}d window"


def _codex_reset_hint(win_map: Mapping[str, Any]) -> str | None:
    # The reset time arrives under `resets_at` or `reset_at`, and as a
    # unix-seconds timestamp (number or numeric string) or an ISO-8601 string.
    # Always humanize it ("resets in 2h 14m") rather than printing a raw value.
    for key in ("resets_at", "reset_at"):
        raw = win_map.get(key)
        if raw is None:
            continue
        dt = _coerce_reset_datetime(raw)
        if dt is not None:
            return _format_reset_delta(dt, win_map)
        if isinstance(raw, str) and raw.strip():
            return f"resets at {raw.strip()}"
    return None


def _coerce_reset_datetime(raw: object) -> datetime | None:
    """Parse a reset timestamp that may be unix seconds (number or numeric
    string) or an ISO-8601 string."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return None
        try:  # numeric string -> unix seconds
            return datetime.fromtimestamp(float(candidate), tz=UTC)
        except (OverflowError, OSError, ValueError):
            pass
        try:  # ISO-8601
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    return None


def _format_reset_delta(dt: datetime, win_map: Mapping[str, Any]) -> str:
    delta = dt - datetime.now(UTC)
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        window_seconds = win_map.get("limit_window_seconds")
        if isinstance(window_seconds, int | float) and window_seconds > 0:
            step = int(window_seconds)
            if step <= 0:
                return "reset"
            seconds += step * (1 + (-seconds) // step)
    if seconds <= 0:
        return "reset"
    return f"resets in {format_duration(seconds)}"
