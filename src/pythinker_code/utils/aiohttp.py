from __future__ import annotations

import ssl
from collections.abc import Callable
from typing import Any

import aiohttp
import certifi

_ssl_context = ssl.create_default_context(cafile=certifi.where())

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(
    total=120,
    sock_read=60,
    sock_connect=15,
)


class _SSRFConnector(aiohttp.TCPConnector):
    """TCPConnector that re-checks every resolved record against an SSRF deny
    rule, so validation and the actual connection share one DNS resolution.
    """

    def __init__(self, *args: Any, ip_blocked: Callable[[str], bool], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # pyright: ignore[reportUnknownMemberType]
        self._ip_blocked = ip_blocked

    async def _resolve_host(self, host: str, port: int, traces: Any = None) -> list[Any]:
        hosts = await super()._resolve_host(host, port, traces=traces)
        for h in hosts:
            if self._ip_blocked(h["host"]):
                raise aiohttp.ClientConnectionError(
                    f"Blocked connection to non-public address {h['host']}"
                )
        return hosts


def new_client_session(
    *,
    timeout: aiohttp.ClientTimeout | None = None,
    ip_blocked: Callable[[str], bool] | None = None,
) -> aiohttp.ClientSession:
    if ip_blocked is not None:
        connector = _SSRFConnector(ssl=_ssl_context, ip_blocked=ip_blocked)
    else:
        connector = aiohttp.TCPConnector(ssl=_ssl_context)
    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout or _DEFAULT_TIMEOUT,
    )
