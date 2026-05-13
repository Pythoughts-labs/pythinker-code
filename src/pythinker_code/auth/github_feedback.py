from __future__ import annotations

import asyncio
import time
import webbrowser
from dataclasses import dataclass
from typing import Any, cast

from pythinker_code.auth.oauth import (
    OAuthEvent,
    OAuthRef,
    OAuthToken,
    delete_tokens,
    load_tokens,
    save_tokens,
)
from pythinker_code.utils.aiohttp import new_client_session
from pythinker_code.utils.logging import logger

GITHUB_FEEDBACK_OAUTH_KEY = "oauth/github-feedback"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubFeedbackError(RuntimeError):
    """GitHub feedback submission failed."""


@dataclass(slots=True, frozen=True)
class GitHubIssue:
    number: int | None
    html_url: str | None


@dataclass(slots=True, frozen=True)
class _GitHubDeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


def _oauth_ref() -> OAuthRef:
    return OAuthRef(storage="file", key=GITHUB_FEEDBACK_OAUTH_KEY)


def load_github_feedback_token() -> str | None:
    token = load_tokens(_oauth_ref())
    if token is None or not token.access_token:
        return None
    return token.access_token


def delete_github_feedback_token() -> None:
    delete_tokens(_oauth_ref())


async def _request_device_authorization(client_id: str) -> _GitHubDeviceAuthorization:
    async with (
        new_client_session() as session,
        session.post(
            GITHUB_DEVICE_CODE_URL,
            data={"client_id": client_id, "scope": "public_repo"},
            headers={"Accept": "application/json"},
        ) as response,
    ):
        data_any: Any = await response.json(content_type=None)
        status = response.status
    if not isinstance(data_any, dict):
        raise GitHubFeedbackError("Unexpected GitHub device authorization response.")
    data = cast(dict[str, Any], data_any)
    if status != 200:
        message = str(data.get("error_description") or data.get("error") or status)
        raise GitHubFeedbackError(f"GitHub device authorization failed: {message}")
    return _GitHubDeviceAuthorization(
        device_code=str(data["device_code"]),
        user_code=str(data["user_code"]),
        verification_uri=str(data["verification_uri"]),
        expires_in=int(data.get("expires_in") or 900),
        interval=max(int(data.get("interval") or 5), 1),
    )


async def _poll_access_token(
    client_id: str,
    auth: _GitHubDeviceAuthorization,
) -> OAuthToken:
    interval = auth.interval
    expires_at = time.monotonic() + auth.expires_in
    while time.monotonic() < expires_at:
        await asyncio.sleep(interval)
        async with (
            new_client_session() as session,
            session.post(
                GITHUB_ACCESS_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "device_code": auth.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            ) as response,
        ):
            data_any: Any = await response.json(content_type=None)
            status = response.status
        if not isinstance(data_any, dict):
            raise GitHubFeedbackError("Unexpected GitHub token response.")
        data = cast(dict[str, Any], data_any)
        if status != 200:
            message = str(data.get("error_description") or data.get("error") or status)
            raise GitHubFeedbackError(f"GitHub token request failed: {message}")
        access_token = str(data.get("access_token") or "")
        if access_token:
            return OAuthToken(
                access_token=access_token,
                refresh_token=str(data.get("refresh_token") or ""),
                expires_at=float(data.get("expires_at") or 0),
                scope=str(data.get("scope") or ""),
                token_type=str(data.get("token_type") or "bearer"),
                expires_in=float(data.get("expires_in") or 0),
            )
        error_code = str(data.get("error") or "")
        if error_code == "authorization_pending":
            continue
        if error_code == "slow_down":
            interval += 5
            continue
        if error_code == "expired_token":
            raise GitHubFeedbackError("GitHub device code expired.")
        if error_code == "access_denied":
            raise GitHubFeedbackError("GitHub authorization was denied.")
        message = str(data.get("error_description") or error_code or "unknown error")
        raise GitHubFeedbackError(f"GitHub authorization failed: {message}")
    raise GitHubFeedbackError("GitHub device code expired.")


async def login_github_feedback(
    client_id: str,
    *,
    open_browser: bool = True,
):
    auth = await _request_device_authorization(client_id)
    yield OAuthEvent(
        "verification_url",
        f"Open {auth.verification_uri} and enter code {auth.user_code}",
        data={"verification_url": auth.verification_uri, "user_code": auth.user_code},
    )
    if open_browser:
        try:
            webbrowser.open(auth.verification_uri)
        except Exception as exc:
            logger.warning("Failed to open browser: {error}", error=exc)
    yield OAuthEvent("waiting", "Waiting for GitHub authorization...")
    token = await _poll_access_token(client_id, auth)
    save_tokens(_oauth_ref(), token)
    yield OAuthEvent("success", "GitHub authorization complete.")


def _normalize_repo(repo: str) -> str:
    repo = repo.strip().strip("/")
    if repo.count("/") != 1:
        raise GitHubFeedbackError("GitHub feedback repo must be in owner/name form.")
    return repo


async def create_github_issue(
    repo: str,
    token: str,
    *,
    title: str,
    body: str,
) -> GitHubIssue:
    repo = _normalize_repo(repo)
    async with (
        new_client_session() as session,
        session.post(
            f"{GITHUB_API_URL}/repos/{repo}/issues",
            json={"title": title, "body": body},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "pythinker-feedback-cli",
            },
        ) as response,
    ):
        data_any: Any = await response.json(content_type=None)
        status = response.status
    if not isinstance(data_any, dict):
        raise GitHubFeedbackError("Unexpected GitHub issue response.")
    data = cast(dict[str, Any], data_any)
    if status not in {200, 201}:
        message = str(data.get("message") or status)
        raise GitHubFeedbackError(f"GitHub issue creation failed: {message}")
    number = data.get("number")
    return GitHubIssue(
        number=int(number) if isinstance(number, int) else None,
        html_url=str(data.get("html_url") or "") or None,
    )


async def star_github_repo(repo: str, token: str) -> None:
    repo = _normalize_repo(repo)
    async with (
        new_client_session() as session,
        session.put(
            f"{GITHUB_API_URL}/user/starred/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "pythinker-feedback-cli",
            },
        ) as response,
    ):
        status = response.status
        if status == 204:
            return
        try:
            data_any: Any = await response.json(content_type=None)
        except Exception:
            data_any = {}
    message_payload = cast(dict[str, Any], data_any) if isinstance(data_any, dict) else {}
    message = str(message_payload.get("message") or status)
    raise GitHubFeedbackError(f"GitHub star failed: {message}")
