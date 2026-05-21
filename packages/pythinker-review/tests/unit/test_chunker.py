from pythinker_review.engine.chunker import build_chunks
from pythinker_review.engine.structured_diff import StructuredFile, StructuredHunk


def _sf(path: str, body: str = "  X") -> StructuredFile:
    h = StructuredHunk(header="@@ -1,1 +1,1 @@", new_block=f"1 +{body}", old_block="-old")
    return StructuredFile(path=path, rendered=f"## File: '{path}'\n{body}", hunks=(h,))


def test_one_chunk_per_file_by_default() -> None:
    chunks = build_chunks(
        [_sf("src/a.py"), _sf("src/b.py")],
        includes=(),
        excludes=(),
        skip_vendored=True,
        budget_chars=10_000,
    )
    assert [c.file for c in chunks] == ["src/a.py", "src/b.py"]


def test_exclude_glob_drops_file() -> None:
    chunks = build_chunks(
        [_sf("src/a.py"), _sf("tests/b.py")],
        includes=(),
        excludes=("tests/**",),
        skip_vendored=True,
        budget_chars=10_000,
    )
    assert [c.file for c in chunks] == ["src/a.py"]


def test_include_filter_keeps_only_matching() -> None:
    chunks = build_chunks(
        [_sf("src/a.py"), _sf("docs/b.md")],
        includes=("src/**",),
        excludes=(),
        skip_vendored=True,
        budget_chars=10_000,
    )
    assert [c.file for c in chunks] == ["src/a.py"]


def test_vendored_skipped_by_default() -> None:
    chunks = build_chunks(
        [_sf("node_modules/x/index.js"), _sf("src/a.py"), _sf(".venv/lib/y.py")],
        includes=(),
        excludes=(),
        skip_vendored=True,
        budget_chars=10_000,
    )
    assert [c.file for c in chunks] == ["src/a.py"]


def test_oversized_file_split_per_hunk() -> None:
    h1 = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +A" * 200, old_block="")
    h2 = StructuredHunk(header="@@ -10 +10 @@", new_block="10 +B" * 200, old_block="")
    sf = StructuredFile(path="src/big.py", rendered="x" * 10_000, hunks=(h1, h2))
    chunks = build_chunks([sf], includes=(), excludes=(), skip_vendored=True, budget_chars=500)
    assert len(chunks) == 2
    assert all(c.file == "src/big.py" for c in chunks)
