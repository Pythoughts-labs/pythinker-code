from __future__ import annotations

import asyncio
from pathlib import Path

from pythinker_review.security_intel.cache import IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import CVEIntelBundle, DependencyIntel, PackageRef
from pythinker_review.security_intel.risk import score_cve
from pythinker_review.security_intel.sources import epss, github, kev, nvd, osv, vendor
from pythinker_review.security_intel.validators import normalize_cve


def default_cache(data_root: Path) -> IntelCache:
    return IntelCache(data_root.parent / "security-intel" / "cache")


async def lookup_cve_bundle(
    cve_id: str,
    *,
    data_root: Path,
    client: IntelHttpClient | None = None,
    include_exploit: bool = True,
    include_vendor: bool = True,
) -> CVEIntelBundle:
    normalized = normalize_cve(cve_id)
    if normalized is None:
        raise ValueError("Invalid CVE ID")
    http = client or IntelHttpClient()
    cache = default_cache(data_root)
    errors: list[str] = []

    async def capture(name: str, coro):
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001 - intel sources degrade independently
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            return None

    nvd_task = capture("nvd", nvd.fetch_cve(normalized, client=http, cache=cache))
    epss_task = capture("epss", epss.get_epss([normalized], client=http, cache=cache))
    kev_task = capture("kev", kev.lookup_kev(normalized, client=http, cache=cache))
    tasks = [nvd_task, epss_task, kev_task]
    if include_exploit:
        tasks.append(
            capture(
                "github-exploit",
                github.check_exploit_availability(normalized, client=http, cache=cache),
            )
        )
    if include_vendor:
        tasks.append(
            capture("vendor", vendor.get_vendor_advisory(normalized, client=http, cache=cache))
        )
    results = await asyncio.gather(*tasks)
    nvd_record = results[0]
    epss_scores = results[1] or []
    kev_entry = results[2]
    exploit = results[3] if include_exploit and len(results) > 3 else None
    vendor_result = results[-1] if include_vendor else None
    epss_score = epss_scores[0] if epss_scores else None
    if any(x is not None for x in (nvd_record, epss_score, kev_entry, exploit)):
        risk = score_cve(
            cve_id=normalized,
            nvd=nvd_record,
            epss=epss_score,
            kev=kev_entry,
            exploit=exploit,
        )
    else:
        risk = None
    return CVEIntelBundle(
        cve_id=normalized,
        nvd=nvd_record,
        epss=epss_score,
        kev=kev_entry,
        exploit=exploit,
        vendor=vendor_result,
        risk=risk,
        source_errors=errors,
    )


async def scan_packages(
    packages: list[PackageRef], *, data_root: Path, client: IntelHttpClient | None = None
) -> list[DependencyIntel]:
    http = client or IntelHttpClient()
    return await osv.query_packages(packages, client=http, cache=default_cache(data_root))


async def lookup_package(
    package: PackageRef, *, data_root: Path, client: IntelHttpClient | None = None
) -> DependencyIntel:
    http = client or IntelHttpClient()
    return await osv.query_package(package, client=http, cache=default_cache(data_root))
