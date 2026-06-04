from __future__ import annotations

from pathlib import Path

from pythinker_review.security_intel.models import DependencyIntel, PackageRef, PackageVulnerability
from pythinker_review.security_scan.dependencies import (
    DependencyScanReport,
    parse_dependency_manifests,
    read_dependency_report,
    write_dependency_report,
)


def test_parse_dependency_manifests_reads_python_and_node(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.28.0\nflask\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"lodash":"^4.17.20","@scope/pkg":"1.0.0"}}', encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["pydantic>=2.0"]\n', encoding="utf-8"
    )

    packages = parse_dependency_manifests(tmp_path)
    keys = {(pkg.ecosystem, pkg.name, pkg.version) for pkg in packages}

    assert ("PyPI", "requests", "2.28.0") in keys
    assert ("PyPI", "flask", "") in keys
    assert ("npm", "lodash", "4.17.20") in keys
    assert ("npm", "@scope/pkg", "1.0.0") in keys
    assert ("PyPI", "pydantic", "") in keys
    assert any(pkg.manifest_path == "requirements.txt" and pkg.line == 1 for pkg in packages)


def test_parse_requirements_strips_extras(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "requests[socks]==2.31.0\nurllib3[secure]\n", encoding="utf-8"
    )
    packages = parse_dependency_manifests(tmp_path)
    names = {pkg.name for pkg in packages}
    assert "requests" in names
    assert "urllib3" in names
    assert not any("[" in pkg.name for pkg in packages)


def test_dependency_report_roundtrip(tmp_path: Path) -> None:
    report = DependencyScanReport.model_validate(
        {
            "projectId": "repo",
            "packageCount": 1,
            "vulnerableCount": 1,
            "dependencies": [
                DependencyIntel(
                    package=PackageRef(
                        name="lodash",
                        ecosystem="npm",
                        version="4.17.20",
                        manifest_path="package.json",
                        line=3,
                    ),
                    vuln_count=1,
                    vulns=[
                        PackageVulnerability(
                            id="GHSA-xxxx",
                            summary="prototype pollution",
                            severity="HIGH",
                        )
                    ],
                ).model_dump()
            ],
        }
    )

    write_dependency_report(report, data_root=tmp_path)
    loaded = read_dependency_report("repo", data_root=tmp_path)

    assert loaded is not None
    assert loaded.vulnerable_count == 1
    assert loaded.dependencies[0].package.name == "lodash"
