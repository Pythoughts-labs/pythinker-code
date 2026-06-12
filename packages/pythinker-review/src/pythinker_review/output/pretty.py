"""Pretty TTY rendering via rich."""

from __future__ import annotations

import io

from rich.console import Console

from pythinker_review.store.models import SEVERITY_ORDER, Finding, RunMeta

_SEV_COLOR = {
    "critical": "bright_red",
    "high": "red",
    "medium": "yellow",
    "low": "blue",
    "info": "dim",
}


def render_pretty(meta: RunMeta, findings: list[Finding], *, no_color: bool = False) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=not no_color, no_color=no_color, width=120)
    console.print(
        f"[bold]pythinker review[/bold] run [cyan]{meta.id}[/cyan]  "
        f"status={meta.status}  findings={meta.findings_count}"
    )
    if meta.fallback_reason:
        console.print(f"[yellow]warning:[/yellow] base fallback: {meta.fallback_reason}")
    if meta.chunks_failed:
        console.print(
            f"[yellow]warning:[/yellow] {meta.chunks_failed} chunk(s) failed "
            f"(allow_partial={meta.allow_partial})"
        )
    if not findings:
        console.print("[green]no findings ≥ threshold[/green]")
        return buf.getvalue()

    ordered = sorted(
        findings,
        key=lambda finding: (
            -SEVERITY_ORDER[finding.severity],
            finding.location.file,
            finding.location.start_line,
        ),
    )
    last_file: str | None = None
    for finding in ordered:
        if finding.location.file != last_file:
            console.print(f"\n[bold]{finding.location.file}[/bold]")
            last_file = finding.location.file
        severity = finding.severity.value.upper()
        color = _SEV_COLOR[finding.severity.value]
        console.print(
            f"  [{color}]{severity:8}[/{color}] "
            f"{finding.location.file}:{finding.location.start_line}  "
            f"[bold]{finding.title}[/bold]  [{finding.rule_id}]"
        )
        console.print(f"    {finding.rationale}")
        if finding.confidence_reason:
            console.print(f"    [dim]confidence:[/dim] {finding.confidence_reason}")
        if finding.exploitability:
            console.print(f"    [dim]exploitability:[/dim] {finding.exploitability}")
        if finding.test_analysis:
            console.print(f"    [dim]tests:[/dim] {finding.test_analysis}")
        if finding.suggested_regression_test:
            console.print(f"    [dim]regression test:[/dim] {finding.suggested_regression_test}")
        if finding.minimum_fix_scope:
            console.print(f"    [dim]minimum scope:[/dim] {finding.minimum_fix_scope}")
        if finding.suggestion:
            console.print(f"    [dim]suggestion:[/dim] {finding.suggestion.summary}")
    return buf.getvalue()
