from __future__ import annotations

import os

from pythinker_review.security_intel.cache import TTL_EXPLOIT, IntelCache
from pythinker_review.security_intel.client import IntelHttpClient
from pythinker_review.security_intel.models import ExploitIntel, PoCConfidence
from pythinker_review.security_intel.validators import normalize_cve

GITHUB_REPO_SEARCH_URL = "https://api.github.com/search/repositories"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _score_repo(repo: dict) -> int:
    score = 0
    stars = int(repo.get("stargazers_count") or 0)
    if stars > 100:
        score += 3
    elif stars > 10:
        score += 2
    if not repo.get("fork", True):
        score += 2
    desc = (repo.get("description") or "").lower()
    if "exploit" in desc:
        score += 1
    if "poc" in desc:
        score += 1
    return score


def _confidence(scores: list[int]) -> PoCConfidence:
    if not scores:
        return "NONE"
    if max(scores) >= 5:
        return "PUBLIC_EXPLOIT"
    return "PUBLIC_POC_LOW_QUALITY"


async def check_exploit_availability(
    cve_id: str, *, client: IntelHttpClient, cache: IntelCache
) -> ExploitIntel:
    normalized = normalize_cve(cve_id)
    if normalized is None:
        raise ValueError("Invalid CVE ID")
    key = f"github:exploit:{normalized}"
    cached = cache.get(key)
    if cached is not None:
        return ExploitIntel.model_validate(cached)
    data = await client.get_json(
        GITHUB_REPO_SEARCH_URL,
        params={"q": f"{normalized} poc exploit", "sort": "stars", "order": "desc", "per_page": 10},
        headers=_headers(),
    )
    refs: list[str] = []
    scores: list[int] = []
    for repo in data.get("items", []) if isinstance(data, dict) else []:
        full_name = repo.get("full_name", "")
        description = repo.get("description") or ""
        if normalized.lower() not in f"{full_name} {description}".lower():
            continue
        score = _score_repo(repo)
        if score < 2:
            continue
        scores.append(score)
        if url := repo.get("html_url"):
            refs.append(str(url))
    result = ExploitIntel(
        cve_id=normalized,
        has_public_exploit=bool(refs),
        poc_count=len(refs),
        confidence=_confidence(scores),
        references=refs[:10],
    )
    cache.set(key, result.model_dump(), TTL_EXPLOIT)
    return result
