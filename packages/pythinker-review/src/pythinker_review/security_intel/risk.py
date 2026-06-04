from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pythinker_review.security_intel.models import (
    CVERecord,
    EPSSScore,
    ExploitIntel,
    KEVEntry,
    RiskScore,
)


def _cvss_score(record: CVERecord | None) -> float:
    if record is None:
        return 0.0
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = record.metrics.get(key, [])
        if entries and isinstance(entries, list):
            score = entries[0].get("cvssData", {}).get("baseScore")
            if score is not None:
                return float(score)
    return 0.0


def _published_date(record: CVERecord | None) -> datetime | None:
    if record is None or not record.published:
        return None
    raw = record.published
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def score_cve(
    *,
    cve_id: str,
    nvd: CVERecord | None,
    epss: EPSSScore | None,
    kev: KEVEntry | None,
    exploit: ExploitIntel | None,
) -> RiskScore:
    cvss = _cvss_score(nvd)
    epss_probability = epss.epss if epss else 0.0
    in_kev = kev is not None
    poc_confidence = exploit.confidence if exploit else "NONE"
    poc_score = {
        "WEAPONIZED": 15,
        "PUBLIC_EXPLOIT_REMOTE": 12,
        "PUBLIC_EXPLOIT": 10,
        "PUBLIC_POC_HIGH_QUALITY": 7,
        "PUBLIC_POC_LOW_QUALITY": 3,
        "NONE": 0,
    }[poc_confidence]

    base = (cvss / 10.0) * 20.0 + epss_probability * 35.0 + (30.0 if in_kev else 0.0) + poc_score
    multiplier = 1.0
    boosters: list[str] = []
    if in_kev and poc_confidence != "NONE":
        multiplier *= 1.15
        boosters.append("KEV+PoC")
    if cvss >= 9.0 and epss_probability > 0.7:
        multiplier *= 1.10
        boosters.append("CVSS>=9+EPSS>0.7")
    days_since_published: int | None = None
    if published := _published_date(nvd):
        days_since_published = (datetime.now(UTC) - published).days
        if days_since_published <= 7:
            multiplier *= 1.05
            boosters.append("Published<7days")
    risk_score = min(100.0, round(base * multiplier, 2))
    if risk_score <= 25:
        label = "LOW"
    elif risk_score <= 50:
        label = "MEDIUM"
    elif risk_score <= 75:
        label = "HIGH"
    else:
        label = "CRITICAL"
    if in_kev and epss_probability > 0.5:
        urgency = "PATCH IMMEDIATELY"
    elif in_kev:
        urgency = "PATCH WITHIN 24 HOURS"
    elif epss_probability > 0.5:
        urgency = "PATCH WITHIN 72 HOURS"
    elif cvss >= 9.0:
        urgency = "PATCH THIS WEEK"
    elif cvss >= 7.0:
        urgency = "PATCH THIS MONTH"
    else:
        urgency = "SCHEDULE FOR NEXT CYCLE"
    recommendation = _recommendation(cve_id, urgency, cvss, epss_probability, in_kev)
    components: dict[str, Any] = {
        "cvss_score": cvss,
        "epss_probability": epss_probability,
        "in_kev": in_kev,
        "poc_confidence": poc_confidence,
    }
    return RiskScore(
        cve_id=cve_id,
        risk_score=risk_score,
        risk_label=label,
        urgency=urgency,
        recommendation=recommendation,
        components=components,
        boosters_applied=boosters,
        days_since_published=days_since_published,
    )


def _recommendation(
    cve_id: str, urgency: str, cvss: float, epss_probability: float, in_kev: bool
) -> str:
    if urgency == "PATCH IMMEDIATELY":
        return f"{cve_id} is actively prioritized: KEV-listed with high EPSS; patch immediately."
    if in_kev:
        return f"{cve_id} is listed in CISA KEV; apply vendor patches within 24 hours."
    if epss_probability > 0.5:
        return (
            f"{cve_id} has high EPSS ({epss_probability:.1%}); "
            "prioritize remediation within 72 hours."
        )
    if cvss >= 9.0:
        return f"{cve_id} has critical CVSS {cvss}; schedule remediation this week."
    if cvss >= 7.0:
        return f"{cve_id} has high CVSS {cvss}; include in the next patch cycle."
    return f"{cve_id} has lower immediate risk; schedule remediation in normal maintenance."
