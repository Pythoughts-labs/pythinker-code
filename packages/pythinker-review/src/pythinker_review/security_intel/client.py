"""Bounded HTTP client for public vulnerability-intelligence APIs.

The client is deliberately narrow: it validates hosts, caps response bodies, redacts sensitive data
from errors, and never targets arbitrary project URLs.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from pythinker_review.security_intel.validators import sanitize_url_for_log, validate_intel_url

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class IntelClientError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disable implicit redirects so host allowlisting cannot be bypassed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(frozen=True, slots=True)
class IntelResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class IntelHttpClient:
    def __init__(
        self,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self.timeout_s = timeout_s
        self.max_response_bytes = max_response_bytes
        self._opener = urllib.request.build_opener(_NoRedirectHandler)

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = await self.get(url, params=params, headers=headers)
        return response.json()

    async def post_json(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = await self.post(url, payload=payload, headers=headers)
        return response.json()

    async def get_text(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        response = await self.get(url, params=params, headers=headers)
        return response.text()

    async def get(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> IntelResponse:
        return await asyncio.to_thread(self._request, "GET", url, params, None, headers)

    async def post(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> IntelResponse:
        return await asyncio.to_thread(self._request, "POST", url, None, payload, headers)

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, object] | None,
        payload: dict[str, object] | None,
        headers: dict[str, str] | None,
    ) -> IntelResponse:
        if params:
            query = urllib.parse.urlencode(params)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"
        validate_intel_url(url)
        body: bytes | None = None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        safe_url = sanitize_url_for_log(url)
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                content_length = resp.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > self.max_response_bytes:
                            raise IntelClientError("response too large (Content-Length)")
                    except ValueError:
                        raise IntelClientError("invalid Content-Length header")
                data = resp.read(self.max_response_bytes + 1)
                if len(data) > self.max_response_bytes:
                    raise IntelClientError("response too large (actual body)")
                return IntelResponse(
                    status=resp.status,
                    body=data,
                    headers={key.lower(): value for key, value in resp.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            raise IntelClientError(f"HTTP {exc.code} for {safe_url}") from exc
        except urllib.error.URLError as exc:
            raise IntelClientError(f"network error for {safe_url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise IntelClientError(f"timeout for {safe_url}") from exc
