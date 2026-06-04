"""`pythinker-security-scan` — Python-native Pythinker Security Scan repo scanner and processor."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import typer

from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.security_intel.models import PackageRef
from pythinker_review.security_intel.service import lookup_cve_bundle, lookup_package
from pythinker_review.security_scan.dependencies import (
    parse_dependency_manifests,
    read_dependency_report,
    scan_project_dependencies,
)
from pythinker_review.security_scan.matchers import create_default_registry
from pythinker_review.security_scan.paths import DEFAULT_STATE_DIR, get_data_root
from pythinker_review.security_scan.processor import (
    process_project,
    revalidate_project,
    triage_project,
)
from pythinker_review.security_scan.prompt import assemble_prompt, batch_languages
from pythinker_review.security_scan.reporting import (
    export_findings,
    project_status,
    render_markdown_report,
    write_report,
)
from pythinker_review.security_scan.reporting import (
    metrics as project_metrics,
)
from pythinker_review.security_scan.scanner import scan_project
from pythinker_review.security_scan.store import (
    ensure_project,
    load_all_file_records,
    purge_stale_projects,
    read_info,
    read_project_settings,
    write_info,
)
from pythinker_review.security_scan.tech import detect_tech, read_tech_json, write_tech_json

app = typer.Typer(add_completion=False, no_args_is_help=True)
deps_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Dependency vulnerability intelligence."
)
intel_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="CVE and package intelligence lookups."
)
app.add_typer(deps_app, name="deps")
app.add_typer(intel_app, name="intel")


def _resolve_llm() -> ReviewLLM:
    fake = os.environ.get("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES")
    if fake is not None:
        return FakeReviewLLM(scripted=fake.split("\0") if fake else ["[]"])
    typer.secho(
        "No active model configured. Invoke via `pythinker security-scan ...` or set "
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES for tests.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=3)


def _data_root(root: Path, state_dir: str) -> Path:
    env_data = os.environ.get("PYTHINKER_SECURITY_SCAN_DATA_ROOT")
    if env_data:
        return get_data_root(None).resolve()
    state = Path(state_dir)
    if not state.is_absolute():
        state = root.resolve() / state
    return (state / "data").resolve()


def _project_id(root: Path, project_id: str | None) -> str:
    if project_id:
        return project_id
    name = root.resolve().name
    return "project" if name in {"", "/"} else name.replace(" ", "-")


@deps_app.command("list")
def deps_list(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List dependency manifest entries Pythinker can enrich via OSV."""
    packages = parse_dependency_manifests(root.resolve())
    if json_output:
        typer.echo(json.dumps([pkg.model_dump(exclude_none=True) for pkg in packages], indent=2))
        return
    if not packages:
        typer.echo("No supported dependency manifests found.")
        return
    for pkg in packages:
        loc = f" ({pkg.manifest_path}:{pkg.line})" if pkg.manifest_path and pkg.line else ""
        typer.echo(f"{pkg.ecosystem}/{pkg.name} {pkg.version or '(unversioned)'}{loc}")


@deps_app.command("scan")
def deps_scan(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Scan dependency manifests with OSV and store dependency intelligence."""
    root = root.resolve()
    pid = _project_id(root, project_id)
    report = asyncio.run(
        scan_project_dependencies(project_id=pid, root=root, data_root=_data_root(root, state_dir))
    )
    payload = report.model_dump(by_alias=True)
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(
        f"Dependency scan complete: {report.package_count} packages, "
        f"{report.vulnerable_count} vulnerable dependencies"
    )
    for item in report.dependencies:
        vulns = ", ".join(v.id for v in item.vulns[:3])
        typer.echo(f"- {item.package.ecosystem}/{item.package.name}: {vulns}")
    for error in report.source_errors:
        typer.secho(error, fg=typer.colors.YELLOW, err=True)


@deps_app.command("report")
def deps_report(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
) -> None:
    """Print the stored dependency-intelligence report."""
    root = root.resolve()
    report = read_dependency_report(
        _project_id(root, project_id), data_root=_data_root(root, state_dir)
    )
    if report is None:
        typer.secho(
            "No dependency report found. Run `pythinker security-scan deps scan` first.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(report.model_dump_json(by_alias=True, indent=2))


@intel_app.command("cve")
def intel_cve(
    cve_id: str = typer.Argument(...),
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
) -> None:
    """Look up CVE intelligence from NVD, EPSS, KEV, GitHub PoC, and vendor feeds."""
    bundle = asyncio.run(lookup_cve_bundle(cve_id, data_root=_data_root(root.resolve(), state_dir)))
    typer.echo(bundle.model_dump_json(exclude_none=True, indent=2))


@intel_app.command("package")
def intel_package(
    name: str = typer.Argument(...),
    ecosystem: str = typer.Option(..., "--ecosystem"),
    version: str = typer.Option("", "--version"),
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
) -> None:
    """Look up package vulnerability intelligence via OSV."""
    package = PackageRef(name=name, ecosystem=ecosystem, version=version)
    result = asyncio.run(lookup_package(package, data_root=_data_root(root.resolve(), state_dir)))
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def init(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    force_info: bool = typer.Option(False, "--force-info"),
) -> None:
    """Initialize a Pythinker Security Scan data mirror for a repository."""
    root = root.resolve()
    pid = _project_id(root, project_id)
    data_root = _data_root(root, state_dir)
    ensure_project(pid, root, data_root=data_root)
    detected = detect_tech(root)
    write_tech_json(pid, detected, data_root=data_root)
    info_path = data_root / pid / "INFO.md"
    if force_info or not info_path.exists():
        write_info(pid, _default_info(pid, detected.tags), data_root=data_root)
    removed = purge_stale_projects(data_root=data_root, keep_project_id=pid)
    if removed:
        typer.secho(
            f"purged stale project data: {', '.join(removed)}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    typer.echo(
        json.dumps(
            {"projectId": pid, "dataRoot": str(data_root), "techTags": detected.tags},
            indent=2,
        )
    )


@app.command()
def scan(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    matcher: list[str] = typer.Option([], "--matcher", help="Run only this matcher slug."),
    ignore: list[str] = typer.Option([], "--ignore", help="Extra ignore glob."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run deterministic matcher scan and write FileRecords."""
    root = root.resolve()
    pid = _project_id(root, project_id)
    data_root = _data_root(root, state_dir)
    result = scan_project(
        project_id=pid,
        root=root,
        data_root=data_root,
        matcher_slugs=matcher or None,
        ignore_paths=ignore or None,
        on_progress=None if json_output else lambda p: typer.echo(p.message, err=True),
    )
    payload = {
        "projectId": pid,
        "runId": result.run_id,
        "filesScanned": result.files_scanned,
        "filesWithCandidates": result.files_with_candidates,
        "candidateCount": result.candidate_count,
        "activeMatchers": result.active_matchers,
        "skippedMatchers": result.skipped_matchers,
        "languageStats": [asdict(s) for s in result.language_stats],
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(
            f"Pythinker Security Scan scan complete: {result.files_with_candidates} files, "
            f"{result.candidate_count} candidates (run {result.run_id})"
        )


@app.command()
def process(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    limit: int | None = typer.Option(None, "--limit", min=1),
    batch_size: int = typer.Option(5, "--batch-size", min=1),
    jobs: int = typer.Option(1, "--jobs", min=1),
    timeout_s: float = typer.Option(180.0, "--timeout-s", min=1.0),
    reinvestigate: bool = typer.Option(False, "--reinvestigate"),
) -> None:
    """Investigate pending candidate files with the active Pythinker model."""
    root = root.resolve()
    pid = _project_id(root, project_id)
    result = asyncio.run(
        process_project(
            project_id=pid,
            data_root=_data_root(root, state_dir),
            llm=_resolve_llm(),
            limit=limit,
            batch_size=batch_size,
            jobs=jobs,
            timeout_s=timeout_s,
            reinvestigate=reinvestigate,
        )
    )
    typer.echo(json.dumps(asdict(result), indent=2))


@app.command()
def revalidate(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    force: bool = typer.Option(False, "--force"),
    limit: int | None = typer.Option(None, "--limit", min=1),
    timeout_s: float = typer.Option(180.0, "--timeout-s", min=1.0),
) -> None:
    """Re-check stored findings for true/false-positive/fixed verdicts."""
    root = root.resolve()
    result = asyncio.run(
        revalidate_project(
            project_id=_project_id(root, project_id),
            data_root=_data_root(root, state_dir),
            llm=_resolve_llm(),
            force=force,
            limit=limit,
            timeout_s=timeout_s,
        )
    )
    typer.echo(json.dumps(asdict(result), indent=2))


@app.command()
def triage(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    severity: str = typer.Option("MEDIUM", "--severity"),
    limit: int | None = typer.Option(None, "--limit", min=1),
    timeout_s: float = typer.Option(120.0, "--timeout-s", min=1.0),
) -> None:
    """Classify findings by remediation priority."""
    root = root.resolve()
    result = asyncio.run(
        triage_project(
            project_id=_project_id(root, project_id),
            data_root=_data_root(root, state_dir),
            llm=_resolve_llm(),
            severity=severity,
            limit=limit,
            timeout_s=timeout_s,
        )
    )
    typer.echo(json.dumps(asdict(result), indent=2))


@app.command()
def status(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
) -> None:
    """Show project mirror status."""
    root = root.resolve()
    payload = project_status(_project_id(root, project_id), data_root=_data_root(root, state_dir))
    typer.echo(json.dumps(asdict(payload), indent=2))


@app.command()
def report(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    write: bool = typer.Option(False, "--write"),
) -> None:
    """Render a Markdown report, optionally writing reports/report.{md,json}."""
    root = root.resolve()
    pid = _project_id(root, project_id)
    data_root = _data_root(root, state_dir)
    if write:
        md_path, json_path = write_report(pid, data_root=data_root)
        typer.echo(json.dumps({"markdown": str(md_path), "json": str(json_path)}, indent=2))
    else:
        typer.echo(render_markdown_report(pid, data_root=data_root))


@app.command()
def metrics(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
) -> None:
    """Print finding counts by severity, slug, and revalidation verdict."""
    root = root.resolve()
    typer.echo(
        json.dumps(
            project_metrics(_project_id(root, project_id), data_root=_data_root(root, state_dir)),
            indent=2,
        )
    )


@app.command(name="export")
def export_cmd(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    fmt: Literal["json", "md-dir"] = typer.Option("json", "--format"),
    out: Path = typer.Option(Path("security-scan-findings.json"), "--out"),
) -> None:
    """Export findings as JSON or one Markdown file per finding."""
    root = root.resolve()
    written = export_findings(
        _project_id(root, project_id), data_root=_data_root(root, state_dir), fmt=fmt, out=out
    )
    typer.echo(str(written))


@app.command()
def matchers(json_output: bool = typer.Option(False, "--json")) -> None:
    """List security matcher slugs."""
    registry = create_default_registry()
    payload = [
        {
            "slug": matcher.slug,
            "description": matcher.description,
            "noiseTier": matcher.noise_tier,
            "filePatterns": matcher.file_patterns,
            "sourceFile": matcher.source_file,
            "patternCount": len(matcher.patterns),
        }
        for matcher in registry.get_all()
    ]
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        for matcher in payload:
            typer.echo(
                f"{matcher['slug']} ({matcher['noiseTier']}, {matcher['patternCount']} patterns)"
            )


@app.command(name="prompt")
def prompt_cmd(
    root: Path = typer.Option(Path.cwd(), "--root", "--repo", exists=True, file_okay=False),
    project_id: str | None = typer.Option(None, "--project-id"),
    state_dir: str = typer.Option(DEFAULT_STATE_DIR, "--state-dir"),
    limit: int = typer.Option(3, "--limit", min=1),
) -> None:
    """Preview the assembled system+user prompt for pending records."""
    root = root.resolve()
    pid = _project_id(root, project_id)
    data_root = _data_root(root, state_dir)
    records = [r for r in load_all_file_records(pid, data_root=data_root) if r.candidates][:limit]
    detected = read_tech_json(pid, data_root=data_root) or detect_tech(root)
    settings = read_project_settings(pid, data_root=data_root)
    assembly = assemble_prompt(
        detected_tags=detected.tags,
        batch_slugs=sorted({c.vuln_slug for record in records for c in record.candidates}),
        batch_languages=batch_languages(records),
        project_info=read_info(pid, data_root=data_root),
        prompt_append=settings.prompt_append,
        records=records,
        project_root=root,
    )
    typer.echo("# SYSTEM\n\n" + assembly.system + "\n\n# USER\n\n" + assembly.user)


def _default_info(project_id: str, tags: list[str]) -> str:
    return f"""# {project_id} security context

- Detected tech: {", ".join(tags) if tags else "unknown"}
- Auth primitives: Fill in project-specific auth/permission helpers.
- Trust boundaries: Fill in public endpoints, queues, webhooks, jobs, agent tools,
  and external integrations.
- Sensitive data: Fill in user, tenant, secret, payment, and privileged resources.
- Project-specific false-positive notes: Add framework wrappers or generated paths
  Pythinker Security Scan should ignore.
"""
