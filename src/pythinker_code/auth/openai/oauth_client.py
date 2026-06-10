# pyright: reportUnusedFunction=false
"""OpenAI OAuth client: PKCE/state generation, token exchanges, and device-code flow."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, cast

from pythinker_code.auth.oauth import OAuthError, OAuthToken, OAuthUnauthorized
from pythinker_code.auth.openai.constants import OPENAI_AUTH_ISSUER, OPENAI_CLIENT_ID
from pythinker_code.utils.aiohttp import new_client_session


@dataclass(frozen=True, slots=True)
class PkceCodes:
    code_verifier: str
    code_challenge: str


@dataclass(frozen=True, slots=True)
class DeviceCode:
    device_auth_id: str
    user_code: str
    interval: int = 5


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _generate_pkce() -> PkceCodes:
    verifier = _base64url(secrets.token_bytes(32))
    challenge = _base64url(hashlib.sha256(verifier.encode(encoding="utf-8")).digest())
    return PkceCodes(code_verifier=verifier, code_challenge=challenge)


def _generate_state() -> str:
    return secrets.token_urlsafe(32)


async def _request_device_code() -> DeviceCode:
    async with (
        new_client_session() as session,
        session.post(
            f"{OPENAI_AUTH_ISSUER}/api/accounts/deviceauth/usercode",
            json={"client_id": OPENAI_CLIENT_ID},
        ) as response,
    ):
        payload = await response.json(content_type=None)
        status = response.status

    if status != 200:
        raise OAuthError(f"Failed to request OpenAI device code: HTTP {status}")

    user_code = payload.get("user_code") or payload.get("usercode")
    device_auth_id = payload.get("device_auth_id")
    if not user_code or not device_auth_id:
        raise OAuthError("OpenAI device authorization response did not include a user code.")

    return DeviceCode(
        device_auth_id=str(device_auth_id),
        user_code=str(user_code),
        interval=int(payload.get("interval") or 5),
    )


async def _poll_device_code(device_code: DeviceCode) -> dict[str, str]:
    deadline = time.monotonic() + 15 * 60
    while time.monotonic() < deadline:
        await asyncio.sleep(max(device_code.interval, 1))
        async with (
            new_client_session() as session,
            session.post(
                f"{OPENAI_AUTH_ISSUER}/api/accounts/deviceauth/token",
                json={
                    "device_auth_id": device_code.device_auth_id,
                    "user_code": device_code.user_code,
                },
            ) as response,
        ):
            payload = await response.json(content_type=None)
            status = response.status

        if status == 200:
            authorization_code = payload.get("authorization_code")
            code_verifier = payload.get("code_verifier")
            if not authorization_code or not code_verifier:
                raise OAuthError("OpenAI device token response was incomplete.")
            return {
                "authorization_code": str(authorization_code),
                "code_verifier": str(code_verifier),
            }
        if status in {403, 404}:
            continue
        raise OAuthError(f"Failed to poll OpenAI device code: HTTP {status}")

    raise OAuthError("Timed out waiting for OpenAI device authorization.")


async def _exchange_code_for_tokens(
    authorization_code: str, code_verifier: str, redirect_uri: str
) -> dict[str, Any]:
    async with (
        new_client_session() as session,
        session.post(
            f"{OPENAI_AUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": OPENAI_CLIENT_ID,
                "code": authorization_code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        ) as response,
    ):
        payload = await response.json(content_type=None)
        status = response.status

    if status != 200:
        raise OAuthError(f"Failed to exchange OpenAI authorization code: HTTP {status}")
    return payload


async def _exchange_id_token_for_api_key(id_token: str) -> str:
    async with (
        new_client_session() as session,
        session.post(
            f"{OPENAI_AUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": OPENAI_CLIENT_ID,
                "subject_token": id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "requested_token": "openai-api-key",
            },
        ) as response,
    ):
        payload = await response.json(content_type=None)
        status = response.status

    if status != 200:
        return ""
    return str(payload.get("access_token") or "")


async def refresh_openai_chatgpt_token(refresh_token: str) -> OAuthToken:
    async with (
        new_client_session() as session,
        session.post(
            f"{OPENAI_AUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": OPENAI_CLIENT_ID,
                "refresh_token": refresh_token,
            },
        ) as response,
    ):
        payload = await response.json(content_type=None)
        status = response.status

    if status != 200:
        error_description = str(payload.get("error_description") or "")
        if status in {401, 403}:
            raise OAuthUnauthorized(error_description or "OpenAI token refresh unauthorized.")
        raise OAuthError(error_description or f"OpenAI token refresh failed ({status}).")
    return _token_from_openai_response(payload)


def _token_from_openai_response(payload: dict[str, Any]) -> OAuthToken:
    normalized = {
        "token_type": "Bearer",
        "scope": "openid profile email offline_access",
        "expires_in": 3600,
        **payload,
    }
    # ChatGPT does not return `account_id` as a top-level OAuth response field;
    # it lives inside the OAuth JWT claims under
    # `https://api.openai.com/auth.chatgpt_account_id`. Hoist it onto the
    # response so OAuthToken.from_response() picks it up. Without this the
    # ChatGPT usage adapter, model catalog endpoint, and Codex request headers
    # cannot scope requests to the active Plus/Pro account.
    if "account_id" not in normalized:
        jwt_token = payload.get("id_token") or payload.get("access_token")
        if jwt_token and (account_id := _extract_chatgpt_account_id(str(jwt_token))):
            normalized["account_id"] = account_id
    return OAuthToken.from_response(normalized)


def _extract_chatgpt_account_id(id_token: str) -> str | None:
    """Decode the id_token JWT (without verifying the signature) and pull the
    ChatGPT account id out of the `https://api.openai.com/auth` claim. We do
    not verify the signature here because the token was just received over TLS
    from the OpenAI auth server in response to our PKCE/refresh exchange.
    """
    parts = id_token.split(".")
    if len(parts) < 2:
        return None
    try:
        # JWT segments are base64url without padding; pad before decoding.
        segment = parts[1]
        padded = segment + "=" * (-len(segment) % 4)
        claims_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
    except (ValueError, binascii.Error):
        return None
    try:
        claims = json.loads(claims_bytes)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    claims_dict = cast(dict[str, Any], claims)
    auth_claim = claims_dict.get("https://api.openai.com/auth")
    if not isinstance(auth_claim, dict):
        return None
    auth_dict = cast(dict[str, Any], auth_claim)
    account_id = auth_dict.get("chatgpt_account_id")
    return str(account_id) if account_id else None
