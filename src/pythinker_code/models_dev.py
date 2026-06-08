from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from pythinker_code.utils.aiohttp import new_client_session
from pythinker_code.utils.logging import logger

_MODELS_DEV_URL = "https://models.dev/api.json"
_TTL_SECONDS = 86_400  # 24 hours

# Canonical providers win over regional/cloud variants when the same
# bare model id appears under multiple providers.
_CANONICAL_PROVIDERS = {
    "anthropic", "openai", "google", "deepseek", "z-ai",
    "moonshot", "minimax", "meta", "mistral", "cohere", "x-ai",
}

# Module-level lock: only one network fetch runs at a time.
_refresh_lock = asyncio.Lock()

# In-process memo: (mtime_ns, catalog_dict)
_catalog_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class ModelPrice:
    input: float        # USD / 1M tokens
    output: float
    cache_read: float   # 0.0 if absent
    cache_write: float  # 0.0 if absent


def _get_cache_path() -> Path:
    """Return ~/.pythinker/model-pricing/models-dev.json (or $PYTHINKER_DIR variant)."""
    base = Path(os.environ.get("PYTHINKER_DIR") or Path.home() / ".pythinker")
    return base / "model-pricing" / "models-dev.json"


def _coerce_cost(value: object) -> float:
    """Coerce a cost field to float; returns 0.0 for None, raises on non-numeric."""
    if value is None:
        return 0.0
    return float(value)


def _flatten_catalog(raw: dict[str, Any]) -> dict[str, ModelPrice]:
    """Flatten provider→models hierarchy into {model_id: ModelPrice}.

    Canonical providers win over regional/compat variants.
    Model ids containing '@' (version-tagged) are excluded.
    context_over_200k tiered pricing is ignored.
    Models with any non-numeric cost field are skipped.
    """
    canonical: dict[str, ModelPrice] = {}
    fallback: dict[str, ModelPrice] = {}

    for provider_id, provider_data in raw.items():
        if not isinstance(provider_data, dict):
            continue
        models = provider_data.get("models")
        if not isinstance(models, dict):
            continue
        target = canonical if provider_id in _CANONICAL_PROVIDERS else fallback
        for model_id, model_data in sorted(models.items()):
            if "@" in model_id:
                continue
            if not isinstance(model_data, dict):
                continue
            cost = model_data.get("cost")
            if not isinstance(cost, dict):
                continue
            try:
                price = ModelPrice(
                    input=_coerce_cost(cost.get("input")),
                    output=_coerce_cost(cost.get("output")),
                    cache_read=_coerce_cost(cost.get("cache_read")),
                    cache_write=_coerce_cost(cost.get("cache_write")),
                )
            except (TypeError, ValueError):
                continue
            if model_id not in target:
                target[model_id] = price

    merged = {**fallback, **canonical}
    return merged


def load_catalog() -> dict[str, ModelPrice]:
    """Sync. Return flattened {model_id: ModelPrice} from disk cache.

    Returns {} when no cache file exists or the file is unreadable/corrupt.
    Memoises by file mtime_ns — re-parses only after a successful refresh.
    """
    cache_path = _get_cache_path()
    try:
        mtime_ns = cache_path.stat().st_mtime_ns
    except OSError:
        return {}

    cached = _catalog_cache.get("entry")
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]  # type: ignore[return-value]

    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    result = _flatten_catalog(raw)
    _catalog_cache["entry"] = (mtime_ns, result)
    return result


async def _do_fetch(cache_path: Path) -> bool:
    """Inner fetch — separated so tests can patch it."""
    tmp_path = cache_path.with_suffix(".tmp")
    try:
        async with (
            new_client_session() as session,
            session.get(
                _MODELS_DEV_URL,
                timeout=aiohttp.ClientTimeout(total=10),
                raise_for_status=True,
            ) as resp,
        ):
            text = await resp.text()
        # Validate it's parseable JSON before writing.
        json.loads(text)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, cache_path)
        return True
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        logger.debug("models.dev fetch failed: {error}", error=exc)
        return False


async def refresh_catalog(*, force: bool = False) -> bool:
    """Async. Fetch models.dev/api.json if cache is missing or stale (>24h).

    Returns True when cache is valid (fresh or just refreshed), False on
    network/write failure. Never raises.
    """
    cache_path = _get_cache_path()
    if not force:
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < _TTL_SECONDS:
                return True
        except OSError:
            pass

    async with _refresh_lock:
        if not force:
            try:
                age = time.time() - cache_path.stat().st_mtime
                if age < _TTL_SECONDS:
                    return True
            except OSError:
                pass
        return await _do_fetch(cache_path)
