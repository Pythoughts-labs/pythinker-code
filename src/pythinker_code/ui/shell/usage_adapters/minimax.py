"""MiniMax Token-Plan usage adapter.

Endpoint sourced from the official docs (verified 2026-05-06 via
context7 + tavily against `platform.minimax.io/docs/token-plan/faq`):

    GET https://www.minimax.io/v1/token_plan/remains
    Authorization: Bearer <API Key>
    Content-Type: application/json

Response shape verified 2026-06-15 against a live `sk-cp-*` key. `model_remains`
is an array of per-*category* entries (e.g. `general`, `video` — not per-model),
each carrying a 5h interval window and a weekly window:

    {
      "model_name": "general",                 # resource CATEGORY, not a model id
      "remains_time": 13224928,                # ms until 5h-interval reset
      "current_interval_total_count": 0,       # 0 on percent-metered plans
      "current_interval_usage_count": 0,       # (REMAINING count when non-zero)
      "current_interval_remaining_percent": 100,
      "weekly_remains_time": 27624928,         # ms until weekly reset
      "current_weekly_total_count": 0,
      "current_weekly_usage_count": 0,
      "current_weekly_remaining_percent": 82,  # -> 18% used this week
      "current_interval_status": 1, "current_weekly_status": 1
    }

Two footguns this parser handles: reset times are **milliseconds** (not seconds),
and current plans meter by **percentage** with the count fields left at 0 — so we
prefer `*_remaining_percent` and only fall back to counts when a real allowance
(`*_total_count > 0`) is present. The unrelated portal endpoint
`https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains` requires
browser cookies (issue #88) — we don't use it.

For pay-as-you-go MiniMax keys (non-`sk-cp-*`) there's no Token-Plan to
query, so we short-circuit and let the Phase-5 rate-limit cache fill in
live limits from chat-completion headers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import aiohttp

from pythinker_code.auth import MINIMAX_PLATFORM_ID
from pythinker_code.ui.shell.usage_adapters.base import UsageReport, UsageRow, used_from_remaining
from pythinker_code.utils.aiohttp import new_client_session

if TYPE_CHECKING:
    from pythinker_code.auth.oauth import OAuthManager
    from pythinker_code.config import LLMProvider


# Documented at https://platform.minimax.io/docs/token-plan/faq (verified
# 2026-05-06): the API-key-authenticated Token-Plan usage endpoint.
MINIMAX_TOKEN_PLAN_URL = "https://www.minimax.io/v1/token_plan/remains"
_TOKEN_PLAN_KEY_PREFIX = "sk-cp-"


class MiniMaxAdapter:
    platform_id = MINIMAX_PLATFORM_ID
    requires_admin_key = False
    provider_label = "MiniMax"

    async def fetch(
        self,
        provider: LLMProvider,
        oauth_mgr: OAuthManager,
    ) -> UsageReport:
        api_key = oauth_mgr.resolve_api_key(provider.api_key, provider.oauth)

        # Pay-as-you-go MiniMax API keys (non-`sk-cp-…`) don't have a
        # token-plan to query at all; short-circuit instead of probing.
        if not api_key.startswith(_TOKEN_PLAN_KEY_PREFIX):
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=[
                    "Pay-as-you-go MiniMax keys don't expose a usage endpoint. "
                    "Live rate-limit headers will appear here after sending a "
                    "chat message."
                ],
                unit_hint="quota",
            )

        try:
            async with (
                new_client_session() as session,
                session.get(
                    MINIMAX_TOKEN_PLAN_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
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
                notes=[f"MiniMax token-plan probe failed: HTTP {e.status}"],
                unit_hint="quota",
            )
        except (TimeoutError, aiohttp.ClientError) as e:
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=[f"MiniMax token-plan probe failed: {e}"],
                unit_hint="quota",
            )

        if not isinstance(payload, Mapping):
            return UsageReport(
                self.provider_label,
                None,
                [],
                notes=["Unexpected MiniMax response shape."],
                unit_hint="quota",
            )

        return parse_minimax_payload(cast(Mapping[str, Any], payload))


def parse_minimax_payload(payload: Mapping[str, Any]) -> UsageReport:
    """Parse the `/v1/token_plan/remains` response (schema verified 2026-06-15).

    `model_remains` is an array of per-category entries. For each entry we emit a
    5h-interval row and a weekly row. Usage is taken from `*_remaining_percent`
    (percent-metered plans leave the count fields at 0); when a real count
    allowance is present (`*_total_count > 0`) we use it instead, treating
    `*_usage_count` as the *remaining* count (a documented MiniMax footgun). Reset
    times (`remains_time`, `weekly_remains_time`) are milliseconds.
    """
    notes: list[str] = []

    # MiniMax's universal envelope: 0 = success, anything else is an error.
    base_resp = payload.get("base_resp")
    if isinstance(base_resp, Mapping):
        base = cast(Mapping[str, Any], base_resp)
        status_code = base.get("status_code")
        if status_code not in (None, 0):
            msg = base.get("status_msg") or "unknown error"
            return UsageReport(
                MiniMaxAdapter.provider_label,
                None,
                [],
                notes=[f"MiniMax responded {status_code}: {msg}"],
                unit_hint="quota",
            )

    summary: UsageRow | None = None
    limits: list[UsageRow] = []

    model_remains = payload.get("model_remains")
    if isinstance(model_remains, list):
        for entry in cast(list[Any], model_remains):
            if not isinstance(entry, Mapping):
                continue
            entry_map = cast(Mapping[str, Any], entry)
            for row in _rows_from_minimax_model_entry(entry_map):
                # First row produced (the highest-priority model's 5h window)
                # becomes the panel summary; the rest go into limits.
                if summary is None:
                    summary = row
                else:
                    limits.append(row)

    if summary is None and not limits:
        outer = ", ".join(sorted(payload.keys())) or "<empty>"
        notes.append(
            f"MiniMax returned no recognizable token-plan fields "
            f"(keys: {outer}). Live rate-limit headers will fill this "
            f"panel after sending a chat message."
        )

    return UsageReport(
        provider_label=MiniMaxAdapter.provider_label,
        summary=summary,
        limits=limits,
        notes=notes,
        unit_hint="quota",
    )


def _rows_from_minimax_model_entry(entry: Mapping[str, Any]) -> list[UsageRow]:
    """Yield the 5h-window and weekly-window UsageRows for one category entry.

    Returns an empty list if no recognized window fields are present.
    """
    category = str(entry.get("model_name") or entry.get("model") or "model")
    rows: list[UsageRow] = []

    interval = _window_row(
        label=f"{category} 5h",
        total=entry.get("current_interval_total_count"),
        remaining_count=entry.get("current_interval_usage_count"),
        remaining_percent=entry.get("current_interval_remaining_percent"),
        remains_millis=entry.get("remains_time"),
    )
    if interval is not None:
        rows.append(interval)

    weekly = _window_row(
        label=f"{category} weekly",
        total=entry.get("current_weekly_total_count"),
        remaining_count=entry.get("current_weekly_usage_count"),
        remaining_percent=entry.get("current_weekly_remaining_percent"),
        remains_millis=entry.get("weekly_remains_time"),
    )
    if weekly is not None:
        rows.append(weekly)

    return rows


def _window_row(
    *,
    label: str,
    total: Any,
    remaining_count: Any,
    remaining_percent: Any,
    remains_millis: Any,
) -> UsageRow | None:
    """Build one window's row, preferring a real count allowance over percent."""
    reset_hint = _millis_to_reset_hint(_to_int(remains_millis))

    total_i = _to_int(total)
    remaining_i = _to_int(remaining_count)
    if total_i is not None and total_i > 0 and remaining_i is not None:
        # `*_usage_count` is the REMAINING count, not the used count.
        return UsageRow(
            label=label,
            used=used_from_remaining(total_i, remaining_i),
            limit=total_i,
            unit="requests",
            reset_hint=reset_hint,
        )

    # Percent-metered plans leave the counts at 0; use the remaining percentage.
    pct = _to_int(remaining_percent)
    if pct is not None:
        pct = max(0, min(100, pct))
        return UsageRow(
            label=label,
            used=100 - pct,
            limit=100,
            unit="%",
            reset_hint=reset_hint,
        )

    return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _seconds_to_reset_hint(seconds: int | None) -> str | None:
    from pythinker_code.utils.datetime import format_duration

    if seconds is None or seconds <= 0:
        return None
    return f"resets in {format_duration(seconds)}"


def _millis_to_reset_hint(millis: int | None) -> str | None:
    """MiniMax reports `remains_time`/`weekly_remains_time` in milliseconds."""
    if millis is None or millis <= 0:
        return None
    return _seconds_to_reset_hint(millis // 1000)
