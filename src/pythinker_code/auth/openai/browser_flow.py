# pyright: reportPrivateUsage=false, reportUnusedFunction=false
"""Localhost-callback browser flow for the OpenAI ChatGPT login."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlencode, urlsplit

from pythinker_code.auth.browser_login_page import build_browser_login_result_html
from pythinker_code.auth.oauth import OAuthError
from pythinker_code.auth.openai.constants import (
    OPENAI_AUTH_ISSUER,
    OPENAI_BROWSER_FALLBACK_PORT,
    OPENAI_BROWSER_PORT,
    OPENAI_BROWSER_REDIRECT_PATH,
    OPENAI_CLIENT_ID,
)
from pythinker_code.auth.openai.oauth_client import PkceCodes, _generate_pkce, _generate_state


def _build_authorize_url(
    *,
    redirect_uri: str,
    pkce: PkceCodes,
    state: str,
    authorize_url: str = f"{OPENAI_AUTH_ISSUER}/oauth/authorize",
    client_id: str = OPENAI_CLIENT_ID,
    scope: str = "openid profile email offline_access api.connectors.read api.connectors.invoke",
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": "S256",
            "codex_cli_simplified_flow": "true",
            "id_token_add_organizations": "true",
            "originator": "codex_cli_rs",
            # Force a fresh login screen instead of silently reusing the browser's
            # existing ChatGPT session. Without this, `/login` cannot switch
            # accounts: OpenAI re-authorizes whoever is already signed in and
            # hands back a fresh token for the *same* account.
            "prompt": "login",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    return f"{authorize_url}?{query}"


def _callback_html(*, ok: bool, message: str | None) -> str:
    return build_browser_login_result_html(
        ok=ok,
        success_title="Pythinker logged in",
        failure_title="Pythinker login failed",
        success_heading="You're logged in to Pythinker",
        failure_heading="Pythinker login failed",
        success_body="You can close this tab and return to Pythinker.",
        failure_body=message,
        fallback_failure_body="OpenAI login failed.",
    )


async def _handle_browser_callback(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, state: str
) -> tuple[str | None, str | None]:
    line = await reader.readline()
    parts = line.decode("utf-8", errors="replace").strip().split()
    code: str | None = None
    error: str | None = None

    is_callback = False
    if len(parts) >= 2:
        parsed = urlsplit(parts[1])
        if parsed.path == OPENAI_BROWSER_REDIRECT_PATH:
            is_callback = True
            params = parse_qs(parsed.query)
            if params.get("state", [None])[0] != state:
                error = "Invalid OpenAI callback state."
            elif params.get("error", [None])[0]:
                error = params.get("error_description", params["error"])[0]
            else:
                code = params.get("code", [None])[0]
                if not code:
                    error = "OpenAI callback did not include an authorization code."

    if not is_callback:
        # Stray probe (favicon, /, port scanner): 404 and keep waiting.
        # Returning (None, None) leaves the shared future unresolved.
        writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return None, None

    ok = code is not None and error is None
    response_html = _callback_html(ok=ok, message=error)
    status = "200 OK" if ok else "400 Bad Request"
    writer.write(
        bytes(
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(response_html.encode('utf-8'))}\r\n"
            "Connection: close\r\n\r\n"
            f"{response_html}",
            encoding="utf-8",
        )
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()
    return code, error


async def _browser_callback_task(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: str,
    result: asyncio.Future[tuple[str | None, str | None]],
) -> None:
    try:
        code, error = await _handle_browser_callback(reader, writer, state)
    except asyncio.CancelledError:
        writer.close()
        await writer.wait_closed()
        raise
    if not result.done() and (code or error):
        result.set_result((code, error))


def _track_browser_callback_task(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: str,
    result: asyncio.Future[tuple[str | None, str | None]],
    callback_tasks: set[asyncio.Task[None]],
) -> None:
    task = asyncio.create_task(_browser_callback_task(reader, writer, state, result))
    callback_tasks.add(task)
    task.add_done_callback(callback_tasks.discard)


async def _wait_for_browser_code(open_browser: bool = True) -> tuple[str, str, str]:
    pkce = _generate_pkce()
    state = _generate_state()
    result: asyncio.Future[tuple[str | None, str | None]] = (
        asyncio.get_running_loop().create_future()
    )
    callback_tasks: set[asyncio.Task[None]] = set()
    server: asyncio.Server | None = None
    redirect_uri = ""

    for port in (OPENAI_BROWSER_PORT, OPENAI_BROWSER_FALLBACK_PORT):
        try:
            server = await asyncio.start_server(
                lambda reader, writer: _track_browser_callback_task(
                    reader, writer, state, result, callback_tasks
                ),
                "127.0.0.1",
                port,
            )
        except OSError:
            continue
        redirect_uri = f"http://localhost:{port}{OPENAI_BROWSER_REDIRECT_PATH}"
        break

    if server is None:
        raise OAuthError("Failed to start OpenAI browser callback server.")

    auth_url = _build_authorize_url(redirect_uri=redirect_uri, pkce=pkce, state=state)
    if open_browser:
        from pythinker_code.utils.term import open_url_in_browser

        open_url_in_browser(auth_url)

    try:
        code, error = await asyncio.wait_for(result, timeout=15 * 60)
    finally:
        server.close()
        for task in callback_tasks:
            task.cancel()
        if callback_tasks:
            await asyncio.gather(*callback_tasks, return_exceptions=True)
        await server.wait_closed()

    if error:
        raise OAuthError(error)
    if not code:
        raise OAuthError("OpenAI callback did not include an authorization code.")
    return code, pkce.code_verifier, redirect_uri
