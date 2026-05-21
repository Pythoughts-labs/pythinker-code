"""Standalone `pythinker-debug` Typer entry for root-cause analysis."""

from __future__ import annotations

from pathlib import Path

import typer

from pythinker_review.cli import review as review_mod
from pythinker_review.cli._shared import OutputFormat
from pythinker_review.diagnostics.parser import parse_diagnostic
from pythinker_review.engine.diff_source import DiffMode, EmptyDiffError, PreflightError
from pythinker_review.engine.orchestrator import EngineRunInput

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Root-cause debugging commands."""


@app.command()
def failure(
    log_file: Path,
    command: str | None = typer.Option(None, "--command"),
    base: str = typer.Option("origin/main", "--base"),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--format"),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
    jobs: int = typer.Option(4, "--jobs", min=1),
    per_chunk_timeout_s: float = typer.Option(120.0, "--per-chunk-timeout-s", min=1.0),
) -> None:
    try:
        log_text = log_file.read_text(errors="replace")
    except FileNotFoundError as exc:
        typer.secho(f"log file not found: {log_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.secho(f"cannot read log file {log_file}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    try:
        diagnostic = parse_diagnostic(log_text, command=command)
    except ValueError as exc:
        typer.secho(
            f"failed to parse diagnostic from {log_file}: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2) from exc
    diagnostic_text = diagnostic.raw
    if diagnostic.command:
        diagnostic_text = f"Reproduction command: {diagnostic.command}\n\n{diagnostic_text}"
    inputs = EngineRunInput(
        repo=repo.resolve(),
        mode=DiffMode.base,
        base_ref=base,
        rev_range=None,
        passes=("debug_review",),
        diagnostics_by_file={"*": diagnostic_text},
        includes=(),
        excludes=(),
        skip_vendored=True,
        jobs=jobs,
        per_chunk_timeout_s=per_chunk_timeout_s,
        chunk_budget_chars=12_000,
        allow_partial=False,
    )
    try:
        output = review_mod._run_review_engine(inputs)
    except EmptyDiffError as exc:
        typer.secho(f"no changes to correlate: {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2) from exc
    except PreflightError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(review_mod._emit(fmt, meta=output.meta, findings=output.findings, no_color=False))
