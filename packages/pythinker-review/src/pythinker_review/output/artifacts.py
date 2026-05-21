"""Render non-finding PR assistant artifacts."""

from __future__ import annotations

import json as _json

from pydantic import BaseModel
from rich.console import Console
from rich.markup import escape


def _safe(value: object) -> str:
    return escape(str(value) if value is not None else "")


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
    console.print(f"[bold]pythinker review {_safe(kind)}[/bold]  source={_safe(source_label)}")
    data = output.model_dump(by_alias=True, mode="json")
    if kind == "describe":
        console.print(f"[bold]Title:[/bold] {_safe(data.get('title', ''))}")
        types = ", ".join(data.get("type", []))
        if types:
            console.print(f"[bold]Type:[/bold] {_safe(types)}")
        labels = ", ".join(data.get("labels", []))
        if labels:
            console.print(f"[bold]Labels:[/bold] {_safe(labels)}")
        console.print("[bold]Description:[/bold]")
        console.print(_safe(data.get("description", "")))
        files = data.get("pr_files", [])
        if files:
            console.print("\n[bold]Files:[/bold]")
            for item in files:
                console.print(
                    f"- {_safe(item.get('filename'))}: {_safe(item.get('changes_title'))}"
                )
    elif kind in {"suggest", "improve"}:
        suggestions = data.get("code_suggestions", [])
        if not suggestions:
            console.print("[green]no code suggestions[/green]")
        for item in suggestions:
            line = item.get("start_line") or "?"
            score = item.get("score")
            score_suffix = f" score={score}" if score is not None else ""
            console.print(
                f"- [bold]{_safe(item.get('relevant_file'))}:{_safe(line)}[/bold] "
                f"[{_safe(item.get('label'))}{_safe(score_suffix)}] "
                f"{_safe(item.get('one_sentence_summary'))}"
            )
            console.print(f"  {_safe(item.get('suggestion_content'))}")
            if item.get("score_why"):
                console.print(f"  [dim]{_safe(item['score_why'])}[/dim]")
    elif kind == "ask":
        console.print(_safe(data.get("answer", "")))
        if data.get("limitations"):
            console.print(f"\n[dim]Limitations:[/dim] {_safe(data['limitations'])}")
    elif kind == "ask-line":
        console.print(
            f"[bold]{_safe(data.get('file'))}:{_safe(data.get('start_line'))}-"
            f"{_safe(data.get('end_line'))}[/bold]"
        )
        console.print(_safe(data.get("answer", "")))
        if data.get("limitations"):
            console.print(f"\n[dim]Limitations:[/dim] {_safe(data['limitations'])}")
    elif kind == "labels":
        console.print(_safe(", ".join(data.get("labels", [])) or "no labels"))
        if data.get("rationale"):
            console.print(f"[dim]{_safe(data['rationale'])}[/dim]")
    elif kind == "changelog":
        console.print(f"[bold]{_safe(data.get('title', ''))}[/bold]")
        console.print(_safe(data.get("entry", "")))
        for bullet in data.get("bullets", []):
            console.print(f"- {_safe(bullet)}")
        if data.get("migration_notes"):
            console.print(f"[dim]Migration notes:[/dim] {_safe(data['migration_notes'])}")
    elif kind == "docs":
        suggestions = data.get("docs_suggestions", [])
        if not suggestions:
            console.print("[green]no documentation gaps detected[/green]")
        for item in suggestions:
            target = f" ({item.get('target_symbol')})" if item.get("target_symbol") else ""
            line = f":{item.get('relevant_line')}" if item.get("relevant_line") else ""
            placement = f" — {item.get('doc_placement')}" if item.get("doc_placement") else ""
            console.print(
                f"- [bold]{_safe(item.get('relevant_file'))}{_safe(line)}"
                f"{_safe(target)}[/bold]{_safe(placement)}: {_safe(item.get('docs_gap'))}"
            )
            console.print(f"  {_safe(item.get('suggested_doc'))}")
    elif kind == "compliance":
        console.print(f"[bold]Overall:[/bold] {_safe(data.get('overall_status', 'unknown'))}")
        if data.get("ticket_summary"):
            console.print(f"[dim]Ticket:[/dim] {_safe(data['ticket_summary'])}")
        checks = data.get("checks", [])
        if not checks:
            console.print("[yellow]no compliance checks returned[/yellow]")
        for item in checks:
            status = item.get("status", "unknown")
            files = ", ".join(item.get("evidence_files", []))
            suffix = f" ({files})" if files else ""
            console.print(
                f"- [bold]{_safe(status)}[/bold] {_safe(item.get('title'))}{_safe(suffix)}"
            )
            console.print(f"  {_safe(item.get('rationale'))}")
            missing = item.get("missing_requirements", [])
            for requirement in missing:
                console.print(f"  [red]missing:[/red] {_safe(requirement)}")
        for risk in data.get("risks", []):
            console.print(f"[dim]Risk:[/dim] {_safe(risk)}")
    elif kind == "help-docs":
        if not data.get("question_is_relevant", True):
            console.print("[yellow]question was not answerable from the provided docs[/yellow]")
        console.print(_safe(data.get("response", "")))
        references = data.get("relevant_sections", [])
        if references:
            console.print("\n[bold]Relevant sources:[/bold]")
            for item in references:
                heading = item.get("relevant_section_header_string") or "whole file"
                console.print(f"- {_safe(item.get('file_name'))} — {_safe(heading)}")
    elif kind == "similar-issues":
        matches = data.get("matches", [])
        if not matches:
            console.print("[green]no similar local issues found[/green]")
        for item in matches:
            console.print(
                f"- [bold]{_safe(item.get('title'))}[/bold] "
                f"({_safe(item.get('path'))}, score={_safe(item.get('score'))})"
            )
            if item.get("snippet"):
                console.print(f"  {_safe(item.get('snippet'))}")
    else:
        console.print_json(data=_json.loads(_json.dumps(data)))
    return buf.getvalue()


__all__ = ["render_artifact_json", "render_artifact_pretty"]
