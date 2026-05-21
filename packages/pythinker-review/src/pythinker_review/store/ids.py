"""Sortable run IDs of the form YYYYMMDDHHMMSS-<8 hex chars>."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


def generate_run_id(*, now: datetime | None = None) -> str:
    when = now or datetime.now(tz=UTC)
    stamp = when.strftime("%Y%m%d%H%M%S")
    return f"{stamp}-{secrets.token_hex(4)}"


def parse_run_id_timestamp(run_id: str) -> datetime:
    if "-" not in run_id:
        raise ValueError(f"Invalid run ID format: {run_id!r}")
    stamp, _hex = run_id.split("-", 1)
    if len(_hex) != 8 or not all(ch in "0123456789abcdef" for ch in _hex.lower()):
        raise ValueError(f"Invalid run ID suffix: {run_id!r}")
    try:
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp in run ID {run_id!r}: {e}") from e
