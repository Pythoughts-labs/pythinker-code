"""Asyncio fan-out over (chunk, pass) work items. Fail-closed by default."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.code_review import run_code_review_pass
from pythinker_review.reviewers.debug_review import run_debug_review_pass
from pythinker_review.reviewers.schema import RawFinding
from pythinker_review.reviewers.security_review import run_security_review_pass
from pythinker_review.signals.models import Signal
from pythinker_review.store.models import ChunkFailure, Pass


@dataclass(frozen=True, slots=True)
class TaggedFinding:
    pass_: Pass
    finding: RawFinding


@dataclass(frozen=True, slots=True)
class RunnerResult:
    chunks_total: int
    chunks_done: int
    chunks_failed: int
    findings: tuple[TaggedFinding, ...] = field(default_factory=tuple)
    chunk_failures: tuple[ChunkFailure, ...] = field(default_factory=tuple)
    failed: bool = False
    cancelled: bool = False


async def run_chunks(
    *,
    chunks: list[Chunk],
    passes: tuple[Pass, ...],
    signals_by_file: dict[str, list[Signal]],
    diagnostics_by_file: dict[str, str],
    llm: ReviewLLM,
    jobs: int,
    per_chunk_timeout_s: float,
    allow_partial: bool,
) -> RunnerResult:
    work: list[tuple[Chunk, Pass]] = [(chunk, p) for chunk in chunks for p in passes]
    if not work:
        return RunnerResult(0, 0, 0)

    sem = asyncio.Semaphore(max(1, jobs))
    findings: list[TaggedFinding] = []
    failures: list[ChunkFailure] = []
    chunks_done = 0
    cancelled = False

    async def one(chunk: Chunk, p: Pass) -> None:
        nonlocal chunks_done
        async with sem:
            try:
                if p == "code_review":
                    res = await run_code_review_pass(
                        chunk=chunk, llm=llm, timeout_s=per_chunk_timeout_s
                    )
                elif p == "security_review":
                    res = await run_security_review_pass(
                        chunk=chunk,
                        signals=signals_by_file.get(chunk.file, []),
                        llm=llm,
                        timeout_s=per_chunk_timeout_s,
                    )
                else:
                    diagnostic = (
                        diagnostics_by_file.get(chunk.file)
                        or diagnostics_by_file.get("*")
                        or "No diagnostic input provided."
                    )
                    res = await run_debug_review_pass(
                        chunk=chunk,
                        diagnostic=diagnostic,
                        llm=llm,
                        timeout_s=per_chunk_timeout_s,
                    )
                if res.ok:
                    findings.extend(TaggedFinding(p, finding) for finding in res.findings)
                else:
                    failures.append(
                        ChunkFailure.model_validate(
                            {
                                "file": chunk.file,
                                "reason": res.failure_reason or "worker_error",
                                "message": res.failure_message,
                                "pass": p,
                            }
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - worker boundary
                failures.append(
                    ChunkFailure.model_validate(
                        {
                            "file": chunk.file,
                            "reason": "worker_error",
                            "message": str(exc),
                            "pass": p,
                        }
                    )
                )
            finally:
                chunks_done += 1

    tasks = [asyncio.create_task(one(chunk, p)) for chunk, p in work]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        cancelled = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    return RunnerResult(
        chunks_total=len(work),
        chunks_done=chunks_done,
        chunks_failed=len(failures),
        findings=tuple(findings),
        chunk_failures=tuple(failures),
        failed=(not allow_partial) and bool(failures),
        cancelled=cancelled,
    )
