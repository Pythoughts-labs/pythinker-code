from __future__ import annotations

from pythinker_review.security_intel.cache import TTL_EPSS, IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import EPSSScore
from pythinker_review.security_intel.validators import normalize_cve

EPSS_BASE = "https://api.first.org/data/v1/epss"
_CHUNK_SIZE = 30


async def get_epss(
    cve_ids: list[str], *, client: IntelHttpClient, cache: IntelCache
) -> list[EPSSScore]:
    out: list[EPSSScore] = []
    uncached: list[str] = []
    for cve in cve_ids:
        normalized = normalize_cve(cve)
        if normalized is None:
            raise ValueError(f"Invalid CVE ID: {cve}")
        cached = cache.get(f"epss:{normalized}")
        if cached is None:
            uncached.append(normalized)
        else:
            out.append(EPSSScore.model_validate(cached))
    for start in range(0, len(uncached), _CHUNK_SIZE):
        chunk = uncached[start : start + _CHUNK_SIZE]
        data = await client.get_json(
            EPSS_BASE, params={"cve": ",".join(chunk), "limit": len(chunk)}
        )
        for item in data.get("data", []) if isinstance(data, dict) else []:
            score = EPSSScore.model_validate(item)
            cache.set(f"epss:{score.cve}", score.model_dump(), TTL_EPSS)
            out.append(score)
    return out
