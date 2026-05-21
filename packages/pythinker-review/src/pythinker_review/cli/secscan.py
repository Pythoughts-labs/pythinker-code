"""Standalone `pythinker-secscan` Typer entry."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from pythinker_review.cli import review as review_mod
from pythinker_review.cli._shared import FailOn, OutputFormat, exit_code
from pythinker_review.engine.diff_source import EmptyDiffError, PreflightError
from pythinker_review.engine.orchestrator import EngineRunInput

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Security-only review commands."""


@app.command()
def diff(
    base: str = typer.Option("origin/main", "--base"),
    staged: bool = typer.Option(False, "--staged"),
    working_tree: bool = typer.Option(False, "--working-tree"),
    range_: str | None = typer.Option(None, "--range"),
    fmt: OutputFormat = typer.Option(
        OutputFormat.pretty if sys.stdout.isatty() else OutputFormat.json, "--format"
    ),
    fail_on: FailOn = typer.Option(FailOn.high, "--fail-on"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
    jobs: int = typer.Option(4, "--jobs", min=1),
    save: bool = typer.Option(True, "--save/--no-save"),
    no_color: bool = typer.Option(
        False, "--no-color", help="Disable ANSI colors in pretty output."
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Deprecated alias for --no-color. Will be removed in a future release.",
        hidden=True,
    ),
    include: list[str] = typer.Option([], "--include"),
    exclude: list[str] = typer.Option([], "--exclude"),
    no_skip_vendored: bool = typer.Option(False, "--no-skip-vendored"),
    chunk_budget_chars: int = typer.Option(12_000, "--chunk-budget-chars", min=500),
    per_chunk_timeout_s: float = typer.Option(120.0, "--per-chunk-timeout-s", min=1.0),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    if quiet:
        typer.secho(
            "warning: --quiet is deprecated; use --no-color instead.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        no_color = no_color or quiet
    resolved_repo = repo.resolve()
    inputs = EngineRunInput(
        repo=resolved_repo,
        mode=review_mod._mode_from_flags(range_=range_, working_tree=working_tree, staged=staged),
        base_ref=base,
        rev_range=range_,
        passes=("security_review",),
        diagnostics_by_file={},
        includes=tuple(include),
        excludes=tuple(exclude),
        skip_vendored=not no_skip_vendored,
        jobs=jobs,
        per_chunk_timeout_s=per_chunk_timeout_s,
        chunk_budget_chars=chunk_budget_chars,
        allow_partial=allow_partial,
    )
    try:
        output = review_mod._run_review_engine(inputs)
    except EmptyDiffError as exc:
        typer.secho(f"no changes to review: {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2) from exc
    except PreflightError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    if save:
        review_mod._save_output(output, repo=resolved_repo)
    typer.echo(review_mod._emit(fmt, meta=output.meta, findings=output.findings, no_color=no_color))
    raise typer.Exit(
        code=exit_code(meta=output.meta, findings=output.findings, fail_on=fail_on, llm_error=False)
    )
