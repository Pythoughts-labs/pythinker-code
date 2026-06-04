from __future__ import annotations

from pythinker_review.security_intel.cache import TTL_OSV, IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import DependencyIntel, PackageRef, PackageVulnerability
from pythinker_review.security_intel.validators import validate_ecosystem, validate_package_name

OSV_BASE = "https://api.osv.dev/v1"
_MAX_BATCH = 1_000


def _extract_severity(vuln: dict) -> str:
    db_specific = vuln.get("database_specific", {})
    if isinstance(db_specific, dict) and db_specific.get("severity"):
        return str(db_specific["severity"]).upper()
    for affected in vuln.get("affected", []):
        if not isinstance(affected, dict):
            continue
        eco = affected.get("ecosystem_specific", {})
        if isinstance(eco, dict) and eco.get("severity"):
            return str(eco["severity"]).upper()
    if vuln.get("severity"):
        return "MEDIUM"
    return "UNKNOWN"


def _summarize_vulns(vulns: list[dict]) -> list[PackageVulnerability]:
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "MEDIUM": 2, "LOW": 3}
    sorted_vulns = sorted(vulns, key=lambda v: severity_order.get(_extract_severity(v), 4))
    out: list[PackageVulnerability] = []
    for vuln in sorted_vulns[:5]:
        out.append(
            PackageVulnerability.model_validate(
                {
                    "id": vuln.get("id", ""),
                    "summary": (vuln.get("summary") or vuln.get("details") or "")[:240],
                    "aliases": vuln.get("aliases", [])[:10],
                    "severity": _extract_severity(vuln),
                    "references": [
                        r.get("url", "")
                        for r in vuln.get("references", [])[:5]
                        if isinstance(r, dict)
                    ],
                }
            )
        )
    return out


async def query_package(
    package: PackageRef, *, client: IntelHttpClient, cache: IntelCache
) -> DependencyIntel:
    package = PackageRef.model_validate(
        {
            **package.model_dump(),
            "name": validate_package_name(package.name),
            "ecosystem": validate_ecosystem(package.ecosystem),
        }
    )
    key = f"osv:pkg:{package.ecosystem}:{package.name}:{package.version}"
    cached = cache.get(key)
    if cached is not None:
        return DependencyIntel.model_validate(cached)
    payload: dict[str, object] = {"package": {"name": package.name, "ecosystem": package.ecosystem}}
    if package.version:
        payload["version"] = package.version
    data = await client.post_json(f"{OSV_BASE}/query", payload=payload)
    raw_vulns = data.get("vulns", []) if isinstance(data, dict) else []
    result = DependencyIntel(
        package=package, vuln_count=len(raw_vulns), vulns=_summarize_vulns(raw_vulns)
    )
    cache.set(key, result.model_dump(), TTL_OSV)
    return result


async def query_packages(
    packages: list[PackageRef], *, client: IntelHttpClient, cache: IntelCache
) -> list[DependencyIntel]:
    if not packages:
        return []
    output: list[DependencyIntel] = []
    for start in range(0, len(packages), _MAX_BATCH):
        batch = packages[start : start + _MAX_BATCH]
        uncached: list[PackageRef] = []
        cached_results: list[DependencyIntel] = []
        for package in batch:
            try:
                package = PackageRef.model_validate(
                    {
                        **package.model_dump(),
                        "name": validate_package_name(package.name),
                        "ecosystem": validate_ecosystem(package.ecosystem),
                    }
                )
            except ValueError:
                continue
            key = f"osv:pkg:{package.ecosystem}:{package.name}:{package.version}"
            cached = cache.get(key)
            if cached is None:
                uncached.append(package)
            else:
                cached_results.append(DependencyIntel.model_validate(cached))
        output.extend(result for result in cached_results if result.vuln_count > 0)
        if not uncached:
            continue
        queries = []
        for package in uncached:
            query: dict[str, object] = {
                "package": {"name": package.name, "ecosystem": package.ecosystem}
            }
            if package.version:
                query["version"] = package.version
            queries.append(query)
        data = await client.post_json(f"{OSV_BASE}/querybatch", payload={"queries": queries})
        results = data.get("results", []) if isinstance(data, dict) else []
        for idx, package in enumerate(uncached):
            raw_vulns = []
            if idx < len(results) and isinstance(results[idx], dict):
                raw_vulns = results[idx].get("vulns", []) or []
            result = DependencyIntel(
                package=package, vuln_count=len(raw_vulns), vulns=_summarize_vulns(raw_vulns)
            )
            cache.set(
                f"osv:pkg:{package.ecosystem}:{package.name}:{package.version}",
                result.model_dump(),
                TTL_OSV,
            )
            if result.vuln_count > 0:
                output.append(result)
    return output
