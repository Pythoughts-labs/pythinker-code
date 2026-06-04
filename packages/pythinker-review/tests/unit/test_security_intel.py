from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_review.security_intel.cache import IntelCache
from pythinker_review.security_intel.models import CVERecord, EPSSScore, ExploitIntel
from pythinker_review.security_intel.risk import score_cve
from pythinker_review.security_intel.validators import (
    normalize_cve,
    sanitize_url_for_log,
    validate_ip_address,
)


def test_normalize_cve_and_reject_private_ip() -> None:
    assert normalize_cve("cve-2024-12345") == "CVE-2024-12345"
    assert normalize_cve("not-a-cve") is None

    with pytest.raises(ValueError):
        validate_ip_address("127.0.0.1")


def test_sanitize_url_for_log_redacts_tokens() -> None:
    redacted = sanitize_url_for_log("https://example.test/?api_key=secret&access_token=tok")
    assert "api_key=secret" not in redacted
    assert "access_token=tok" not in redacted
    assert redacted.count("***REDACTED***") == 2


def test_intel_cache_roundtrip(tmp_path: Path) -> None:
    cache = IntelCache(tmp_path)
    cache.set("k", {"v": 1}, ttl=60)

    assert cache.get("k") == {"v": 1}


def test_risk_score_combines_cvss_epss_kev_and_poc() -> None:
    nvd = CVERecord.model_validate(
        {
            "id": "CVE-2024-0001",
            "published": "2024-01-01T00:00:00.000",
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]
            },
        }
    )
    epss = EPSSScore(cve="CVE-2024-0001", epss=0.8, percentile=0.99, date="2024-01-02")
    exploit = ExploitIntel(
        cve_id="CVE-2024-0001",
        has_public_exploit=True,
        poc_count=1,
        confidence="PUBLIC_EXPLOIT",
        references=["https://github.com/example/poc"],
    )

    result = score_cve(cve_id="CVE-2024-0001", nvd=nvd, epss=epss, kev=None, exploit=exploit)

    assert result.risk_label in {"HIGH", "CRITICAL"}
    assert result.components["epss_probability"] == 0.8
    assert "CVSS>=9+EPSS>0.7" in result.boosters_applied
