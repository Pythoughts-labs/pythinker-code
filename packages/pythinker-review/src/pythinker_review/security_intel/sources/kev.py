from __future__ import annotations

from pythinker_review.security_intel.cache import TTL_KEV, IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import KEVEntry
from pythinker_review.security_intel.validators import normalize_cve

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
KEV_FALLBACK = "https://raw.githubusercontent.com/cisagov/kev-data/main/data/known_exploited_vulnerabilities.json"


async def fetch_kev_catalog(*, client: IntelHttpClient, cache: IntelCache) -> list[KEVEntry]:
    cached = cache.get("kev:catalog")
    if cached is not None:
        return [KEVEntry.model_validate(item) for item in cached]
    last_error: Exception | None = None
    for url in (CISA_KEV_URL, KEV_FALLBACK):
        try:
            data = await client.get_json(url)
            if not isinstance(data, dict) or not isinstance(data.get("vulnerabilities"), list):
                raise ValueError(f"Unexpected KEV catalog shape from {url}")
            entries = [KEVEntry.model_validate(item) for item in data["vulnerabilities"]]
            cache.set("kev:catalog", [entry.model_dump() for entry in entries], TTL_KEV)
            return entries
        except Exception as exc:  # noqa: BLE001 - fallback source boundary
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


async def lookup_kev(cve_id: str, *, client: IntelHttpClient, cache: IntelCache) -> KEVEntry | None:
    normalized = normalize_cve(cve_id)
    if normalized is None:
        raise ValueError("Invalid CVE ID")
    catalog = await fetch_kev_catalog(client=client, cache=cache)
    return next((entry for entry in catalog if entry.cveID == normalized), None)
