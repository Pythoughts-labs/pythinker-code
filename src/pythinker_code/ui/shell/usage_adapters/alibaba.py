"""Usage adapter for Alibaba DashScope."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

import aiohttp

from pythinker_code.auth import ALIBABA_PLATFORM_ID
from pythinker_code.auth.alibaba import ALIBABA_BASE_URL
from pythinker_code.ui.shell.stats_collector import load_all_stats as _load_all_stats
from pythinker_code.ui.shell.usage_adapters.base import UsageReport, UsageRow
from pythinker_code.usage_ratelimit_cache import get_cache
from pythinker_code.utils.aiohttp import new_client_session
from pythinker_code.utils.logging import logger

if TYPE_CHECKING:
    from pythinker_code.auth.oauth import OAuthManager
    from pythinker_code.config import LLMProvider

_QUOTA_PATH = "/api/v1/quotas"
_TIMEOUT = aiohttp.ClientTimeout(total=8, sock_connect=5)

# DashScope quota API lives on a separate host from the compatible-mode endpoint.
# The "dashscope-us" host is the completion endpoint; quota is on "dashscope-intl".
_DASHSCOPE_HOST_REMAP: dict[str, str] = {
    "dashscope-us.aliyuncs.com": "dashscope-intl.aliyuncs.com",
}


def _quota_url(base_url: str) -> str:
    """Derive the quota API URL from the configured base URL.

    The OpenAI-compatible completion host and the quota API host differ for the
    international (US) region — remap known mismatches before constructing the URL.
    """
    parsed = urlparse(base_url)
    host = _DASHSCOPE_HOST_REMAP.get(parsed.netloc, parsed.netloc)
    return f"{parsed.scheme}://{host}{_QUOTA_PATH}"


def _parse_quota_response(data: object) -> list[UsageRow]:
    """Parse DashScope /api/v1/quotas response into UsageRow list.

    Handles both flat {token_quota, token_used} and {quota_list: [...]} shapes.
    Returns [] if the response has an unrecognised shape.
    """
    if not isinstance(data, dict):
        return []
    data_map = cast(dict[str, Any], data)
    rows: list[UsageRow] = []
    payload = data_map.get("data", data_map)
    if not isinstance(payload, dict):
        return []
    payload_map = cast(dict[str, Any], payload)

    # Flat shape: {token_quota: N, token_used: N}
    total = (
        payload_map["token_quota"]
        if "token_quota" in payload_map
        else payload_map.get("total_quota")
    )
    used = (
        payload_map["token_used"] if "token_used" in payload_map else payload_map.get("total_used")
    )
    if isinstance(total, (int, float)) and isinstance(used, (int, float)):
        rows.append(UsageRow(label="Token quota", used=int(used), limit=int(total), unit="tokens"))

    # List shape: {quota_list: [{quota_name, total_quota, total_used}]}
    quota_list = payload_map.get("quota_list")
    if isinstance(quota_list, list):
        for item in cast(list[Any], quota_list):
            if not isinstance(item, dict):
                continue
            item_map = cast(dict[str, Any], item)
            name = item_map.get("quota_name") or item_map.get("quota_type") or "Quota"
            t = item_map.get("total_quota")
            u = item_map.get("total_used")
            if isinstance(t, (int, float)) and isinstance(u, (int, float)):
                rows.append(
                    UsageRow(label=str(name).title(), used=int(u), limit=int(t), unit="tokens")
                )

    return rows


class AlibabaAdapter:
    platform_id = ALIBABA_PLATFORM_ID
    provider_label = "Alibaba DashScope"
    requires_admin_key = False

    async def fetch(self, provider: LLMProvider, oauth_mgr: OAuthManager) -> UsageReport:
        api_key = provider.api_key.get_secret_value()
        base_url = provider.base_url or ALIBABA_BASE_URL
        provider_key = f"managed:{ALIBABA_PLATFORM_ID}"

        # --- Local token stats (primary source, always available) ---
        local_rows: list[UsageRow] = []
        try:
            all_stats = await asyncio.to_thread(_load_all_stats)
            for period_name, label in (("today", "Today"), ("all_time", "All time")):
                period = all_stats.periods.get(period_name)
                if period is None:
                    continue
                prov = period.providers.get(provider_key)
                if prov is None or prov.messages == 0:
                    continue
                local_rows.append(
                    UsageRow(
                        label=label,
                        used=prov.tokens,
                        limit=0,
                        unit="tokens",
                        reset_hint=(
                            f"↑{prov.input_other:,} in  ↓{prov.output:,} out  ${prov.cost:.4f}"
                        ),
                    )
                )
        except Exception as e:
            logger.debug("local usage stats unavailable: {error}", error=e, exc_info=True)

        # --- DashScope quota API (best-effort; logs + notes on failure) ---
        quota_rows: list[UsageRow] = []
        notes: list[str] = []
        try:
            async with (
                new_client_session(timeout=_TIMEOUT) as session,
                session.get(
                    _quota_url(base_url),
                    headers={"Authorization": f"Bearer {api_key}"},
                ) as resp,
            ):
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    quota_rows = _parse_quota_response(data)
                elif resp.status in (401, 403):
                    notes.append(
                        "DashScope quota API: authorization failed — quota data unavailable."
                    )
        except (aiohttp.ClientError, TimeoutError) as e:
            logger.debug("DashScope quota API request failed: {error}", error=e, exc_info=True)
            notes.append("DashScope quota API unavailable right now — retry in a moment.")

        # --- Rate-limit headers from last response (if DashScope ever sends them) ---
        rl_rows: list[UsageRow] = []
        snap = get_cache().snapshot(provider_key)
        if snap is not None:
            if snap.requests_limit is not None and snap.requests_remaining is not None:
                rl_rows.append(
                    UsageRow(
                        label="Requests",
                        used=min(
                            snap.requests_limit,
                            max(0, snap.requests_limit - snap.requests_remaining),
                        ),
                        limit=snap.requests_limit,
                        unit="requests",
                    )
                )
            if snap.tokens_limit is not None and snap.tokens_remaining is not None:
                rl_rows.append(
                    UsageRow(
                        label="Tokens",
                        used=min(
                            snap.tokens_limit,
                            max(0, snap.tokens_limit - snap.tokens_remaining),
                        ),
                        limit=snap.tokens_limit,
                        unit="tokens",
                    )
                )

        all_rows = local_rows + quota_rows + rl_rows
        if not all_rows and not notes:
            notes.append("No usage recorded yet. Start a conversation to see token counts here.")

        summary = all_rows[0] if all_rows else None
        return UsageReport(
            provider_label=self.provider_label,
            summary=summary,
            limits=all_rows[1:],
            notes=notes,
            unit_hint="tokens",
        )
