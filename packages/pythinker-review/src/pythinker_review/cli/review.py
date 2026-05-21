"""Standalone `pythinker-review` Typer entry."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import typer

from pythinker_review.cli._shared import FailOn, OutputFormat, exit_code
from pythinker_review.engine.diff_source import DiffMode, EmptyDiffError, PreflightError
from pythinker_review.engine.orchestrator import EngineRunInput, EngineRunOutput, run_engine
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.output.json import render_json
from pythinker_review.output.pretty import render_pretty
from pythinker_review.output.sarif import render_sarif
from pythinker_review.store.findings_store import FindingsStore
from pythinker_review.store.gitignore import ensure_gitignored
from pythinker_review.store.models import Finding, Pass, RunMeta

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _resolve_llm() -> ReviewLLM:
    fake = os.environ.get("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES")
    if fake is not None:
        return FakeReviewLLM(scripted=fake.split("\0") if fake else ['{"findings": []}'])
    typer.secho(
        "No active model configured. Set PYTHINKER_REVIEW_FAKE_LLM_RESPONSES for tests, "
        "or invoke via `pythinker review` for the Pythinker-integrated path.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=3)


def _emit(fmt: OutputFormat, *, meta: RunMeta, findings: list[Finding], no_color: bool) -> str:
    if fmt is OutputFormat.json:
        return render_json(meta, findings)
    if fmt is OutputFormat.sarif:
        return render_sarif(meta, findings)
    return render_pretty(meta, findings, no_color=no_color)


def _mode_from_flags(*, range_: str | None, working_tree: bool, staged: bool) -> DiffMode:
    if range_:
        return DiffMode.range
    if working_tree:
        return DiffMode.working_tree
    if staged:
        return DiffMode.staged
    return DiffMode.base


def _save_output(output: EngineRunOutput, *, repo: Path) -> None:
    store = FindingsStore(repo_root=repo)
    store.begin(output.meta)
    for finding in output.findings:
        store.append(finding)
    store.write_diff(output.meta.id, output.resolved.patch_text)
    store.finalize(output.meta)
    ensure_gitignored(repo_root=repo)


def _run_review_engine(inputs: EngineRunInput) -> EngineRunOutput:
    return asyncio.run(run_engine(llm=_resolve_llm(), inputs=inputs))


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
    quiet: bool = typer.Option(False, "--quiet"),
    include: list[str] = typer.Option([], "--include"),
    exclude: list[str] = typer.Option([], "--exclude"),
    no_skip_vendored: bool = typer.Option(False, "--no-skip-vendored"),
    with_security: bool = typer.Option(False, "--with-security"),
    chunk_budget_chars: int = typer.Option(12_000, "--chunk-budget-chars", min=500),
    per_chunk_timeout_s: float = typer.Option(120.0, "--per-chunk-timeout-s", min=1.0),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    passes: tuple[Pass, ...]
    passes = ("code_review", "security_review") if with_security else ("code_review",)
    resolved_repo = repo.resolve()
    inputs = EngineRunInput(
        repo=resolved_repo,
        mode=_mode_from_flags(range_=range_, working_tree=working_tree, staged=staged),
        base_ref=base,
        rev_range=range_,
        passes=passes,
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
        output = _run_review_engine(inputs)
    except EmptyDiffError as exc:
        typer.secho(f"no changes to review: {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2) from exc
    except PreflightError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    if save:
        _save_output(output, repo=resolved_repo)
    typer.echo(_emit(fmt, meta=output.meta, findings=output.findings, no_color=quiet))
    raise typer.Exit(
        code=exit_code(meta=output.meta, findings=output.findings, fail_on=fail_on, llm_error=False)
    )


@app.command(name="list")
def list_runs(
    limit: int = typer.Option(20, "--limit", min=1),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    import json as _json

    idx = repo / ".pythinker-review" / "index.json"
    if not idx.exists():
        typer.echo("no runs")
        raise typer.Exit(code=0)
    parsed = _json.loads(idx.read_text(encoding="utf-8"))
    runs = parsed.get("runs", [])[:limit]
    for item in runs:
        if isinstance(item, dict):
            typer.echo(
                f"{item.get('id')}  {item.get('status')}  "
                f"findings={item.get('findings_count')}  branch={item.get('branch')}"
            )


@app.command()
def show(
    run_id: str,
    fmt: OutputFormat = typer.Option(OutputFormat.pretty, "--format"),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    run_dir = repo / ".pythinker-review" / "runs" / run_id
    if not run_dir.exists():
        typer.secho(f"unknown run: {run_id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    meta = RunMeta.model_validate_json((run_dir / "meta.json").read_text(encoding="utf-8"))
    findings: list[Finding] = []
    findings_file = run_dir / "findings.jsonl"
    if findings_file.exists():
        for line in findings_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                findings.append(Finding.model_validate_json(line))
    typer.echo(_emit(fmt, meta=meta, findings=findings, no_color=False))


__all__: Sequence[str] = ("app", "_resolve_llm", "_emit")
