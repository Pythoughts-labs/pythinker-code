"""Small JSON TTL cache for public security-intelligence responses."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

TTL_CVE = 14_400
TTL_SEARCH = 600
TTL_OSV = 1_800
TTL_EPSS = 3_600
TTL_KEV = 21_600
TTL_EXPLOIT = 3_600
TTL_VENDOR = 14_400
TTL_ATTACK = 86_400

_MAX_ENTRIES = 10_000


class IntelCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "cache.json"
        self._data: dict[str, dict[str, Any]] | None = None

    def get(self, key: str) -> Any | None:
        data = self._load()
        entry = data.get(key)
        if not entry:
            return None
        if float(entry.get("expires_at", 0)) < time.time():
            data.pop(key, None)
            self._save(data)
            return None
        return entry.get("value")

    def set(self, key: str, value: Any, ttl: int) -> None:
        data = self._load()
        if len(data) >= _MAX_ENTRIES:
            # Keep the entries that expire latest; this is deterministic and cheap for our size cap.
            survivors = sorted(data.items(), key=lambda item: item[1].get("expires_at", 0))[
                -(_MAX_ENTRIES - 1) :
            ]
            data = dict(survivors)
        data[key] = {"value": value, "expires_at": time.time() + ttl}
        self._save(data)

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._data is not None:
            return self._data
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            raw = {}
        self._data = raw if isinstance(raw, dict) else {}
        return self._data

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        self._data = data
