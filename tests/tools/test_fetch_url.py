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
from pythinker_code.tools.web.fetch import FetchURL, Params


@pytest.fixture(autouse=True)
def _bypass_ssrf_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fetch tool blocks loopback / private IPs as SSRF mitigation, but
    every test in this module either talks to a localhost mock server or
    exercises malformed-URL handling that pre-dates the validator. Disable it
    for these unit tests; production callers still get the protection.
    """
    monkeypatch.setattr(fetch_module, "_validate_fetch_url", lambda _url: None)


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
    assert "optimizer" in result.output
    assert "adamw" in result.output
    assert "adamW" in result.output
    # Verify HTML tags were stripped (not returning raw HTML)
    assert "<article>" not in result.output
    assert "<code>" not in result.output
    # Verify metadata extraction (with_metadata=True)
    assert "title:" in result.output.lower()
    assert "description:" in result.output.lower()


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
    assert result.output == snapshot(plain_markdown)
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
    assert result.output == snapshot(complex_markdown)
    assert result.message == "The returned content is the full content of the page."


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
        assert result.output == expected_content
        assert result.message == snapshot(
            "The returned content is the main content extracted from the page."
        )

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

    def _validator(url: str) -> str | None:
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
    assert "redirected body" in result.output


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
