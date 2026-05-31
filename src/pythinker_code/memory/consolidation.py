from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from loguru import logger
from pythinker_host.path import HostPath

from pythinker_code.memory.recall import gather_candidates
from pythinker_code.memory.recap import content_hash
from pythinker_code.project_memory import ProjectMemoryStore


@dataclass(frozen=True, slots=True)
class InboxCandidate:
    id: str
    target: str
    title: str
    content: str
    source_path: str
    content_hash: str


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", value.lower())[:32].strip("-") or "candidate"


def _memory_entry_hash(content: str) -> str:
    return content_hash(tier="memory", title=content[:60], body=content)


async def inbox_dir(store: ProjectMemoryStore) -> Path:
    root = await store.ensure_root()
    path = root / "memory" / "inbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def list_inbox_candidates(store: ProjectMemoryStore) -> list[InboxCandidate]:
    directory = await inbox_dir(store)
    out: list[InboxCandidate] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(InboxCandidate(**data))
        except Exception as exc:
            logger.debug("inbox candidate {} dropped during listing: {!r}", path.name, exc)
            continue
    return out


async def generate_inbox_candidates(
    store: ProjectMemoryStore, work_dir: HostPath, *, limit: int = 20
) -> list[InboxCandidate]:
    """Stage scratch/journal candidates for approval-gated durable memory consolidation."""
    existing_entries = [*await store.read_entries("memory"), *await store.read_entries("user")]
    existing_hashes = {_memory_entry_hash(entry) for entry in existing_entries}
    inbox_candidates = await list_inbox_candidates(store)
    staged = {candidate.content_hash for candidate in inbox_candidates}
    staged.update(_memory_entry_hash(candidate.content) for candidate in inbox_candidates)
    directory = await inbox_dir(store)
    candidates: list[InboxCandidate] = []
    for block in await gather_candidates(store, work_dir):
        if block.tier in {"memory", "user"}:
            continue
        digest = _memory_entry_hash(block.content)
        if digest in existing_hashes or digest in staged:
            continue
        candidate = InboxCandidate(
            id=_safe_id(digest),
            target="memory",
            title=block.title or block.tier,
            content=block.content,
            source_path=block.source_path,
            content_hash=digest,
        )
        path = directory / f"{candidate.id}.json"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # A file with this id already exists on disk but was absent from
            # ``staged`` (e.g. it is corrupt and was skipped during listing).
            # Treat it as already staged instead of crashing the whole harvest.
            staged.add(digest)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(candidate), fh, ensure_ascii=False, indent=2)
        candidates.append(candidate)
        staged.add(digest)
        if len(candidates) >= limit:
            break
    return candidates


async def approve_inbox_candidate(store: ProjectMemoryStore, candidate_id: str) -> str:
    directory = await inbox_dir(store)
    path = directory / f"{_safe_id(candidate_id)}.json"
    if not path.is_file():
        return "Candidate not found."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        candidate = InboxCandidate(**data)
    except Exception as exc:
        logger.warning(
            "inbox candidate {} rejected on approve due to parse error: {!r}",
            path.name,
            exc,
        )
        return "Candidate file is corrupt and cannot be approved."
    result = await store.add("memory", candidate.content)
    if not result.ok:
        return result.message
    path.unlink(missing_ok=True)
    return "Candidate approved and added to project memory."


async def reject_inbox_candidate(store: ProjectMemoryStore, candidate_id: str) -> str:
    directory = await inbox_dir(store)
    path = directory / f"{_safe_id(candidate_id)}.json"
    if not path.is_file():
        return "Candidate not found."
    path.unlink(missing_ok=True)
    return "Candidate rejected."
