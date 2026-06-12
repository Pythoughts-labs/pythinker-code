# ruff: noqa

"""Tests for WebFetch tool."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

import pytest
import pytest_asyncio
from aiohttp import web
from inline_snapshot import snapshot
from pythinker_core.tooling import ToolReturnValue

from pythinker_code.tools.web import fetch as fetch_module
from pythinker_code.tools.web.fetch import FetchURL, Params, _validate_fetch_url

from tests.tools._untrusted import unwrap_untrusted


@pytest.fixture(autouse=True)
def _bypass_ssrf_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fetch tool blocks loopback / private IPs as SSRF mitigation, but
    every test in this module either talks to a localhost mock server or
    exercises malformed-URL handling that pre-dates the validator. Disable both
    the up-front URL validator and the connector-level IP guard for these unit
    tests; production callers still get the protection.
    """
    monkeypatch.setattr(fetch_module, "_validate_fetch_url", lambda _url, _allowed=None: None)
    monkeypatch.setattr(fetch_module, "_ip_is_blocked", lambda _address: False)


class MockServerFactory(Protocol):
    async def __call__(
        self,
        response_body: str,
        *,
        content_type: str = "text/html",
        status: int = 200,
    ) -> str: ...


@pytest_asyncio.fixture
async def mock_http_server() -> AsyncIterator[MockServerFactory]:
    """Provide a temporary HTTP server factory that returns static content."""

    runners: list[web.AppRunner] = []

    async def start_server(
        response_body: str,
        *,
        content_type: str = "text/html",
        status: int = 200,
    ) -> str:
        async def handler(request: web.Request) -> web.Response:  # noqa: ARG001
            ct_part, sep, charset_part = content_type.partition(";")
            charset_value: str | None = None
            if sep:
                _, _, charset_value = charset_part.partition("=")
                charset_value = charset_value.strip() or None

            content_type_value = ct_part.strip() or None
            return web.Response(
                text=response_body,
                status=status,
                content_type=content_type_value,
                charset=charset_value,
            )

        app = web.Application()
        app.router.add_get("/", handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="127.0.0.1", port=0)
        await site.start()

        sockets = site._server.sockets  # type: ignore[attr-defined]
        assert sockets, "Server failed to bind to a port."
        port = sockets[0].getsockname()[1]

        runners.append(runner)
        return f"http://127.0.0.1:{port}"

    try:
        yield start_server
    finally:
        for runner in runners:
            await runner.cleanup()


async def test_fetch_url_basic_functionality(
    fetch_url_tool: FetchURL,
    mock_http_server: MockServerFactory,
) -> None:
    """Test basic WebFetch functionality with HTML content extraction."""
    # Use a mocked HTML page to test trafilatura extraction instead of hitting
    # a real external URL.  Real pages change over time and cause flaky failures.
    html_page = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Sample Bug Report</title>
    <meta name="author" content="TestAuthor">
    <meta name="description" content="The default value should be lowercase.">
</head>
<body>
<article>
    <h1>Sample Bug Report</h1>
    <p>The default parameter value for <code>optimizer</code> should probably be
    <code>adamw</code> instead of <code>adamW</code> according to how
    <code>get_optimizer</code> is written.</p>
</article>
</body>
</html>"""
    server_url = await mock_http_server(html_page, content_type="text/html")
    result = await fetch_url_tool(Params(url=server_url))

    assert not result.is_error
    assert isinstance(result.output, str)
    assert (
        result.message == "The returned content is the main text content extracted from the page."
    )
    # Verify trafilatura extracted the meaningful text from the HTML
    assert "optimizer" in unwrap_untrusted(result.output)
    assert "adamw" in unwrap_untrusted(result.output)
    assert "adamW" in unwrap_untrusted(result.output)
    # Verify HTML tags were stripped (not returning raw HTML)
    assert "<article>" not in unwrap_untrusted(result.output)
    assert "<code>" not in unwrap_untrusted(result.output)
    # Verify metadata extraction (with_metadata=True)
    assert "title:" in unwrap_untrusted(result.output).lower()
    assert "description:" in unwrap_untrusted(result.output).lower()


async def test_fetch_url_invalid_url(fetch_url_tool: FetchURL) -> None:
    """Test fetching from an invalid URL."""
    result = await fetch_url_tool(
        Params(url="https://this-domain-definitely-does-not-exist-12345.com/")
    )

    # Should fail with network error
    assert result.is_error
    assert "Failed to fetch URL due to network error:" in result.message


async def test_fetch_url_404_url(fetch_url_tool: FetchURL) -> None:
    """Test fetching from a URL that returns 404."""
    result = await fetch_url_tool(
        Params(url="https://github.com/PythinkerAI/non-existing-repo/issues/1")
    )

    # Should fail with HTTP error
    assert result.is_error
    assert result.message == snapshot(
        "Failed to fetch URL. Status: 404. This may indicate the page is not accessible or the server is down."
    )


async def test_fetch_url_malformed_url(fetch_url_tool: FetchURL) -> None:
    """Test fetching from a malformed URL."""
    result = await fetch_url_tool(Params(url="not-a-valid-url"))

    # Should fail
    assert result.is_error
    assert result.message == snapshot(
        "Failed to fetch URL due to network error: not-a-valid-url. This may indicate the URL is invalid or the server is unreachable."
    )


async def test_fetch_url_empty_url(fetch_url_tool: FetchURL) -> None:
    """Test fetching with empty URL."""
    result = await fetch_url_tool(Params(url=""))

    # Should fail
    assert result.is_error
    assert result.message == snapshot(
        "Failed to fetch URL due to network error: . This may indicate the URL is invalid or the server is unreachable."
    )


async def test_fetch_url_javascript_driven_site(
    fetch_url_tool: FetchURL,
    mock_http_server: MockServerFactory,
) -> None:
    """Test fetching a JavaScript-driven page that trafilatura cannot extract."""
    html_page = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Client Rendered App</title></head>
<body>
    <div id="root"></div>
    <script>document.getElementById("root").textContent = "Rendered later";</script>
</body>
</html>"""
    server_url = await mock_http_server(html_page, content_type="text/html")
    result = await fetch_url_tool(Params(url=server_url))

    assert result.is_error
    assert "failed to extract meaningful content" in result.message.lower()


async def test_fetch_url_mocked_http_responses(
    fetch_url_tool: FetchURL,
    mock_http_server: MockServerFactory,
) -> None:
    """Test fetching multiple mocked HTTP responses."""

    async def mocked_fetch(resp: str, *, content_type: str = "text/html") -> ToolReturnValue:
        server_url = await mock_http_server(resp, content_type=content_type)
        return await fetch_url_tool(Params(url=f"{server_url}/"))

    # plain markdown. Real example: https://lucumr.pocoo.org/2025/10/17/code.md
    plain_markdown = """\
# Title

This is a markdown document.
"""
    result = await mocked_fetch(plain_markdown, content_type="text/markdown; charset=utf-8")
    assert not result.is_error
    assert unwrap_untrusted(result.output) == snapshot(plain_markdown)
    assert result.message == "The returned content is the full content of the page."

    # Real example: https://langfuse.com/docs.md
    complex_markdown = """\
---
title: Markdown Documentation
description: This is a sample markdown document with front-matter.
---

# Title

This is a markdown document.

<div><p>But has some html</p></div>
"""
    result = await mocked_fetch(
        complex_markdown,
        content_type="text/markdown; charset=utf-8",
    )
    assert not result.is_error
    assert unwrap_untrusted(result.output) == snapshot(complex_markdown)
    assert result.message == "The returned content is the full content of the page."


async def _start_redirect_server(routes) -> tuple[str, web.AppRunner]:
    """Start a server with the given (path, handler) routes; return base URL + runner."""
    app = web.Application()
    for path, handler in routes:
        app.router.add_get(path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
    return f"http://127.0.0.1:{port}", runner


async def test_fetch_url_follows_validated_redirect(fetch_url_tool: FetchURL) -> None:
    """A redirect to an allowed location is followed (validation is bypassed here)."""

    async def start(request: web.Request) -> web.Response:  # noqa: ARG001
        raise web.HTTPFound("/end")

    async def end(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(text="redirected body content", content_type="text/plain")

    base, runner = await _start_redirect_server([("/start", start), ("/end", end)])
    try:
        result = await fetch_url_tool(Params(url=f"{base}/start"))
    finally:
        await runner.cleanup()

    assert not result.is_error
    assert "redirected body content" in unwrap_untrusted(result.output)


async def test_fetch_url_blocks_redirect_to_disallowed_host(
    fetch_url_tool: FetchURL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A redirect whose target fails validation is blocked *before* being fetched."""

    # Override the module-wide bypass: allow the initial URL, block the redirect
    # target (any URL whose path is /blocked).
    monkeypatch.setattr(
        fetch_module,
        "_validate_fetch_url",
        lambda url, _allowed=None: ("host blocked" if "/blocked" in url else None),
    )

    blocked_hit = False

    async def start(request: web.Request) -> web.Response:  # noqa: ARG001
        raise web.HTTPFound("/blocked")

    async def blocked(request: web.Request) -> web.Response:  # noqa: ARG001
        nonlocal blocked_hit
        blocked_hit = True
        return web.Response(text="secret", content_type="text/plain")

    base, runner = await _start_redirect_server([("/start", start), ("/blocked", blocked)])
    try:
        result = await fetch_url_tool(Params(url=f"{base}/start"))
    finally:
        await runner.cleanup()

    assert result.is_error
    assert "redirect" in result.message.lower()
    # The security guarantee: the disallowed location was never contacted.
    assert blocked_hit is False


async def test_fetch_url_rejects_redirect_loop(fetch_url_tool: FetchURL) -> None:
    """A redirect loop terminates with a 'too many redirects' error."""

    async def loop(request: web.Request) -> web.Response:  # noqa: ARG001
        raise web.HTTPFound("/loop")

    base, runner = await _start_redirect_server([("/loop", loop)])
    try:
        result = await fetch_url_tool(Params(url=f"{base}/loop"))
    finally:
        await runner.cleanup()

    assert result.is_error
    assert "too many redirects" in result.message.lower()


async def test_fetch_url_with_service(runtime) -> None:
    """Test fetching using the pythinker_ai_fetch service."""
    from pythinker_code.config import Config, PythinkerAIFetchConfig, Services
    from pydantic import SecretStr

    # Setup mock service response
    expected_content = "# Service Content\n\nThis content was fetched via the service."

    async def service_handler(request: web.Request) -> web.Response:
        # Verify request
        assert request.method == "POST"
        assert request.headers.get("Authorization") == "Bearer test-key"
        assert request.headers.get("Accept") == "text/markdown"
        assert request.headers.get("X-Custom-Header") == "custom-value"

        data = await request.json()
        assert data["url"] == "https://example.com"

        return web.Response(text=expected_content)

    # Create a mock server for the service
    app = web.Application()
    app.router.add_post("/fetch", service_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
    service_url = f"http://127.0.0.1:{port}/fetch"

    try:
        # Configure tool with service
        config = Config(
            services=Services(
                pythinker_ai_fetch=PythinkerAIFetchConfig(
                    base_url=service_url,
                    api_key=SecretStr("test-key"),
                    custom_headers={"X-Custom-Header": "custom-value"},
                )
            )
        )

        fetch_tool = FetchURL(config=config, runtime=runtime)

        # Execute fetch with tool call context
        from pythinker_code.wire.types import ToolCall
        from pythinker_code.soul.toolset import current_tool_call

        token = current_tool_call.set(
            ToolCall(
                id="test-call-id", function=ToolCall.FunctionBody(name="FetchURL", arguments=None)
            )
        )
        try:
            result = await fetch_tool(Params(url="https://example.com"))
        finally:
            current_tool_call.reset(token)

        assert not result.is_error
        assert unwrap_untrusted(result.output) == expected_content
        assert result.message == snapshot(
            "The returned content is the main content extracted from the page."
        )

    finally:
        await runner.cleanup()


async def test_fetch_url_with_service_truncated_envelope_stays_closed(runtime) -> None:
    """Service-fetched content larger than the builder limit must keep a
    well-formed <untrusted_data> envelope: wrapping happens after truncation,
    so the closing tag can never be cut off."""
    from pydantic import SecretStr

    from pythinker_code.config import Config, PythinkerAIFetchConfig, Services
    from pythinker_code.tools.utils import DEFAULT_MAX_CHARS
    from pythinker_code.utils.trust import strip_untrusted_envelope

    big_content = "".join(f"line {i}: service filler text\n" for i in range(4000))
    assert len(big_content) > DEFAULT_MAX_CHARS

    async def service_handler(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(text=big_content)

    app = web.Application()
    app.router.add_post("/fetch", service_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]

    try:
        config = Config(
            services=Services(
                pythinker_ai_fetch=PythinkerAIFetchConfig(
                    base_url=f"http://127.0.0.1:{port}/fetch",
                    api_key=SecretStr("test-key"),
                )
            )
        )
        fetch_tool = FetchURL(config=config, runtime=runtime)

        from pythinker_code.soul.toolset import current_tool_call
        from pythinker_code.wire.types import ToolCall

        token = current_tool_call.set(
            ToolCall(
                id="test-call-id", function=ToolCall.FunctionBody(name="FetchURL", arguments=None)
            )
        )
        try:
            result = await fetch_tool(Params(url="https://example.com"))
        finally:
            current_tool_call.reset(token)

        assert not result.is_error
        assert isinstance(result.output, str)
        assert "truncated" in result.message
        # unwrap_untrusted asserts the envelope is well-formed (closing tag intact).
        inner = unwrap_untrusted(result.output)
        assert len(inner) < len(big_content)
        assert strip_untrusted_envelope(result.output) == inner

    finally:
        await runner.cleanup()


@pytest_asyncio.fixture
async def serve_app() -> AsyncIterator[Callable[[web.Application], Awaitable[str]]]:
    """Serve an arbitrary aiohttp app on a random loopback port and clean up."""
    runners: list[web.AppRunner] = []

    async def _serve(app: web.Application) -> str:
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="127.0.0.1", port=0)
        await site.start()
        runners.append(runner)
        sockets = site._server.sockets  # type: ignore[attr-defined]
        assert sockets, "Server failed to bind to a port."
        return f"http://127.0.0.1:{sockets[0].getsockname()[1]}"

    try:
        yield _serve
    finally:
        for runner in runners:
            await runner.cleanup()


async def test_fetch_url_redirect_to_blocked_target_is_rejected(
    fetch_url_tool: FetchURL,
    serve_app: Callable[[web.Application], Awaitable[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 30x redirect whose target fails SSRF validation must be rejected, not
    silently followed (aiohttp would otherwise follow it without re-checking)."""

    def _validator(url: str, _allowed: object = None) -> str | None:
        return "internal address blocked" if "blocked.invalid" in url else None

    monkeypatch.setattr(fetch_module, "_validate_fetch_url", _validator)

    async def handler(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(status=302, headers={"Location": "http://blocked.invalid/secret"})

    app = web.Application()
    app.router.add_get("/", handler)
    base = await serve_app(app)

    result = await fetch_url_tool(Params(url=base))

    assert result.is_error
    assert "internal address blocked" in result.message


async def test_fetch_url_follows_safe_redirect(
    fetch_url_tool: FetchURL,
    serve_app: Callable[[web.Application], Awaitable[str]],
) -> None:
    """Legitimate redirects to allowed targets are still followed end to end."""

    async def start(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(status=302, headers={"Location": "/dest"})

    async def dest(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(text="redirected body", content_type="text/markdown")

    app = web.Application()
    app.router.add_get("/start", start)
    app.router.add_get("/dest", dest)
    base = await serve_app(app)

    result = await fetch_url_tool(Params(url=f"{base}/start"))

    assert not result.is_error
    assert "redirected body" in unwrap_untrusted(result.output)


async def test_fetch_url_redirect_loop_is_capped(
    fetch_url_tool: FetchURL,
    serve_app: Callable[[web.Application], Awaitable[str]],
) -> None:
    """A redirect loop terminates with an error instead of looping forever."""

    async def loop(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(status=302, headers={"Location": "/loop"})

    app = web.Application()
    app.router.add_get("/loop", loop)
    base = await serve_app(app)

    result = await fetch_url_tool(Params(url=f"{base}/loop"))

    assert result.is_error
    assert "too many redirects" in result.message


def _make_addrinfo(ip_str: str):
    """Build a minimal socket.getaddrinfo-style result for a single IP."""
    import socket

    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip_str, 80))]


def _addrinfo_returning(ip_str: str):
    """Return a fake socket.getaddrinfo callable that always resolves to *ip_str*."""

    def _fake(*_args, **_kwargs):
        return _make_addrinfo(ip_str)

    return _fake


async def test_fetch_url_connector_blocks_rebound_private_ip() -> None:
    """DNS-rebinding guard: _SSRFConnector blocks a connection when _resolve_host
    returns a private/loopback address, even if _validate_fetch_url was not called.

    Fails before the fix because new_client_session uses a plain TCPConnector
    that connects regardless of the resolved IP.
    """
    import aiohttp

    from pythinker_code.utils.aiohttp import new_client_session

    # ip_blocked returns True for any address — simulates the deny rule
    def _always_blocked(address: str) -> bool:
        return True

    session = new_client_session(ip_blocked=_always_blocked)
    async with session:
        with pytest.raises(aiohttp.ClientConnectionError):
            async with session.get("http://example.com/"):
                pass


async def test_fetch_url_connector_blocks_rebound_private_ip_via_resolve() -> None:
    """Unit-guard for _SSRFConnector._resolve_host: checks the private API exists
    and that it raises ClientConnectionError when ip_blocked returns True for a
    resolved host record.  Fails loudly on aiohttp upgrades that change the
    signature rather than silently disabling the guard.
    """
    import aiohttp
    from unittest.mock import AsyncMock, patch

    from pythinker_code.utils.aiohttp import _SSRFConnector

    connector = _SSRFConnector(ssl=False, ip_blocked=lambda _: True)

    fake_hosts = [{"host": "1.2.3.4", "port": 80}]

    try:
        with patch.object(
            aiohttp.TCPConnector,
            "_resolve_host",
            new=AsyncMock(return_value=fake_hosts),
        ):
            with pytest.raises(aiohttp.ClientConnectionError):
                await connector._resolve_host("1.2.3.4", 80)
    finally:
        await connector.close()


def test_validate_fetch_url_blocks_cgnat_and_unspecified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed SSRF guard: block CGNAT, unspecified, benchmarking, multicast;
    allow a genuine public address."""

    _BLOCKED = "Fetching private, local, link-local, multicast, or reserved addresses is blocked."

    blocked_cases = [
        ("100.64.0.1", "CGNAT (RFC 6598)"),
        ("0.0.0.0", "unspecified address"),
        ("198.18.0.1", "benchmarking range (RFC 2544)"),
        ("224.0.0.1", "multicast"),
    ]

    for ip_str, label in blocked_cases:
        monkeypatch.setattr(
            fetch_module.socket,
            "getaddrinfo",
            _addrinfo_returning(ip_str),
        )
        result = _validate_fetch_url("http://example.com/")
        assert result == _BLOCKED, f"Expected block for {label} ({ip_str}), got: {result!r}"

    # Public address must still be allowed (no false positive).
    monkeypatch.setattr(
        fetch_module.socket,
        "getaddrinfo",
        _addrinfo_returning("8.8.8.8"),
    )
    assert _validate_fetch_url("http://example.com/") is None, "8.8.8.8 must not be blocked"
