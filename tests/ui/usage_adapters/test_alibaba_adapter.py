"""Tests for AlibabaAdapter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from pydantic import SecretStr

from pythinker_code.config import LLMProvider
from pythinker_code.ui.shell.usage_adapters.alibaba import (
    AlibabaAdapter,
    _parse_quota_response,
    _quota_url,
)
from pythinker_code.usage_ratelimit_cache import RateLimitSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    api_key: str = "test-key",
    base_url: str = "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
) -> LLMProvider:
    return LLMProvider(
        type="openai_legacy",
        api_key=SecretStr(api_key),
        base_url=base_url,
    )


class _StubOAuth:
    pass


def _make_response(status: int, json_data: object = None) -> MagicMock:
    """Build a fake aiohttp response context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


def _make_session(response: MagicMock) -> MagicMock:
    """Build a fake aiohttp ClientSession context manager."""
    session = MagicMock()
    # session.get(...) is used as an async context manager
    get_cm = MagicMock()
    get_cm.__aenter__ = AsyncMock(return_value=response)
    get_cm.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=get_cm)
    return session


@asynccontextmanager
async def _fake_new_client_session(session: MagicMock, **_kwargs):
    yield session


# ---------------------------------------------------------------------------
# Unit tests for pure helpers
# ---------------------------------------------------------------------------


def test_quota_url_strips_path() -> None:
    # US completion host is remapped to the international quota host
    assert _quota_url("https://dashscope-us.aliyuncs.com/compatible-mode/v1") == (
        "https://dashscope-intl.aliyuncs.com/api/v1/quotas"
    )


def test_quota_url_china_unchanged() -> None:
    # China host has no remap — quota API lives on the same host
    assert _quota_url("https://dashscope.aliyuncs.com/compatible-mode/v1") == (
        "https://dashscope.aliyuncs.com/api/v1/quotas"
    )


def test_parse_quota_response_flat_shape() -> None:
    data = {"token_quota": 1_000_000, "token_used": 123_456}
    rows = _parse_quota_response(data)
    assert len(rows) == 1
    assert rows[0].label == "Token quota"
    assert rows[0].used == 123_456
    assert rows[0].limit == 1_000_000
    assert rows[0].unit == "tokens"


def test_parse_quota_response_flat_shape_inside_data_key() -> None:
    data = {"data": {"token_quota": 500_000, "token_used": 50_000}}
    rows = _parse_quota_response(data)
    assert len(rows) == 1
    assert rows[0].used == 50_000
    assert rows[0].limit == 500_000


def test_parse_quota_response_quota_list_shape() -> None:
    data = {
        "quota_list": [
            {"quota_name": "text", "total_quota": 500_000, "total_used": 50_000},
        ]
    }
    rows = _parse_quota_response(data)
    assert len(rows) == 1
    assert rows[0].label == "Text"
    assert rows[0].used == 50_000
    assert rows[0].limit == 500_000
    assert rows[0].unit == "tokens"


def test_parse_quota_response_unrecognised_shape_returns_empty() -> None:
    assert _parse_quota_response({"foo": "bar"}) == []
    assert _parse_quota_response("not a dict") == []
    assert _parse_quota_response(None) == []


# ---------------------------------------------------------------------------
# Adapter metadata
# ---------------------------------------------------------------------------


def test_alibaba_adapter_metadata() -> None:
    assert AlibabaAdapter.platform_id == "alibaba"
    assert AlibabaAdapter.requires_admin_key is False
    assert AlibabaAdapter.provider_label == "Alibaba DashScope"


# ---------------------------------------------------------------------------
# Async fetch tests
# ---------------------------------------------------------------------------


async def test_quota_api_success() -> None:
    """HTTP 200 with flat quota shape produces a correct UsageRow."""
    json_data = {"token_quota": 1_000_000, "token_used": 123_456}
    resp = _make_response(200, json_data)
    session = _make_session(resp)

    with patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.new_client_session",
        side_effect=lambda **kw: _fake_new_client_session(session, **kw),
    ), patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.get_cache"
    ) as mock_cache:
        mock_cache.return_value.snapshot.return_value = None
        report = await AlibabaAdapter().fetch(_make_provider(), _StubOAuth())  # type: ignore[arg-type]

    assert report.summary is not None
    assert report.summary.label == "Token quota"
    assert report.summary.used == 123_456
    assert report.summary.limit == 1_000_000
    assert report.summary.unit == "tokens"
    assert report.notes == []


async def test_quota_list_shape() -> None:
    """HTTP 200 with quota_list shape produces a correct UsageRow."""
    json_data = {
        "quota_list": [
            {"quota_name": "text", "total_quota": 500_000, "total_used": 50_000}
        ]
    }
    resp = _make_response(200, json_data)
    session = _make_session(resp)

    with patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.new_client_session",
        side_effect=lambda **kw: _fake_new_client_session(session, **kw),
    ), patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.get_cache"
    ) as mock_cache:
        mock_cache.return_value.snapshot.return_value = None
        report = await AlibabaAdapter().fetch(_make_provider(), _StubOAuth())  # type: ignore[arg-type]

    assert report.summary is not None
    assert report.summary.label == "Text"
    assert report.summary.used == 50_000
    assert report.summary.limit == 500_000


async def test_quota_api_404_falls_through() -> None:
    """HTTP 404 with no snapshot falls through to the 'no data yet' note."""
    resp = _make_response(404)
    session = _make_session(resp)

    with patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.new_client_session",
        side_effect=lambda **kw: _fake_new_client_session(session, **kw),
    ), patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.get_cache"
    ) as mock_cache:
        mock_cache.return_value.snapshot.return_value = None
        report = await AlibabaAdapter().fetch(_make_provider(), _StubOAuth())  # type: ignore[arg-type]

    assert report.summary is None
    assert report.limits == []
    assert any("console.aliyun.com" in n or "quota" in n.lower() for n in report.notes)


async def test_quota_api_401_shows_note() -> None:
    """HTTP 401 appends an authorization-failure note."""
    resp = _make_response(401)
    session = _make_session(resp)

    with patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.new_client_session",
        side_effect=lambda **kw: _fake_new_client_session(session, **kw),
    ), patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.get_cache"
    ) as mock_cache:
        mock_cache.return_value.snapshot.return_value = None
        report = await AlibabaAdapter().fetch(_make_provider(), _StubOAuth())  # type: ignore[arg-type]

    assert any("authorization failed" in n.lower() for n in report.notes)


async def test_ratelimit_cache_used() -> None:
    """When quota API returns 404, snapshot data fills in rate-limit rows."""
    resp = _make_response(404)
    session = _make_session(resp)

    snap = RateLimitSnapshot(
        requests_limit=None,
        requests_remaining=None,
        requests_reset_seconds=None,
        tokens_limit=10_000,
        tokens_remaining=8_000,
        tokens_reset_seconds=None,
        captured_at=0.0,
    )

    with patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.new_client_session",
        side_effect=lambda **kw: _fake_new_client_session(session, **kw),
    ), patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.get_cache"
    ) as mock_cache:
        mock_cache.return_value.snapshot.return_value = snap
        report = await AlibabaAdapter().fetch(_make_provider(), _StubOAuth())  # type: ignore[arg-type]

    assert report.summary is not None
    assert report.summary.label == "Tokens"
    assert report.summary.used == 8_000
    assert report.summary.limit == 10_000
    assert report.summary.unit == "tokens"


async def test_network_error_falls_through() -> None:
    """aiohttp.ClientError during HTTP call is swallowed; returns a UsageReport."""

    @asynccontextmanager
    async def _error_session(**_kw):
        session = MagicMock()
        get_cm = MagicMock()
        get_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("network"))
        get_cm.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=get_cm)
        yield session

    with patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.new_client_session",
        side_effect=_error_session,
    ), patch(
        "pythinker_code.ui.shell.usage_adapters.alibaba.get_cache"
    ) as mock_cache:
        mock_cache.return_value.snapshot.return_value = None
        # Must not raise
        report = await AlibabaAdapter().fetch(_make_provider(), _StubOAuth())  # type: ignore[arg-type]

    assert report is not None
    assert any("console.aliyun.com" in n or "quota" in n.lower() for n in report.notes)
