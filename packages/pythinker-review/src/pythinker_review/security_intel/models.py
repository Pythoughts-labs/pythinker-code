"""Normalized vulnerability-intelligence models.

External API models use ``extra='ignore'`` because public security feeds evolve. Internal models use
``extra='forbid'`` so stored Pythinker state remains stable.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLabel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PoCConfidence = Literal[
    "WEAPONIZED",
    "PUBLIC_EXPLOIT_REMOTE",
    "PUBLIC_EXPLOIT",
    "PUBLIC_POC_HIGH_QUALITY",
    "PUBLIC_POC_LOW_QUALITY",
    "NONE",
]


class ExternalIntelModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IntelModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CVERecord(ExternalIntelModel):
    id: str
    published: str = ""
    lastModified: str = ""
    vulnStatus: str = ""
    descriptions: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    weaknesses: list[dict[str, Any]] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)


class EPSSScore(ExternalIntelModel):
    cve: str
    epss: float = Field(ge=0.0, le=1.0)
    percentile: float = Field(ge=0.0, le=1.0)
    date: str = ""


class KEVEntry(ExternalIntelModel):
    cveID: str
    vendorProject: str = ""
    product: str = ""
    vulnerabilityName: str = ""
    dateAdded: str = ""
    dueDate: str = ""
    knownRansomwareCampaignUse: str = ""


class PackageRef(IntelModel):
    name: str
    ecosystem: str
    version: str = ""
    manifest_path: str | None = None
    line: int | None = Field(default=None, ge=1)


class PackageVulnerability(IntelModel):
    id: str
    summary: str = ""
    aliases: list[str] = Field(default_factory=list)
    severity: str = "UNKNOWN"
    references: list[str] = Field(default_factory=list)


class DependencyIntel(IntelModel):
    package: PackageRef
    vuln_count: int = Field(ge=0)
    vulns: list[PackageVulnerability] = Field(default_factory=list)


class ExploitIntel(IntelModel):
    cve_id: str
    has_public_exploit: bool = False
    poc_count: int = 0
    confidence: PoCConfidence = "NONE"
    references: list[str] = Field(default_factory=list)


class VendorAdvisoryIntel(IntelModel):
    cve_id: str
    microsoft: list[dict[str, Any]] = Field(default_factory=list)
    redhat: list[dict[str, Any]] = Field(default_factory=list)
    ubuntu: list[dict[str, Any]] = Field(default_factory=list)


class RiskScore(IntelModel):
    cve_id: str
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_label: RiskLabel
    urgency: str
    recommendation: str
    components: dict[str, Any]
    boosters_applied: list[str] = Field(default_factory=list)
    days_since_published: int | None = None


class CVEIntelBundle(IntelModel):
    cve_id: str
    nvd: CVERecord | None = None
    epss: EPSSScore | None = None
    kev: KEVEntry | None = None
    exploit: ExploitIntel | None = None
    vendor: VendorAdvisoryIntel | None = None
    risk: RiskScore | None = None
    source_errors: list[str] = Field(default_factory=list)


class IntelSourceStatus(IntelModel):
    source: str
    ok: bool
    message: str = ""
