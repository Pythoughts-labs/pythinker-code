from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "models-dev-subset.json"


def _fixture_json() -> str:
    return FIXTURE_PATH.read_text()


def _fixture_dict() -> dict:
    return json.loads(_fixture_json())


# ---------------------------------------------------------------------------
# flatten_catalog
# ---------------------------------------------------------------------------


def test_flatten_canonical_provider_wins():
    from pythinker_code.models_dev import _flatten_catalog

    catalog = _fixture_dict()
    result = _flatten_catalog(catalog)
    # anthropic is canonical; google-vertex-anthropic is not
    assert "claude-sonnet-4-6" in result
    p = result["claude-sonnet-4-6"]
    assert p.input == 3.0  # anthropic price, not vertex (3.1)


def test_flatten_skips_versioned_ids():
    from pythinker_code.models_dev import _flatten_catalog

    catalog = _fixture_dict()
    result = _flatten_catalog(catalog)
    assert "claude-sonnet-4-6@default" not in result


def test_flatten_missing_cache_fields_defaults_to_zero():
    from pythinker_code.models_dev import _flatten_catalog

    catalog = _fixture_dict()
    result = _flatten_catalog(catalog)
    # gpt-4o-mini has no cache_write in fixture
    assert result["gpt-4o-mini"].cache_write == 0.0
    # openai gpt-4o-mini has cache_read in fixture
    assert result["gpt-4o-mini"].cache_read == 0.08


def test_flatten_unknown_provider_included_as_fallback():
    from pythinker_code.models_dev import _flatten_catalog

    catalog = _fixture_dict()
    result = _flatten_catalog(catalog)
    # unknown-provider/some-model not overridden by canonical
    assert "some-model" in result


def test_flatten_context_over_200k_ignored():
    from pythinker_code.models_dev import _flatten_catalog

    catalog = _fixture_dict()
    result = _flatten_catalog(catalog)
    # Base tier only — input should be 3.0, not 6.0
    assert result["claude-sonnet-4-6"].input == 3.0


def test_flatten_malformed_costs_skipped():
    from pythinker_code.models_dev import _flatten_catalog

    catalog = {
        "openai": {
            "models": {
                "bad-model": {"cost": {"input": "n/a", "output": 1.0}},
                "good-model": {"cost": {"input": 1.0, "output": 2.0}},
            }
        }
    }
    result = _flatten_catalog(catalog)
    assert "bad-model" not in result
    assert "good-model" in result
    assert result["good-model"].input == 1.0


# ---------------------------------------------------------------------------
# load_catalog
# ---------------------------------------------------------------------------


def test_load_catalog_empty_when_no_cache_file(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: tmp_path / "nonexistent.json")
    models_dev._catalog_cache.clear()
    result = models_dev.load_catalog()
    assert result == {}


def test_load_catalog_parses_valid_cache(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    cache_file.write_text(_fixture_json())
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()
    result = models_dev.load_catalog()
    assert "claude-sonnet-4-6" in result
    assert result["claude-sonnet-4-6"].input == 3.0


def test_load_catalog_returns_empty_on_corrupt_json(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    cache_file.write_text("{not valid json!!!")
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()
    result = models_dev.load_catalog()
    assert result == {}


def test_load_catalog_memoized_by_mtime(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    cache_file.write_text(_fixture_json())
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()
    result1 = models_dev.load_catalog()
    # Second call with same mtime returns same object
    result2 = models_dev.load_catalog()
    assert result1 is result2


# ---------------------------------------------------------------------------
# refresh_catalog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_catalog_writes_cache(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    cache_file = tmp_path / "pricing" / "models-dev.json"
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()

    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.text = AsyncMock(return_value=_fixture_json())
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = lambda *a, **kw: mock_resp
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("pythinker_code.models_dev.new_client_session", return_value=mock_session):
        result = await models_dev.refresh_catalog(force=True)

    assert result is True
    assert cache_file.exists()
    assert "anthropic" in json.loads(cache_file.read_text())


@pytest.mark.asyncio
async def test_refresh_catalog_noop_within_ttl(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    cache_file.write_text(_fixture_json())
    # mtime is fresh (just written)
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()

    with patch("pythinker_code.models_dev.new_client_session") as mock_new_session:
        result = await models_dev.refresh_catalog(force=False)

    # Cache is fresh — no network I/O should occur
    assert result is True
    mock_new_session.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_catalog_fetches_when_stale(tmp_path, monkeypatch):
    import os

    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    cache_file.write_text(_fixture_json())
    # Backdate mtime by 25 hours (beyond 24h TTL)
    stale_mtime = cache_file.stat().st_mtime - (25 * 3600)
    os.utime(cache_file, (stale_mtime, stale_mtime))
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()

    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.text = AsyncMock(return_value=_fixture_json())
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = lambda *a, **kw: mock_resp
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "pythinker_code.models_dev.new_client_session", return_value=mock_session
    ) as mock_new_session:
        result = await models_dev.refresh_catalog(force=False)

    # Stale cache — a real network fetch must have been attempted
    assert result is True
    mock_new_session.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_catalog_swallows_network_error(tmp_path, monkeypatch):
    import aiohttp

    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()

    mock_resp = AsyncMock()
    mock_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection refused"))
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = lambda *a, **kw: mock_resp
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("pythinker_code.models_dev.new_client_session", return_value=mock_session):
        result = await models_dev.refresh_catalog(force=True)

    assert result is False
    assert not cache_file.exists()


@pytest.mark.asyncio
async def test_refresh_catalog_atomic_write(tmp_path, monkeypatch):
    from pythinker_code import models_dev

    cache_file = tmp_path / "models-dev.json"
    monkeypatch.setattr(models_dev, "_get_cache_path", lambda: cache_file)
    models_dev._catalog_cache.clear()

    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.text = AsyncMock(return_value=_fixture_json())
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = lambda *a, **kw: mock_resp
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("pythinker_code.models_dev.new_client_session", return_value=mock_session):
        await models_dev.refresh_catalog(force=True)

    # No stray .tmp file left behind
    tmp_file = cache_file.with_suffix(".tmp")
    assert not tmp_file.exists()
    assert cache_file.exists()
