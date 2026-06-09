# ruff: noqa

"""Tool-level tests for the web domain allowlist on FetchURL and SearchWeb."""

from __future__ import annotations

from aiohttp import web
from pydantic import SecretStr

from pythinker_code.config import Config, PythinkerAISearchConfig
from pythinker_code.soul.toolset import current_tool_call
from pythinker_code.tools.web import fetch as fetch_module
from pythinker_code.tools.web.fetch import FetchURL, Params, _validate_fetch_url
from pythinker_code.tools.web.search import Params as SearchParams
from pythinker_code.tools.web.search import SearchWeb
from pythinker_code.wire.types import ToolCall


def test_validate_fetch_url_allows_in_allowlist_host() -> None:
    # Allowed host (subdomain) passes validation; SSRF check is unrelated here.
    assert _validate_fetch_url("https://docs.example.com/x", ["example.com"]) is None


def test_validate_fetch_url_rejects_out_of_allowlist_host() -> None:
    reason = _validate_fetch_url("https://evil.org/x", ["example.com"])
    assert reason == "URL host is not in the configured web allowlist."


async def test_fetch_url_rejected_by_allowlist_makes_no_request(
    config: Config, runtime, monkeypatch
) -> None:
    config.web.allowed_domains = ["example.com"]

    def _no_network(*_args, **_kwargs):
        raise AssertionError("network must not be opened for a disallowed host")

    monkeypatch.setattr(fetch_module, "new_client_session", _no_network)

    tool = FetchURL(config=config, runtime=runtime)
    result = await tool(Params(url="https://evil.org/page"))

    assert result.is_error
    assert "allowlist" in result.message.lower()


async def test_search_web_filters_results_by_allowlist(config: Config, runtime) -> None:
    payload = {
        "search_results": [
            {
                "site_name": "Example",
                "title": "Allowed",
                "url": "https://docs.example.com/a",
                "snippet": "kept",
            },
            {
                "site_name": "Evil",
                "title": "Blocked",
                "url": "https://evil.org/b",
                "snippet": "dropped",
            },
        ]
    }

    async def handler(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.json_response(payload)

    app = web.Application()
    app.router.add_post("/search", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[index]

    try:
        config.services.pythinker_ai_search = PythinkerAISearchConfig(
            base_url=f"http://127.0.0.1:{port}/search",
            api_key=SecretStr("test-key"),
        )
        config.web.allowed_domains = ["example.com"]
        tool = SearchWeb(config, runtime)

        token = current_tool_call.set(
            ToolCall(
                id="test-call-id",
                function=ToolCall.FunctionBody(name="SearchWeb", arguments=None),
            )
        )
        try:
            result = await tool(SearchParams(query="x"))
        finally:
            current_tool_call.reset(token)
    finally:
        await runner.cleanup()

    assert not result.is_error
    assert "docs.example.com" in result.output
    assert "evil.org" not in result.output
    assert (result.extras or {}).get("allowlist_filtered") == 1
    # Search results are crawled third-party web content — wrapped as untrusted
    # data for the model (prompt-injection defense), mirroring FetchURL.
    assert isinstance(result.output, str)
    assert result.output.startswith("<untrusted_data id=")
    assert result.output.rstrip().endswith("</untrusted_data>")
