"""Group/split structured files into review chunks."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from pythinker_review.engine.structured_diff import StructuredFile, StructuredHunk
from pythinker_review.engine.token_budget import clip_text

VENDORED_PREFIXES: tuple[str, ...] = (
    "node_modules/",
    ".venv/",
    "venv/",
    "vendor/",
    "third_party/",
    "dist/",
    "build/",
    "out/",
    ".git/",
    ".pythinker-review/",
    "coverage/",
    "htmlcov/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "target/",
    "generated/",
    "__generated__/",
    # Root-level codegen artifacts. The matching ** globs below cover nested
    # cases; these prefixes catch the root-level case fnmatch.fnmatch misses.
    "openapi_client/",
    "openapi_server/",
)

GENERATED_GLOBS: tuple[str, ...] = (
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/*.pb.go",
    "**/*.pb.cc",
    "**/*_pb2.py",
    "**/*_pb2.pyi",
    "**/*_pb2_grpc.py",
    "**/*_grpc.py",
    "**/*Grpc.java",
    "**/*Grpc.cs",
    "**/*_grpc.ts",
    "**/*_grpc.js",
    "**/*.generated.ts",
    "**/*.generated.js",
    "**/*.graphql.ts",
    "**/openapi_client/**",
    "**/openapi_server/**",
    "**/__generated__/**",
)


@dataclass(frozen=True, slots=True)
class Chunk:
    file: str
    hunks: tuple[StructuredHunk, ...]
    rendered: str


def build_chunks(
    files: list[StructuredFile],
    *,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    skip_vendored: bool,
    budget_chars: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sf in files:
        if not _matches_filters(sf.path, includes, excludes, skip_vendored):
            continue
        if len(sf.rendered) <= budget_chars or len(sf.hunks) <= 1:
            chunks.append(Chunk(file=sf.path, hunks=sf.hunks, rendered=sf.rendered))
        else:
            chunks.extend(_split_per_hunk(sf, budget_chars))
    return chunks


def _matches_filters(
    path: str, includes: tuple[str, ...], excludes: tuple[str, ...], skip_vendored: bool
) -> bool:
    if skip_vendored and any(path.startswith(prefix) for prefix in VENDORED_PREFIXES):
        return False
    if skip_vendored and any(fnmatch.fnmatch(path, pattern) for pattern in GENERATED_GLOBS):
        return False
    if includes and not any(fnmatch.fnmatch(path, pattern) for pattern in includes):
        return False
    return not any(fnmatch.fnmatch(path, pattern) for pattern in excludes)


def _split_per_hunk(sf: StructuredFile, budget_chars: int) -> list[Chunk]:
    out: list[Chunk] = []
    for hunk in sf.hunks:
        rendered = (
            f"## File: '{sf.path}'\n"
            f"{hunk.header}\n__new hunk__\n{hunk.new_block}\n__old hunk__\n{hunk.old_block}\n"
        )
        rendered = clip_text(rendered, budget_chars)
        out.append(Chunk(file=sf.path, hunks=(hunk,), rendered=rendered))
    return out
