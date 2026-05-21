"""Render non-finding PR assistant artifacts."""

from __future__ import annotations

import json as _json

from pydantic import BaseModel
from rich.console import Console


def render_artifact_json(kind: str, output: BaseModel, *, metadata: dict[str, str]) -> str:
    return _json.dumps(
        {
            "kind": kind,
            "metadata": metadata,
            "result": output.model_dump(by_alias=True, mode="json"),
        },
        indent=2,
    )


def render_artifact_pretty(kind: str, output: BaseModel, *, metadata: dict[str, str]) -> str:
    from io import StringIO

    buf = StringIO()
    console = Console(file=buf, width=120)
    source_label = metadata.get("source_label", "unknown")
    console.print(f"[bold]pythinker review {kind}[/bold]  source={source_label}")
    data = output.model_dump(by_alias=True, mode="json")
    if kind == "describe":
        console.print(f"[bold]Title:[/bold] {data.get('title', '')}")
        types = ", ".join(data.get("type", []))
        if types:
            console.print(f"[bold]Type:[/bold] {types}")
        console.print("[bold]Description:[/bold]")
        console.print(data.get("description", ""))
        files = data.get("pr_files", [])
        if files:
            console.print("\n[bold]Files:[/bold]")
            for item in files:
                console.print(f"- {item.get('filename')}: {item.get('changes_title')}")
    elif kind in {"suggest", "improve"}:
        suggestions = data.get("code_suggestions", [])
        if not suggestions:
            console.print("[green]no code suggestions[/green]")
        for item in suggestions:
            line = item.get("start_line") or "?"
            console.print(
                f"- [bold]{item.get('relevant_file')}:{line}[/bold] "
                f"[{item.get('label')}] {item.get('one_sentence_summary')}"
            )
            console.print(f"  {item.get('suggestion_content')}")
    elif kind == "ask":
        console.print(data.get("answer", ""))
        if data.get("limitations"):
            console.print(f"\n[dim]Limitations:[/dim] {data['limitations']}")
    elif kind == "labels":
        console.print(", ".join(data.get("labels", [])) or "no labels")
        if data.get("rationale"):
            console.print(f"[dim]{data['rationale']}[/dim]")
    elif kind == "changelog":
        console.print(f"[bold]{data.get('title', '')}[/bold]")
        console.print(data.get("entry", ""))
        for bullet in data.get("bullets", []):
            console.print(f"- {bullet}")
        if data.get("migration_notes"):
            console.print(f"[dim]Migration notes:[/dim] {data['migration_notes']}")
    elif kind == "docs":
        suggestions = data.get("docs_suggestions", [])
        if not suggestions:
            console.print("[green]no documentation gaps detected[/green]")
        for item in suggestions:
            target = f" ({item.get('target_symbol')})" if item.get("target_symbol") else ""
            console.print(
                f"- [bold]{item.get('relevant_file')}{target}[/bold]: {item.get('docs_gap')}"
            )
            console.print(f"  {item.get('suggested_doc')}")
    elif kind == "compliance":
        console.print(f"[bold]Overall:[/bold] {data.get('overall_status', 'unknown')}")
        if data.get("ticket_summary"):
            console.print(f"[dim]Ticket:[/dim] {data['ticket_summary']}")
        checks = data.get("checks", [])
        if not checks:
            console.print("[yellow]no compliance checks returned[/yellow]")
        for item in checks:
            status = item.get("status", "unknown")
            files = ", ".join(item.get("evidence_files", []))
            suffix = f" ({files})" if files else ""
            console.print(f"- [bold]{status}[/bold] {item.get('title')}{suffix}")
            console.print(f"  {item.get('rationale')}")
            missing = item.get("missing_requirements", [])
            for requirement in missing:
                console.print(f"  [red]missing:[/red] {requirement}")
        for risk in data.get("risks", []):
            console.print(f"[dim]Risk:[/dim] {risk}")
    else:
        console.print_json(data=_json.loads(_json.dumps(data)))
    return buf.getvalue()


__all__ = ["render_artifact_json", "render_artifact_pretty"]
