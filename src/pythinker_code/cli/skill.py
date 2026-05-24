from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from pythinker_host.path import HostPath

from pythinker_code.config import load_config
from pythinker_code.skill import discover_skills_from_roots, index_skills, resolve_skills_roots
from pythinker_code.skill.lockfile import (
    LOCKFILE_NAME,
    build_skill_lock,
    load_skill_lock,
    verify_skill_lock,
    write_skill_lock,
)

cli = typer.Typer(help="Inspect and lock Pythinker skills.")


def _resolve_project_path(work_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else work_dir / path


async def _discover(work_dir: Path):
    config = load_config()
    roots = await resolve_skills_roots(
        HostPath.unsafe_from_local_path(work_dir),
        merge_brands=config.merge_all_available_skills,
        extra_skill_dirs=config.extra_skill_dirs or None,
    )
    return index_skills(await discover_skills_from_roots(roots))


@cli.command("list")
def list_skills(
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", exists=True, file_okay=False, dir_okay=True),
    ] = Path("."),
) -> None:
    """List discovered skills for a working directory."""
    work_dir = work_dir.resolve()

    async def _run() -> None:
        skills = await _discover(work_dir)
        if skills and not (work_dir / LOCKFILE_NAME).exists():
            typer.echo(
                f"Warning: discovered {len(skills)} skill(s) but no {LOCKFILE_NAME} in {work_dir}.",
                err=True,
            )
        for skill in sorted(skills.values(), key=lambda item: item.name):
            typer.echo(f"{skill.name}\t{skill.scope}\t{skill.skill_md_file}")

    asyncio.run(_run())


@cli.command("lock")
def lock_skills(
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", exists=True, file_okay=False, dir_okay=True),
    ] = Path("."),
    output: Annotated[Path, typer.Option("--output", "-o")] = Path(LOCKFILE_NAME),
) -> None:
    """Write a skills-lock.json file for currently discovered skills."""
    work_dir = work_dir.resolve()

    async def _run() -> None:
        skills = await _discover(work_dir)
        lock = await build_skill_lock(skills, project_root=work_dir)
        output_path = _resolve_project_path(work_dir, output)
        write_skill_lock(output_path, lock)
        typer.echo(f"Wrote {output_path} with {len(lock.skills)} skill(s).")

    asyncio.run(_run())


@cli.command("verify-lock")
def verify_lock(
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", exists=True, file_okay=False, dir_okay=True),
    ] = Path("."),
    lockfile: Annotated[Path, typer.Option("--lockfile", "-l")] = Path(LOCKFILE_NAME),
) -> None:
    """Verify discovered skills against a skills-lock.json file."""
    work_dir = work_dir.resolve()

    async def _run() -> None:
        lockfile_path = _resolve_project_path(work_dir, lockfile)
        if not lockfile_path.exists():
            typer.echo(f"Lockfile not found: {lockfile_path}", err=True)
            raise typer.Exit(code=1)
        skills = await _discover(work_dir)
        errors = await verify_skill_lock(skills, load_skill_lock(lockfile_path))
        if errors:
            for error in errors:
                typer.echo(error, err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Verified {lockfile_path}.")

    asyncio.run(_run())
