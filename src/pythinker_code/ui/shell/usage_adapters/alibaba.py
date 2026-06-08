"""Usage adapter for Alibaba DashScope."""

from __future__ import annotations

from urllib.parse import urlparse
from typing import TYPE_CHECKING

import aiohttp

from pythinker_code.auth import ALIBABA_PLATFORM_ID
from pythinker_code.auth.alibaba import ALIBABA_BASE_URL
from pythinker_code.ui.shell.usage_adapters.base import UsageReport, UsageRow
from pythinker_code.usage_ratelimit_cache import get_cache
from pythinker_code.utils.aiohttp import new_client_session

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
    rows: list[UsageRow] = []
    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return []

    # Flat shape: {token_quota: N, token_used: N}
    total = payload.get("token_quota") or payload.get("total_quota")
    used = payload.get("token_used") or payload.get("total_used")
    if isinstance(total, (int, float)) and isinstance(used, (int, float)):
        rows.append(
            UsageRow(label="Token quota", used=int(used), limit=int(total), unit="tokens")
        )

    # List shape: {quota_list: [{quota_name, total_quota, total_used}]}
    quota_list = payload.get("quota_list")
    if isinstance(quota_list, list):
        for item in quota_list:
            if not isinstance(item, dict):
                continue
            name = item.get("quota_name") or item.get("quota_type") or "Quota"
            t = item.get("total_quota")
            u = item.get("total_used")
            if isinstance(t, (int, float)) and isinstance(u, (int, float)):
                rows.append(
                    UsageRow(
                        label=str(name).title(), used=int(u), limit=int(t), unit="tokens"
                    )
                )

    return rows


class AlibabaAdapter:
    platform_id = ALIBABA_PLATFORM_ID
    provider_label = "Alibaba DashScope"
    requires_admin_key = False

    async def fetch(self, provider: "LLMProvider", oauth_mgr: "OAuthManager") -> UsageReport:
        api_key = provider.api_key.get_secret_value()
        base_url = provider.base_url or ALIBABA_BASE_URL
        quota_url = _quota_url(base_url)
        provider_key = f"managed:{ALIBABA_PLATFORM_ID}"

        quota_rows: list[UsageRow] = []
        notes: list[str] = []

        try:
            async with new_client_session(timeout=_TIMEOUT) as session:
                async with session.get(
                    quota_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        quota_rows = _parse_quota_response(data)
                        if not quota_rows:
                            notes.append(
                                "DashScope quota API returned an unrecognised response shape."
                            )
                    elif resp.status in (401, 403):
                        notes.append(
                            "DashScope quota API: authorization failed — quota data unavailable."
                        )
                    elif resp.status == 404:
                        pass  # Quota endpoint not available for this key type; silent
                    else:
                        notes.append(f"DashScope quota API returned HTTP {resp.status}.")
        except (aiohttp.ClientError, TimeoutError):
            pass  # Network error — fall through to rate-limit data

        # Read rate-limit headers captured from the most recent completion response
        rl_rows: list[UsageRow] = []
        snap = get_cache().snapshot(provider_key)
        if snap is not None:
            req_lim = snap.requests_limit
            req_rem = snap.requests_remaining
            tok_lim = snap.tokens_limit
            tok_rem = snap.tokens_remaining
            if req_lim is not None and req_rem is not None:
                rl_rows.append(
                    UsageRow(label="Requests", used=req_rem, limit=req_lim, unit="requests")
                )
            if tok_lim is not None and tok_rem is not None:
                rl_rows.append(
                    UsageRow(label="Tokens", used=tok_rem, limit=tok_lim, unit="tokens")
                )

        all_rows = quota_rows + rl_rows
        if not all_rows and not notes:
            notes.append(
                "DashScope does not expose real-time quota in API responses. "
                "View your usage at console.aliyun.com → Model Studio → Quota."
            )

        summary = all_rows[0] if all_rows else None
        return UsageReport(
            provider_label=self.provider_label,
            summary=summary,
            limits=all_rows[1:],
            notes=notes,
            unit_hint="tokens",
        )
