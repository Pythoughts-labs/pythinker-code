from __future__ import annotations

import os

from pythinker_review.security_intel.cache import TTL_CVE, TTL_SEARCH, IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import CVERecord
from pythinker_review.security_intel.validators import normalize_cve, sanitize_keyword

NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
MAX_SEARCH_LIMIT = 50


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if key := os.environ.get("NVD_API_KEY"):
        headers["apiKey"] = key
    return headers


async def fetch_cve(cve_id: str, *, client: IntelHttpClient, cache: IntelCache) -> CVERecord | None:
    normalized = normalize_cve(cve_id)
    if normalized is None:
        raise ValueError("Invalid CVE ID")
    key = f"nvd:cve:{normalized}"
    cached = cache.get(key)
    if cached is not None:
        return CVERecord.model_validate(cached)
    data = await client.get_json(NVD_BASE, params={"cveId": normalized}, headers=_headers())
    if not isinstance(data, dict) or data.get("totalResults", 0) == 0:
        return None
    vulnerabilities = data.get("vulnerabilities", [])
    if not vulnerabilities:
        return None
    record_data = vulnerabilities[0].get("cve", {})
    record = CVERecord.model_validate(record_data)
    cache.set(key, record.model_dump(), TTL_CVE)
    return record


async def search_cves(
    query: str,
    *,
    severity: str = "",
    limit: int = 10,
    client: IntelHttpClient,
    cache: IntelCache,
) -> list[CVERecord]:
    safe_query = sanitize_keyword(query)
    if safe_query is None:
        raise ValueError("Invalid search query")
    safe_limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    sev = severity.upper().strip()
    key = f"nvd:search:{safe_query}:{sev}:{safe_limit}"
    cached = cache.get(key)
    if cached is not None:
        return [CVERecord.model_validate(item) for item in cached]
    params: dict[str, object] = {"keywordSearch": safe_query, "resultsPerPage": safe_limit}
    if sev:
        params["cvssV3Severity"] = sev
    data = await client.get_json(NVD_BASE, params=params, headers=_headers())
    records = [
        CVERecord.model_validate(item.get("cve", {})) for item in data.get("vulnerabilities", [])
    ]
    cache.set(key, [record.model_dump() for record in records], TTL_SEARCH)
    return records
