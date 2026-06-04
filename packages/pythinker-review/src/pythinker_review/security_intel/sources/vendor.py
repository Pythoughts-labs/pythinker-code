from __future__ import annotations

from pythinker_review.security_intel.cache import TTL_VENDOR, IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import VendorAdvisoryIntel
from pythinker_review.security_intel.validators import normalize_cve

MSRC_SUG_URL = "https://api.msrc.microsoft.com/sug/v2.0/en-US/vulnerability"
REDHAT_SECURITY_BASE = "https://access.redhat.com/hydra/rest/securitydata"
UBUNTU_SECURITY_BASE = "https://ubuntu.com/security/cves"


async def get_vendor_advisory(
    cve_id: str, *, client: IntelHttpClient, cache: IntelCache
) -> VendorAdvisoryIntel:
    normalized = normalize_cve(cve_id)
    if normalized is None:
        raise ValueError("Invalid CVE ID")
    key = f"vendor:{normalized}"
    cached = cache.get(key)
    if cached is not None:
        return VendorAdvisoryIntel.model_validate(cached)
    microsoft, redhat, ubuntu = (
        await _msrc(normalized, client),
        await _redhat(normalized, client),
        await _ubuntu(normalized, client),
    )
    result = VendorAdvisoryIntel(
        cve_id=normalized, microsoft=microsoft, redhat=redhat, ubuntu=ubuntu
    )
    cache.set(key, result.model_dump(), TTL_VENDOR)
    return result


async def _msrc(cve_id: str, client: IntelHttpClient) -> list[dict]:
    try:
        data = await client.get_json(MSRC_SUG_URL, params={"$filter": f"cveNumber eq '{cve_id}'"})
    except Exception:  # noqa: BLE001 - best-effort enrichment
        return []
    out: list[dict] = []
    for entry in data.get("value", [])[:20] if isinstance(data, dict) else []:
        out.append(
            {
                "title": entry.get("cveTitle", ""),
                "severity": entry.get("severity", ""),
                "impact": entry.get("impact", ""),
                "article_url": entry.get("articleUrl1", ""),
                "release_date": entry.get("releaseDate", ""),
            }
        )
    return out


async def _redhat(cve_id: str, client: IntelHttpClient) -> list[dict]:
    try:
        data = await client.get_json(f"{REDHAT_SECURITY_BASE}/cve/{cve_id}.json")
    except Exception:  # noqa: BLE001 - best-effort enrichment
        return []
    if not isinstance(data, dict):
        return []
    out: list[dict] = []
    for release in data.get("affected_release", [])[:20]:
        out.append(
            {
                "product_name": release.get("product_name", ""),
                "advisory": release.get("advisory", ""),
                "package": release.get("package", ""),
                "release_date": release.get("release_date", ""),
                "severity": data.get("threat_severity", ""),
            }
        )
    return out


async def _ubuntu(cve_id: str, client: IntelHttpClient) -> list[dict]:
    try:
        data = await client.get_json(f"{UBUNTU_SECURITY_BASE}/{cve_id}.json")
    except Exception:  # noqa: BLE001 - best-effort enrichment
        return []
    if not isinstance(data, dict):
        return []
    status = data.get("status", [])
    if isinstance(status, list):
        return [item for item in status[:20] if isinstance(item, dict)]
    return []
