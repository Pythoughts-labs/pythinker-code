> **STATUS: DRAFT (write-stage). Finalize pass PENDING.**
> Produced by the plan-writing workflow (run `wf_40be7924-69f`) and passed structural review,
> but the automated finalize pass — which applies the *Review punch-list* appended at the end —
> was interrupted by a session usage limit (resets 2:20pm America/New_York, 2026-05-31).
> Before executing, an implementer (or a finalize re-run) MUST apply the punch-list items.

---

# Release Tool + Version Single-Source-of-Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make `pyproject.toml:3` the single authoritative version, build `scripts/release.py` to rewrite every derived file + `uv.lock` from it and open a `release/X.Y.Z` PR, and enforce the version relationship (including the frozen `pythinker-review==0.1.0` pin) with an extended dependency-check script + a new `tests/test_version_lockstep.py` that runs on every PR.

**Architecture:** `scripts/release.py` is stdlib + shells out to `git`/`gh`/`uv` (C3-exempt CI/release tooling — the shipped agent gains zero runtime deps). It is factored so all rewrite logic is pure functions (semver/monotonic validation, tomlkit rewrites with a `tomllib` parse-back assertion, CHANGELOG `## Unreleased`→`## X.Y.Z (DATE)` promotion, pattern-targeted README/asset rewrites) — those get real failing-test-first pytest; the orchestration (git/gh/uv) is verified via `--dry-run`. The lockstep test asserts every version-bearing string on every main commit; `--version` flag examples are asserted shape-only (the documented §3 exception). `update.py` gains a `PYTHINKER_MANAGED` env hook ahead of the existing brew path-sniff so P2 channels ship self-updating, with a mandatory brew-unchanged regression test.

**Tech Stack:** Python 3.12+ (stdlib `argparse`/`subprocess`/`tomllib`/`re`/`datetime` + `tomlkit` 0.15.0 already at `pyproject.toml:50`), `uv` (`/home/ai/.local/bin/uv`), `gh` CLI, pytest 9 (run via `uv run pytest`).

---

## Prerequisites (manual / operator)

P1 is purely local tooling + tests. It creates **no** GitHub Apps, **no** org/repo secrets, and **no** new repos (those are P0/P2). The only sensitive, outward-facing action is the post-merge tag push, which is the deliberate last human step under C1.

- [ ] **Operator — confirm local tooling.** `uv` must be on `PATH` (verified at `/home/ai/.local/bin/uv`) and `gh` must be authenticated (`gh auth status`). `release.py` shells out to both.
- [ ] **Operator — post-merge tag push (C1, after each release PR merges).** `release.py` does *not* push tags; it prints the exact command(s). For a pure code release: `git tag vX.Y.Z && git push origin vX.Y.Z`. When `--bump-core/--bump-host` was used, push the sub-package tags first (`git tag pythinker-core-A.B.C && git push origin pythinker-core-A.B.C`, likewise host), wait for their OIDC PyPI publish jobs to land, **then** push `vX.Y.Z`.
- [ ] **Operator — merge gate (C2).** Before merging any P1 PR, confirm the `CodeRabbit` commit status on the PR head SHA is `success`.

There are no admin/secret/App actions in P1.

---

## File Structure

**Created**
- `scripts/release.py` — the release orchestrator: 4 phases (validate → rewrite-from-SSOT + `uv lock` → local gates → branch/PR), CLI `--set-version X.Y.Z [--bump-core A.B.C] [--bump-host A.B.C] [--dry-run]`.
- `tests/test_version_lockstep.py` — stdlib+tomllib CI test (every PR): semver shape; core/host/review pins == sub-pkg versions; README heading + pip snippet; asset-name shapes == VERSION across README + linux-installer README + getting-started.md; CHANGELOG `## X (`; `--version` flag examples are valid-semver shape only.
- `tests/test_release_py.py` — unit tests for the pure functions of `scripts/release.py`.

**Modified**
- `scripts/check_pythinker_dependency_versions.py` — add a `--pythinker-review-pyproject` arg + a third `("pythinker-review", ...)` tuple so the `pythinker-review==0.1.0` pin must match `packages/pythinker-review`.
- `.github/workflows/ci-pythinker-cli.yml:253-256` — pass `--pythinker-review-pyproject` to the dep-check call (or argparse fails CI red).
- `.github/workflows/release-pythinker-cli.yml:57-60` — same new arg for the release-time dep-check call.
- `src/pythinker_code/ui/shell/update.py:95-106` — `PYTHINKER_MANAGED` env read at the top of `_detect_upgrade_command()`; brew path left unchanged.
- `tests/test_release_update_pipeline.py` — add the brew-unchanged + `PYTHINKER_MANAGED` regression tests (existing file already covers the updater).
- `docs/en/release-notes/breaking-changes.md` — add a `## Unreleased` anchor (currently absent) so `release.py`'s heading promotion is uniform across all three changelog files.
- `.agents/skills/release/SKILL.md` — repoint the `update_files`/`uv_sync` nodes at `python scripts/release.py`.

---

## Task 1 — Extend `check_pythinker_dependency_versions.py` with the `pythinker-review` tuple

**Files:**
- Modify: `scripts/check_pythinker_dependency_versions.py:43-68`
- Modify: `.github/workflows/ci-pythinker-cli.yml:253-256`
- Modify: `.github/workflows/release-pythinker-cli.yml:57-60`
- Test: `tests/test_release_py.py` (new — `subprocess`-invokes the script)

1. - [ ] Write the failing test. Create `tests/test_release_py.py` with:
   ```python
   from __future__ import annotations

   import subprocess
   import sys
   from pathlib import Path

   REPO_ROOT = Path(__file__).resolve().parents[1]
   DEP_CHECK = REPO_ROOT / "scripts" / "check_pythinker_dependency_versions.py"


   def _write(tmp_path: Path, name: str, body: str) -> Path:
       p = tmp_path / name
       p.write_text(body, encoding="utf-8")
       return p


   def _run_dep_check(*args: str) -> subprocess.CompletedProcess[str]:
       return subprocess.run(
           [sys.executable, str(DEP_CHECK), *args],
           capture_output=True,
           text=True,
       )


   def test_dep_check_passes_when_review_pin_matches(tmp_path: Path) -> None:
       root = _write(
           tmp_path,
           "root.toml",
           '[project]\nname="pythinker-code"\nversion="0.27.0"\n'
           'dependencies=["pythinker-core[contrib]==1.1.1","pythinker-host==1.0.0",'
           '"pythinker-review==0.1.0"]\n',
       )
       core = _write(tmp_path, "core.toml", '[project]\nname="pythinker-core"\nversion="1.1.1"\n')
       host = _write(tmp_path, "host.toml", '[project]\nname="pythinker-host"\nversion="1.0.0"\n')
       review = _write(tmp_path, "review.toml", '[project]\nname="pythinker-review"\nversion="0.1.0"\n')
       result = _run_dep_check(
           "--root-pyproject", str(root),
           "--pythinker-core-pyproject", str(core),
           "--pythinker-host-pyproject", str(host),
           "--pythinker-review-pyproject", str(review),
       )
       assert result.returncode == 0, result.stderr


   def test_dep_check_fails_when_review_pin_drifts(tmp_path: Path) -> None:
       root = _write(
           tmp_path,
           "root.toml",
           '[project]\nname="pythinker-code"\nversion="0.27.0"\n'
           'dependencies=["pythinker-core[contrib]==1.1.1","pythinker-host==1.0.0",'
           '"pythinker-review==0.1.0"]\n',
       )
       core = _write(tmp_path, "core.toml", '[project]\nname="pythinker-core"\nversion="1.1.1"\n')
       host = _write(tmp_path, "host.toml", '[project]\nname="pythinker-host"\nversion="1.0.0"\n')
       review = _write(tmp_path, "review.toml", '[project]\nname="pythinker-review"\nversion="0.2.0"\n')
       result = _run_dep_check(
           "--root-pyproject", str(root),
           "--pythinker-core-pyproject", str(core),
           "--pythinker-host-pyproject", str(host),
           "--pythinker-review-pyproject", str(review),
       )
       assert result.returncode == 1
       assert "pythinker-review version mismatch" in result.stderr
   ```
2. - [ ] Run it and see it fail. `uv run pytest tests/test_release_py.py -q` → both tests fail with non-zero exit because argparse rejects the unknown `--pythinker-review-pyproject` (`error: unrecognized arguments`).
3. - [ ] Add the argparse flag. In `scripts/check_pythinker_dependency_versions.py`, after `parser.add_argument("--pythinker-host-pyproject", type=Path, required=True)` (line 47), add:
   ```python
       parser.add_argument("--pythinker-review-pyproject", type=Path, required=True)
   ```
4. - [ ] Add the third tuple. Change the loop header (lines 65-68) from:
   ```python
       for name, pyproject_path in (
           ("pythinker-core", args.pythinker_core_pyproject),
           ("pythinker-host", args.pythinker_host_pyproject),
       ):
   ```
   to:
   ```python
       for name, pyproject_path in (
           ("pythinker-core", args.pythinker_core_pyproject),
           ("pythinker-host", args.pythinker_host_pyproject),
           ("pythinker-review", args.pythinker_review_pyproject),
       ):
   ```
5. - [ ] Run and see it pass. `uv run pytest tests/test_release_py.py -q` → `2 passed`.
6. - [ ] Update the CI caller. In `.github/workflows/ci-pythinker-cli.yml`, change the block at lines 253-256 from:
   ```yaml
           python scripts/check_pythinker_dependency_versions.py \
             --root-pyproject pyproject.toml \
             --pythinker-core-pyproject packages/pythinker-core/pyproject.toml \
             --pythinker-host-pyproject packages/pythinker-host/pyproject.toml
   ```
   to (append the review line):
   ```yaml
           python scripts/check_pythinker_dependency_versions.py \
             --root-pyproject pyproject.toml \
             --pythinker-core-pyproject packages/pythinker-core/pyproject.toml \
             --pythinker-host-pyproject packages/pythinker-host/pyproject.toml \
             --pythinker-review-pyproject packages/pythinker-review/pyproject.toml
   ```
7. - [ ] Update the release caller. Apply the identical 4th-line append to `.github/workflows/release-pythinker-cli.yml:57-60`.
8. - [ ] Sanity-check the real workspace passes. `python scripts/check_pythinker_dependency_versions.py --root-pyproject pyproject.toml --pythinker-core-pyproject packages/pythinker-core/pyproject.toml --pythinker-host-pyproject packages/pythinker-host/pyproject.toml --pythinker-review-pyproject packages/pythinker-review/pyproject.toml` → `ok: pythinker-code dependencies match workspace package versions`.
9. - [ ] Lint the workflows. `uvx actionlint .github/workflows/ci-pythinker-cli.yml .github/workflows/release-pythinker-cli.yml` (if `actionlint` is unavailable, fall back to `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/ci-pythinker-cli.yml .github/workflows/release-pythinker-cli.yml`) → no output / exit 0.
10. - [ ] Commit. `git switch -c p1/dep-check-review && git add scripts/check_pythinker_dependency_versions.py tests/test_release_py.py .github/workflows/ci-pythinker-cli.yml .github/workflows/release-pythinker-cli.yml && git commit -m "feat(release): enforce pythinker-review pin in dependency check"`

---

## Task 2 — `release.py` Phase-1 validation helpers (pure, TDD)

**Files:**
- Create: `scripts/release.py` (validation helpers only this task)
- Test: `tests/test_release_py.py`

1. - [ ] Write the failing test. Append to `tests/test_release_py.py`:
   ```python
   import importlib.util

   _spec = importlib.util.spec_from_file_location(
       "release_tool", REPO_ROOT / "scripts" / "release.py"
   )
   assert _spec and _spec.loader
   release_tool = importlib.util.module_from_spec(_spec)
   _spec.loader.exec_module(release_tool)


   def test_parse_semver_accepts_xyz() -> None:
       assert release_tool.parse_semver("0.28.0") == (0, 28, 0)


   def test_parse_semver_rejects_non_xyz() -> None:
       import pytest

       with pytest.raises(release_tool.ReleaseError):
           release_tool.parse_semver("0.28")
       with pytest.raises(release_tool.ReleaseError):
           release_tool.parse_semver("v0.28.0")


   def test_assert_monotonic_allows_increase() -> None:
       release_tool.assert_monotonic(current="0.27.0", target="0.28.0")


   def test_assert_monotonic_rejects_equal_or_lower() -> None:
       import pytest

       with pytest.raises(release_tool.ReleaseError):
           release_tool.assert_monotonic(current="0.27.0", target="0.27.0")
       with pytest.raises(release_tool.ReleaseError):
           release_tool.assert_monotonic(current="0.27.0", target="0.26.0")
   ```
2. - [ ] Run and see it fail. `uv run pytest tests/test_release_py.py -q` → `ModuleNotFoundError`/import error (file does not exist yet).
3. - [ ] Create the module with the validation helpers. Write `scripts/release.py`:
   ```python
   #!/usr/bin/env python3
   """Pythinker-code release orchestrator.

   Rewrites every version-derived file + uv.lock from the single source of
   truth (pyproject.toml:3), runs the same gates CI runs, and opens a
   release/X.Y.Z PR. It never pushes to main and never pushes the tag — the
   maintainer pushes the tag(s) after the PR merges (C1).

   stdlib + shells out to git/gh/uv. The shipped agent gains zero runtime deps
   (C3: CI/release-tooling exemption).
   """

   from __future__ import annotations

   import argparse
   import re
   import subprocess
   import sys
   import tomllib
   from datetime import date
   from pathlib import Path

   import tomlkit

   REPO_ROOT = Path(__file__).resolve().parents[1]
   ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
   CORE_PYPROJECT = REPO_ROOT / "packages" / "pythinker-core" / "pyproject.toml"
   HOST_PYPROJECT = REPO_ROOT / "packages" / "pythinker-host" / "pyproject.toml"
   REVIEW_PYPROJECT = REPO_ROOT / "packages" / "pythinker-review" / "pyproject.toml"

   SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


   class ReleaseError(Exception):
       """Raised when a precondition or rewrite invariant fails."""


   def parse_semver(version: str) -> tuple[int, int, int]:
       m = SEMVER_RE.match(version)
       if not m:
           raise ReleaseError(f"not a valid x.y.z version: {version!r}")
       return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


   def assert_monotonic(*, current: str, target: str) -> None:
       if parse_semver(target) <= parse_semver(current):
           raise ReleaseError(
               f"target version {target} must be strictly greater than current {current}"
           )


   def read_project_version(pyproject_path: Path) -> str:
       with pyproject_path.open("rb") as fh:
           data = tomllib.load(fh)
       version = data.get("project", {}).get("version")
       if not isinstance(version, str) or not version:
           raise ReleaseError(f"missing project.version in {pyproject_path}")
       return version
   ```
4. - [ ] Run and see it pass. `uv run pytest tests/test_release_py.py -q` → previous tests still pass + the 4 new ones pass.
5. - [ ] Commit. `git switch -c p1/release-tool && git add scripts/release.py tests/test_release_py.py && git commit -m "feat(release): add release.py validation helpers"`

---

## Task 3 — `release.py` SSOT rewrite of pyproject + sub-package pins (tomlkit + tomllib parse-back, TDD)

**Files:**
- Modify: `scripts/release.py`
- Test: `tests/test_release_py.py`

1. - [ ] Write the failing test. Append to `tests/test_release_py.py`:
   ```python
   def test_set_root_version_rewrites_and_parses_back(tmp_path: Path) -> None:
       src = (
           '[project]\nname = "pythinker-code"\nversion = "0.27.0"\n'
           'dependencies = [\n'
           '    "pythinker-core[contrib]==1.1.1",\n'
           '    "pythinker-host==1.0.0",\n'
           '    "pythinker-review==0.1.0",\n'
           ']\n'
       )
       p = tmp_path / "pyproject.toml"
       p.write_text(src, encoding="utf-8")
       release_tool.set_root_version(p, "0.28.0")
       assert release_tool.read_project_version(p) == "0.28.0"


   def test_set_dependency_pin_updates_extras_form(tmp_path: Path) -> None:
       src = (
           '[project]\nname = "x"\nversion = "0.1.0"\n'
           'dependencies = [\n    "pythinker-core[contrib]==1.1.1",\n    "rich==15.0.0",\n]\n'
       )
       p = tmp_path / "pyproject.toml"
       p.write_text(src, encoding="utf-8")
       release_tool.set_dependency_pin(p, "pythinker-core", "1.2.0")
       with p.open("rb") as fh:
           deps = tomllib.load(fh)["project"]["dependencies"]
       assert "pythinker-core[contrib]==1.2.0" in deps
       assert "rich==15.0.0" in deps  # untouched


   def test_set_dependency_pin_rejects_missing(tmp_path: Path) -> None:
       import pytest

       src = '[project]\nname="x"\nversion="0.1.0"\ndependencies=["rich==15.0.0"]\n'
       p = tmp_path / "pyproject.toml"
       p.write_text(src, encoding="utf-8")
       with pytest.raises(release_tool.ReleaseError):
           release_tool.set_dependency_pin(p, "pythinker-core", "1.2.0")
   ```
2. - [ ] Run and see it fail. `uv run pytest tests/test_release_py.py -q -k "set_root_version or set_dependency_pin"` → `AttributeError: module 'release_tool' has no attribute 'set_root_version'`.
3. - [ ] Implement the rewrites. Append to `scripts/release.py`:
   ```python
   _DEP_PIN_RE = re.compile(
       r"^(?P<name>[A-Za-z0-9._-]+)(?P<extras>\[[^\]]+\])?==(?P<ver>[^;\s]+)(?P<rest>.*)$"
   )


   def _dump_and_verify(path: Path, doc: tomlkit.TOMLDocument) -> None:
       """Write `doc` then re-read with tomllib to confirm it parses."""
       path.write_text(tomlkit.dumps(doc), encoding="utf-8")
       with path.open("rb") as fh:
           tomllib.load(fh)  # raises tomllib.TOMLDecodeError if we produced junk


   def set_root_version(pyproject_path: Path, version: str) -> None:
       parse_semver(version)
       doc = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
       doc["project"]["version"] = version  # type: ignore[index]
       _dump_and_verify(pyproject_path, doc)
       if read_project_version(pyproject_path) != version:
           raise ReleaseError(f"parse-back failed: {pyproject_path} did not re-read as {version}")


   def set_dependency_pin(pyproject_path: Path, name: str, version: str) -> None:
       """Rewrite the `name[extras]==<ver>` pin in [project].dependencies, preserving extras."""
       parse_semver(version)
       doc = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
       deps = doc["project"]["dependencies"]  # type: ignore[index]
       found = False
       for i, dep in enumerate(deps):
           m = _DEP_PIN_RE.match(str(dep))
           if m and m.group("name") == name:
               extras = m.group("extras") or ""
               rest = m.group("rest") or ""
               deps[i] = f"{name}{extras}=={version}{rest}"
               found = True
               break
       if not found:
           raise ReleaseError(f"no `=={'<ver>'}` pin for {name} in {pyproject_path}")
       _dump_and_verify(pyproject_path, doc)
       # parse-back assertion: the intended pin re-reads to the intended version
       with pyproject_path.open("rb") as fh:
           reread = tomllib.load(fh)["project"]["dependencies"]
       expected = next((d for d in reread if d.split("==")[0].split("[")[0] == name), None)
       if expected is None or expected.split("==", 1)[1].split(";")[0].strip() != version:
           raise ReleaseError(f"parse-back failed: {name} pin in {pyproject_path} != {version}")
   ```
4. - [ ] Run and see it pass. `uv run pytest tests/test_release_py.py -q -k "set_root_version or set_dependency_pin"` → `3 passed`.
5. - [ ] Commit. `git add scripts/release.py tests/test_release_py.py && git commit -m "feat(release): add tomlkit version/pin rewrites with parse-back assertions"`

---

## Task 4 — `release.py` CHANGELOG `## Unreleased` → `## X.Y.Z (DATE)` promotion (body preserved, C5, TDD)

**Files:**
- Modify: `scripts/release.py`
- Test: `tests/test_release_py.py`

1. - [ ] Write the failing test. Append to `tests/test_release_py.py`:
   ```python
   def test_promote_changelog_preserves_body_and_reinserts_unreleased(tmp_path: Path) -> None:
       src = (
           "# Changelog\n\n"
           "## Unreleased\n\n"
           "- **Did a thing.** Detail line.\n\n"
           "## 0.27.0 (2026-05-31)\n\n- Older entry.\n"
       )
       p = tmp_path / "CHANGELOG.md"
       p.write_text(src, encoding="utf-8")
       release_tool.promote_changelog(p, "0.28.0", release_date="2026-06-01")
       out = p.read_text(encoding="utf-8")
       assert "## Unreleased\n" in out  # empty anchor re-inserted
       assert "## 0.28.0 (2026-06-01)\n" in out
       assert "- **Did a thing.** Detail line." in out  # authored body preserved
       # the new dated section sits above the previous release
       assert out.index("## 0.28.0 (2026-06-01)") < out.index("## 0.27.0 (2026-05-31)")
       # the empty Unreleased anchor sits above the new dated section
       assert out.index("## Unreleased") < out.index("## 0.28.0 (2026-06-01)")


   def test_promote_changelog_empty_unreleased_is_ok(tmp_path: Path) -> None:
       src = "# Changelog\n\n## Unreleased\n\n## 0.27.0 (2026-05-31)\n\n- Older.\n"
       p = tmp_path / "CHANGELOG.md"
       p.write_text(src, encoding="utf-8")
       release_tool.promote_changelog(p, "0.28.0", release_date="2026-06-01")
       out = p.read_text(encoding="utf-8")
       assert "## 0.28.0 (2026-06-01)" in out
       assert "## Unreleased" in out


   def test_promote_changelog_missing_anchor_raises(tmp_path: Path) -> None:
       import pytest

       p = tmp_path / "CHANGELOG.md"
       p.write_text("# Changelog\n\n## 0.27.0 (2026-05-31)\n", encoding="utf-8")
       with pytest.raises(release_tool.ReleaseError):
           release_tool.promote_changelog(p, "0.28.0", release_date="2026-06-01")
   ```
2. - [ ] Run and see it fail. `uv run pytest tests/test_release_py.py -q -k promote_changelog` → `AttributeError: ... 'promote_changelog'`.
3. - [ ] Implement promotion. Append to `scripts/release.py`:
   ```python
   _UNRELEASED_RE = re.compile(r"^## Unreleased[ \t]*$", re.MULTILINE)


   def promote_changelog(path: Path, version: str, *, release_date: str) -> None:
       """Rename `## Unreleased` to `## X.Y.Z (DATE)`, preserving its body (C5),
       and re-insert a fresh empty `## Unreleased` above it.
       """
       parse_semver(version)
       text = path.read_text(encoding="utf-8")
       m = _UNRELEASED_RE.search(text)
       if m is None:
           raise ReleaseError(f"no `## Unreleased` anchor in {path}")
       # Replace the heading line in place, then prepend a new empty anchor.
       dated = f"## {version} ({release_date})"
       promoted = text[: m.start()] + dated + text[m.end() :]
       new_text = (
           promoted[: m.start()] + "## Unreleased\n\n" + promoted[m.start() :]
       )
       path.write_text(new_text, encoding="utf-8")
   ```
4. - [ ] Run and see it pass. `uv run pytest tests/test_release_py.py -q -k promote_changelog` → `3 passed`.
5. - [ ] Add the missing `## Unreleased` anchor to breaking-changes.md so promotion is uniform across all three files. In `docs/en/release-notes/breaking-changes.md`, change lines 1-5 from:
   ```
   # Breaking changes and migration

   This page documents breaking changes in Pythinker Code releases and provides migration guidance.

   ## 0.27.0 (2026-05-31)
   ```
   to:
   ```
   # Breaking changes and migration

   This page documents breaking changes in Pythinker Code releases and provides migration guidance.

   ## Unreleased

   ## 0.27.0 (2026-05-31)
   ```
6. - [ ] Commit. `git add scripts/release.py tests/test_release_py.py docs/en/release-notes/breaking-changes.md && git commit -m "feat(release): promote changelog Unreleased heading preserving body"`

---

## Task 5 — `release.py` pattern-targeted README/docs/asset rewrites (NOT a blanket replace, TDD)

**Files:**
- Modify: `scripts/release.py`
- Test: `tests/test_release_py.py`

Rewrite **only** these patterns (everything else — including the `--version 0.27.0` flag examples at README:303 and getting-started.md:34 — is left untouched, per §3): the `## 🆕 What's New in X` heading, the `pythinker-code==X` pip snippet, `PythinkerSetup-X.Y.Z.exe`, `pythinker-code_X.Y.Z_<arch>.deb`, `pythinker-code-X.Y.Z.<arch>.rpm`, and `/releases/download/vX.Y.Z/`.

1. - [ ] Write the failing test. Append to `tests/test_release_py.py`:
   ```python
   def test_rewrite_version_strings_targets_only_release_patterns() -> None:
       text = (
           "## 🆕 What's New in 0.27.0\n"
           "pip install --upgrade pythinker-code==0.27.0\n"
           "PythinkerSetup-0.27.0.exe\n"
           "pythinker-code_0.27.0_amd64.deb\n"
           "pythinker-code-0.27.0.x86_64.rpm\n"
           "releases/download/v0.27.0/pythinker-code_0.27.0_arm64.deb\n"
           "bash -s -- --version 0.27.0\n"  # flag example: MUST be preserved
       )
       out = release_tool.rewrite_version_strings(text, old="0.27.0", new="0.28.0")
       assert "## 🆕 What's New in 0.28.0" in out
       assert "pythinker-code==0.28.0" in out
       assert "PythinkerSetup-0.28.0.exe" in out
       assert "pythinker-code_0.28.0_amd64.deb" in out
       assert "pythinker-code-0.28.0.x86_64.rpm" in out
       assert "releases/download/v0.28.0/pythinker-code_0.28.0_arm64.deb" in out
       # the flag example is the documented exception — untouched
       assert "--version 0.27.0" in out
       assert "--version 0.28.0" not in out
   ```
2. - [ ] Run and see it fail. `uv run pytest tests/test_release_py.py -q -k rewrite_version_strings` → `AttributeError`.
3. - [ ] Implement targeted rewrites. Append to `scripts/release.py`:
   ```python
   def rewrite_version_strings(text: str, *, old: str, new: str) -> str:
       """Replace ONLY release-pattern occurrences of `old` with `new`.

       Deliberately skips `--version <old>` flag examples (the documented
       §3 exception) so they stay shape-only — the lockstep test enforces this.
       """
       o = re.escape(old)
       patterns = [
           (rf"(What's New in ){o}", rf"\g<1>{new}"),
           (rf"(pythinker-code==){o}", rf"\g<1>{new}"),
           (rf"(PythinkerSetup-){o}(\.exe)", rf"\g<1>{new}\g<2>"),
           (rf"(pythinker-code_){o}(_[a-z0-9]+\.deb)", rf"\g<1>{new}\g<2>"),
           (rf"(pythinker-code-){o}(\.[a-z0-9_]+\.rpm)", rf"\g<1>{new}\g<2>"),
           (rf"(releases/download/v){o}(/)", rf"\g<1>{new}\g<2>"),
       ]
       for pat, repl in patterns:
           text = re.sub(pat, repl, text)
       return text


   def rewrite_version_in_files(paths: list[Path], *, old: str, new: str) -> None:
       for path in paths:
           original = path.read_text(encoding="utf-8")
           path.write_text(rewrite_version_strings(original, old=old, new=new), encoding="utf-8")
   ```
4. - [ ] Run and see it pass. `uv run pytest tests/test_release_py.py -q -k rewrite_version_strings` → `1 passed`.
5. - [ ] Commit. `git add scripts/release.py tests/test_release_py.py && git commit -m "feat(release): pattern-targeted README/asset version rewrites"`

---

## Task 6 — `release.py` orchestration (4 phases) + `--dry-run` (verified by dry-run, not fake pytest)

**Files:**
- Modify: `scripts/release.py`
- Test: dry-run walkthrough (orchestration is git/gh/uv — no local pytest faking those)

The git/gh/uv orchestration is genuine I/O and is verified by `--dry-run` + a rehearsal in "Phase verification". `--dry-run` runs Phase 1 (validate) + prints the intended rewrites and tag order, but writes no files, runs no `uv lock`, and creates no branch/PR.

1. - [ ] Implement the phases + CLI. Append to `scripts/release.py`:
   ```python
   def _run(cmd: list[str], *, dry_run: bool, check: bool = True) -> subprocess.CompletedProcess[str]:
       if dry_run:
           print(f"[dry-run] {' '.join(cmd)}")
           return subprocess.CompletedProcess(cmd, 0, "", "")
       print(f"$ {' '.join(cmd)}")
       return subprocess.run(cmd, cwd=REPO_ROOT, text=True, check=check)


   def _git_capture(cmd: list[str]) -> str:
       return subprocess.run(
           cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=True
       ).stdout.strip()


   def validate(target: str) -> None:
       """Phase 1 — fail loud, no writes."""
       parse_semver(target)
       if _git_capture(["git", "status", "--porcelain"]):
           raise ReleaseError("working tree is not clean; commit or stash first")
       _git_capture(["git", "fetch", "origin"])
       local = _git_capture(["git", "rev-parse", "main"])
       remote = _git_capture(["git", "rev-parse", "origin/main"])
       if local != remote:
           raise ReleaseError("local main != origin/main; rebase onto origin/main first")
       assert_monotonic(current=read_project_version(ROOT_PYPROJECT), target=target)
       text = ROOT_PYPROJECT  # anchor existence is checked per changelog file in rewrite()
       changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
       m = _UNRELEASED_RE.search(changelog)
       if m is None:
           raise ReleaseError("CHANGELOG.md has no `## Unreleased` section")
       body = changelog[m.end():].split("\n## ", 1)[0].strip()
       if not body:
           print("warning: `## Unreleased` body is empty (CI-only/docs release?)")


   def rewrite(target: str, *, bump_core: str | None, bump_host: str | None) -> None:
       """Phase 2 — rewrite all derived files + regenerate uv.lock."""
       old = read_project_version(ROOT_PYPROJECT)
       set_root_version(ROOT_PYPROJECT, target)
       if bump_core:
           set_root_version(CORE_PYPROJECT, bump_core)
           set_dependency_pin(ROOT_PYPROJECT, "pythinker-core", bump_core)
       if bump_host:
           set_root_version(HOST_PYPROJECT, bump_host)
           set_dependency_pin(ROOT_PYPROJECT, "pythinker-host", bump_host)
       today = date.today().isoformat()
       for changelog in (
           REPO_ROOT / "CHANGELOG.md",
           REPO_ROOT / "docs" / "en" / "release-notes" / "changelog.md",
           REPO_ROOT / "docs" / "en" / "release-notes" / "breaking-changes.md",
       ):
           promote_changelog(changelog, target, release_date=today)
       rewrite_version_in_files(
           [
               REPO_ROOT / "README.md",
               REPO_ROOT / "packages" / "linux-installer" / "README.md",
               REPO_ROOT / "docs" / "en" / "guides" / "getting-started.md",
           ],
           old=old,
           new=target,
       )


   GATES = [
       ["python", "scripts/check_version_tag.py", "--pyproject", "pyproject.toml",
        "--expected-version", "{target}"],
       ["python", "scripts/check_pythinker_dependency_versions.py",
        "--root-pyproject", "pyproject.toml",
        "--pythinker-core-pyproject", "packages/pythinker-core/pyproject.toml",
        "--pythinker-host-pyproject", "packages/pythinker-host/pyproject.toml",
        "--pythinker-review-pyproject", "packages/pythinker-review/pyproject.toml"],
       ["uv", "sync", "--frozen", "--all-extras", "--all-packages"],
       ["uv", "run", "pytest", "tests/test_version_lockstep.py", "-q"],
   ]


   def run_gates(target: str) -> None:
       """Phase 3 — the same gates CI runs; abort before push on any failure."""
       for tmpl in GATES:
           cmd = [part.format(target=target) for part in tmpl]
           result = subprocess.run(cmd, cwd=REPO_ROOT, text=True)
           if result.returncode != 0:
               raise ReleaseError(f"local gate failed: {' '.join(cmd)}")
       # README/CHANGELOG fixed-string greps (grep -qF, not regex).
       for needle, path in (
           (f"What's New in {target}", "README.md"),
           (f"pythinker-code=={target}", "README.md"),
           (f"## {target} (", "CHANGELOG.md"),
       ):
           if subprocess.run(["grep", "-qF", needle, path], cwd=REPO_ROOT).returncode != 0:
               raise ReleaseError(f"expected string {needle!r} not found in {path}")


   def open_pr(target: str, *, bump_core: str | None, bump_host: str | None, dry_run: bool) -> None:
       """Phase 4 — branch + commit + push + PR (never main, C1)."""
       branch = f"release/{target}"
       _run(["git", "switch", "-c", branch], dry_run=dry_run)
       _run(["git", "add", "-A"], dry_run=dry_run)
       _run(["git", "commit", "-m", f"chore(release): prepare {target}"], dry_run=dry_run)
       _run(["git", "push", "-u", "origin", branch], dry_run=dry_run)
       _run(
           ["gh", "pr", "create", "--base", "main", "--head", branch,
            "--title", f"chore(release): prepare {target}",
            "--body", f"Automated release prep for {target}. Tag after merge (C1)."],
           dry_run=dry_run,
       )
       print("\nAfter the PR merges and CodeRabbit status is success, push the tag(s):")
       if bump_core:
           print(f"  git tag pythinker-core-{bump_core} && git push origin pythinker-core-{bump_core}")
       if bump_host:
           print(f"  git tag pythinker-host-{bump_host} && git push origin pythinker-host-{bump_host}")
       if bump_core or bump_host:
           print("  # wait for the sub-package OIDC publish jobs to land on PyPI, THEN:")
       print(f"  git tag v{target} && git push origin v{target}")


   def main() -> int:
       parser = argparse.ArgumentParser(description="Prepare a pythinker-code release PR.")
       parser.add_argument("--set-version", required=True, help="target X.Y.Z")
       parser.add_argument("--bump-core", default=None, help="new pythinker-core A.B.C")
       parser.add_argument("--bump-host", default=None, help="new pythinker-host A.B.C")
       parser.add_argument("--dry-run", action="store_true")
       args = parser.parse_args()

       target = args.set_version
       try:
           validate(target)
           if args.dry_run:
               print(f"[dry-run] would rewrite SSOT -> {target}"
                     + (f", core -> {args.bump_core}" if args.bump_core else "")
                     + (f", host -> {args.bump_host}" if args.bump_host else ""))
               print("[dry-run] would run: uv lock; gates; branch+PR")
               open_pr(target, bump_core=args.bump_core, bump_host=args.bump_host, dry_run=True)
               return 0
           rewrite(target, bump_core=args.bump_core, bump_host=args.bump_host)
           _run(["uv", "lock"], dry_run=False)
           run_gates(target)
           open_pr(target, bump_core=args.bump_core, bump_host=args.bump_host, dry_run=False)
       except ReleaseError as exc:
           print(f"error: {exc}", file=sys.stderr)
           return 1
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```
2. - [ ] Lint the module. `uv run ruff check scripts/release.py && uv run ruff format --check scripts/release.py` → exit 0 (run `uv run ruff format scripts/release.py` first if formatting fails). Remove the unused `text = ROOT_PYPROJECT` line flagged by ruff (delete that line in `validate`).
3. - [ ] Confirm the unit tests still pass. `uv run pytest tests/test_release_py.py -q` → all pure-function tests pass (orchestration is not under pytest).
4. - [ ] Dry-run verification (no writes). On a clean tree synced to origin/main: `python scripts/release.py --set-version 0.28.0 --dry-run`. Expected: prints `warning` only if Unreleased body is empty, then `[dry-run] would rewrite SSOT -> 0.28.0`, `[dry-run] git switch -c release/0.28.0`, ... `[dry-run] gh pr create ...`, and the tag-order block ending `git tag v0.28.0 && git push origin v0.28.0`. Confirm `git status --porcelain` is still empty afterward (dry-run wrote nothing).
5. - [ ] Commit. `git add scripts/release.py && git commit -m "feat(release): add 4-phase orchestration with uv lock + frozen-sync gate"`

---

## Task 7 — `tests/test_version_lockstep.py` (runs on every PR; equality on assets, shape on flags, TDD)

**Files:**
- Create: `tests/test_version_lockstep.py`
- Test: itself — it must pass against the current repo at `0.27.0` / core `1.1.1` / host `1.0.0` / review `0.1.0`.

This test is the CI safety net. It asserts only relationships true on every main commit (never "a tag exists").

1. - [ ] Write the test as failing-by-construction first, then make it green against the real tree. Create `tests/test_version_lockstep.py`:
   ```python
   from __future__ import annotations

   import re
   import tomllib
   from pathlib import Path

   REPO_ROOT = Path(__file__).resolve().parents[1]
   SEMVER = r"\d+\.\d+\.\d+"


   def _version(rel: str) -> str:
       with (REPO_ROOT / rel).open("rb") as fh:
           return tomllib.load(fh)["project"]["version"]


   def _root_deps() -> list[str]:
       with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
           return tomllib.load(fh)["project"]["dependencies"]


   def _pin(name: str) -> str:
       for dep in _root_deps():
           head = dep.split("==", 1)
           if len(head) == 2 and head[0].split("[")[0] == name:
               return head[1].split(";")[0].strip()
       raise AssertionError(f"no =={'<ver>'} pin for {name}")


   VERSION = _version("pyproject.toml")


   def test_version_is_semver() -> None:
       assert re.fullmatch(SEMVER, VERSION), VERSION


   def test_subpackage_pins_match_versions() -> None:
       assert _pin("pythinker-core") == _version("packages/pythinker-core/pyproject.toml")
       assert _pin("pythinker-host") == _version("packages/pythinker-host/pyproject.toml")
       assert _pin("pythinker-review") == _version("packages/pythinker-review/pyproject.toml")


   def test_review_is_frozen_at_0_1_0() -> None:
       assert _pin("pythinker-review") == "0.1.0"


   def test_readme_heading_and_pip_snippet() -> None:
       readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
       assert f"What's New in {VERSION}" in readme
       assert f"pythinker-code=={VERSION}" in readme


   def test_changelog_has_dated_heading_for_version() -> None:
       changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
       assert f"## {VERSION} (" in changelog


   def test_asset_names_match_version_across_files() -> None:
       files = [
           REPO_ROOT / "README.md",
           REPO_ROOT / "packages" / "linux-installer" / "README.md",
           REPO_ROOT / "docs" / "en" / "guides" / "getting-started.md",
       ]
       v = re.escape(VERSION)
       # Each asset shape, where present, must carry VERSION (never a stale one).
       shape_res = [
           re.compile(rf"PythinkerSetup-({SEMVER})\.exe"),
           re.compile(rf"pythinker-code_({SEMVER})_[a-z0-9]+\.deb"),
           re.compile(rf"pythinker-code-({SEMVER})\.[a-z0-9_]+\.rpm"),
           re.compile(rf"releases/download/v({SEMVER})/"),
       ]
       for path in files:
           text = path.read_text(encoding="utf-8")
           for rx in shape_res:
               for found in rx.findall(text):
                   assert found == VERSION, f"{path}: {found} != {VERSION}"


   def test_install_flag_examples_are_valid_semver_shape_only() -> None:
       # The documented §3 exception: `--version <x.y.z>` teaches flag syntax and
       # is NOT lockstepped to VERSION — only asserted to be valid semver shape.
       flag_re = re.compile(rf"--version ({SEMVER})")
       for rel in ("README.md", "docs/en/guides/getting-started.md"):
           text = (REPO_ROOT / rel).read_text(encoding="utf-8")
           for found in flag_re.findall(text):
               assert re.fullmatch(SEMVER, found), found
   ```
2. - [ ] Run against the real tree and see it pass. `uv run pytest tests/test_version_lockstep.py -q` → all pass (current repo: VERSION `0.27.0`, review pin `0.1.0`, asset names all `0.27.0`, flag examples `0.27.0` valid shape).
3. - [ ] Prove the lockstep actually bites (temporary mutation). Edit `README.md` heading to `What's New in 0.99.0`, run `uv run pytest tests/test_version_lockstep.py -q -k readme_heading` → it FAILS. Revert the edit (`git checkout README.md`), re-run → passes. This confirms the equality assertion is load-bearing.
4. - [ ] Confirm the gate set in `release.py` already invokes this test (Task 6 `GATES` includes `pytest tests/test_version_lockstep.py`). No change needed; just verify the path matches.
5. - [ ] Commit. `git add tests/test_version_lockstep.py && git commit -m "test(release): add version lockstep guard for every PR"`

---

## Task 8 — `PYTHINKER_MANAGED` env hook in `update.py` + brew-unchanged regression test (TDD)

**Files:**
- Modify: `src/pythinker_code/ui/shell/update.py:95-106`
- Test: `tests/test_release_update_pipeline.py` (append)

Brew must NOT set `PYTHINKER_MANAGED`; it keeps its existing cellar path-sniff (line 98). The env read is the literal first lines of `_detect_upgrade_command()` so non-brew managed channels (Docker/Nix/Scoop/WinGet) short-circuit to a channel-native hint while brew falls through unchanged.

1. - [ ] Write the failing tests. Append to `tests/test_release_update_pipeline.py`:
   ```python
   import pytest

   from pythinker_code.ui.shell import update as update_mod


   def test_brew_unchanged_when_pythinker_managed_unset(monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.delenv("PYTHINKER_MANAGED", raising=False)
       monkeypatch.setattr(
           update_mod.sys, "executable",
           "/opt/homebrew/Cellar/pythinker-code/0.27.0/libexec/bin/python",
       )
       monkeypatch.setattr(update_mod, "_is_native_build", lambda: False)
       assert update_mod._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


   def test_brew_unchanged_even_with_native_marker(monkeypatch: pytest.MonkeyPatch) -> None:
       # The .pythinker-native marker also trips is_native_build(); the cellar
       # path-sniff must win first so brew installs stay on `brew upgrade`.
       monkeypatch.delenv("PYTHINKER_MANAGED", raising=False)
       monkeypatch.setattr(
           update_mod.sys, "executable",
           "/opt/homebrew/Cellar/pythinker-code/0.27.0/libexec/bin/python",
       )
       monkeypatch.setattr(update_mod, "_is_native_build", lambda: True)
       assert update_mod._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


   def test_pythinker_managed_channel_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.setenv("PYTHINKER_MANAGED", "docker")
       monkeypatch.setattr(update_mod.sys, "executable", "/usr/local/bin/python")
       cmd = update_mod._detect_upgrade_command()
       assert cmd == [update_mod.MANAGED_CHANNEL_MARKER, "docker"]
   ```
2. - [ ] Run and see it fail. `uv run pytest tests/test_release_update_pipeline.py -q -k "pythinker_managed or brew_unchanged"` → `test_pythinker_managed_channel_short_circuits` fails (`AttributeError: ... MANAGED_CHANNEL_MARKER`); the brew tests fail too because the marker constant does not exist at import time.
3. - [ ] Add the marker constant. In `src/pythinker_code/ui/shell/update.py`, after the existing `NATIVE_INSTALLER_MARKER = "__pythinker_native_installer__"` (line 61), add:
   ```python
   MANAGED_CHANNEL_MARKER = "__pythinker_managed_channel__"
   ```
4. - [ ] Add the env read at the top of `_detect_upgrade_command()`. Change lines 95-99 from:
   ```python
   def _detect_upgrade_command() -> list[str]:
       """Pick the right upgrade argv based on how this interpreter was installed."""
       exe = sys.executable.replace("\\", "/").lower()
       if "/cellar/pythinker-code/" in exe or "/homebrew/cellar/pythinker-code/" in exe:
           return ["brew", "upgrade", "pythinker-code"]
   ```
   to:
   ```python
   def _detect_upgrade_command() -> list[str]:
       """Pick the right upgrade argv based on how this interpreter was installed."""
       # Channel-managed installs (Docker/Nix/Scoop/WinGet) export PYTHINKER_MANAGED
       # so the updater emits a channel-native hint instead of shelling pip/uv.
       # Brew deliberately does NOT set it — its cellar path-sniff below is the
       # load-bearing, behavior-unchanged path.
       managed = os.environ.get("PYTHINKER_MANAGED")
       if managed:
           return [MANAGED_CHANNEL_MARKER, managed]
       exe = sys.executable.replace("\\", "/").lower()
       if "/cellar/pythinker-code/" in exe or "/homebrew/cellar/pythinker-code/" in exe:
           return ["brew", "upgrade", "pythinker-code"]
   ```
   (`os` is already imported at line 5; no new import.)
5. - [ ] Run and see it pass. `uv run pytest tests/test_release_update_pipeline.py -q -k "pythinker_managed or brew_unchanged"` → `3 passed`.
6. - [ ] Confirm no regression in the existing pipeline tests + types. `uv run pytest tests/test_release_update_pipeline.py -q` → all pass; `uv run pyright src/pythinker_code/ui/shell/update.py` → 0 errors (the file is in the `strict` set at `pyproject.toml:138`).
7. - [ ] Commit. `git add src/pythinker_code/ui/shell/update.py tests/test_release_update_pipeline.py && git commit -m "feat(update): add PYTHINKER_MANAGED channel hint; keep brew unchanged"`

---

## Task 9 — Repoint the release SKILL at `scripts/release.py`

**Files:**
- Modify: `.agents/skills/release/SKILL.md` (the `update_files` and `uv_sync` nodes)

1. - [ ] Read the current nodes. `sed -n '22,40p' .agents/skills/release/SKILL.md` (the `update_files` markdown block + `uv_sync` line shown in recon).
2. - [ ] Replace the manual-bump prose. In the `update_files` node body, replace the manual "Update the relevant pyproject.toml ... CHANGELOG.md ... breaking-changes.md" instructions with: `Run python scripts/release.py --set-version X.Y.Z [--bump-core A.B.C --bump-host A.B.C]. It rewrites pyproject.toml:3, sub-package pins, uv.lock, all three changelog files (preserving the authored body), and README/asset names from the single source of truth, then runs the local gates and opens the release/X.Y.Z PR. There is no --bump-review (review is frozen at 0.1.0).` Change the `uv_sync: "Run uv sync."` node to note that `release.py` already runs `uv lock` + `uv sync --frozen --all-extras --all-packages` as Phase-2/3 steps.
3. - [ ] Verify the file still parses as the skill front-matter + d2 graph (no structural breakage): `head -5 .agents/skills/release/SKILL.md` shows the unchanged `---`/`name:`/`type:` front matter.
4. - [ ] Commit. `git add .agents/skills/release/SKILL.md && git commit -m "docs(release): repoint release skill at scripts/release.py"`

---

## Task 10 — Open the P1 PR (C1) and merge gate (C2)

**Files:** none (process)

1. - [ ] Confirm the full local gate set is green before pushing. `uv run pytest tests/test_release_py.py tests/test_version_lockstep.py tests/test_release_update_pipeline.py -q` → all pass; `uv run ruff check scripts/release.py tests/test_release_py.py tests/test_version_lockstep.py && uv run ruff format --check scripts/release.py tests/test_release_py.py tests/test_version_lockstep.py` → exit 0; `uv run pyright src/pythinker_code/ui/shell/update.py` → 0 errors.
2. - [ ] Confirm the working tree-version checks pass exactly as CI will run them: `python scripts/check_pythinker_dependency_versions.py --root-pyproject pyproject.toml --pythinker-core-pyproject packages/pythinker-core/pyproject.toml --pythinker-host-pyproject packages/pythinker-host/pyproject.toml --pythinker-review-pyproject packages/pythinker-review/pyproject.toml` → `ok: ...`.
3. - [ ] Push the branch (all P1 commits are on `p1/release-tool` after Task 2 created it; Task 1 used `p1/dep-check-review` — rebase Task 1's commit onto the same branch so it is one PR, OR open two stacked PRs. Simplest: `git switch p1/release-tool && git cherry-pick <Task-1 commit sha>` if not already included, then verify with `git log --oneline -10`). `git push -u origin p1/release-tool`.
4. - [ ] Open the PR. `gh pr create --base main --head p1/release-tool --title "feat(release): release.py + version lockstep SSOT (P1)" --body "Implements design spec §3 + §6 'Required code change'. Adds scripts/release.py, tests/test_version_lockstep.py, the pythinker-review dependency-check tuple (with both CI callers updated), and the PYTHINKER_MANAGED updater hook with a brew-unchanged regression test. No new agent runtime deps (C3)."`
5. - [ ] Wait for CI and CodeRabbit. Confirm required checks (`check`, `test`, `release-validate`) pass and the `CodeRabbit` commit status on the PR head SHA is `success` (C2) before merging. Read CodeRabbit's "Actionable comments" and resolve or surface them — do not merge past unresolved findings.
6. - [ ] Merge after C2 is satisfied. `gh pr merge p1/release-tool --squash` (the local CodeRabbit merge-gate hook enforces the status check).

---

## Phase verification

**What "done" looks like:** `pyproject.toml:3` is the only place a human edits the version; everything else is derived by `scripts/release.py` or guarded by `tests/test_version_lockstep.py`; the `pythinker-review==0.1.0` freeze is enforced in the dependency check (both CI callers updated) and the lockstep test; and `_detect_upgrade_command()` honors `PYTHINKER_MANAGED` while brew behavior is provably unchanged.

**End-to-end rehearsal (the proof, no tag pushed):**

1. - [ ] On a clean tree synced to `origin/main`, run a real (non-dry-run) rehearsal to a throwaway version: `python scripts/release.py --set-version 0.28.0`. Expected: Phase 2 rewrites the files + runs `uv lock`; Phase 3 runs all four gates (`check_version_tag`, the extended `check_pythinker_dependency_versions`, `uv sync --frozen --all-extras --all-packages`, `pytest tests/test_version_lockstep.py`) plus the `grep -qF` checks — all green; Phase 4 creates branch `release/0.28.0`, commits `chore(release): prepare 0.28.0`, pushes, and opens a PR, then prints `git tag v0.28.0 && git push origin v0.28.0`.
2. - [ ] Prove the stress-test catch is covered: confirm `uv.lock` changed in the rehearsal commit (`git show --stat release/0.28.0 | grep uv.lock`) and that `uv sync --frozen --all-extras --all-packages` ran clean inside Phase 3 (no "lockfile out of date" error). This is the exact failure that would otherwise turn the release PR's own CI red.
3. - [ ] Confirm the documented exception held: `grep -n "version 0.28.0" docs/en/guides/getting-started.md` returns nothing — the `--version 0.27.0` flag example is unchanged (still `--version 0.27.0`), while `What's New in 0.28.0`, `pythinker-code==0.28.0`, and `PythinkerSetup-0.28.0.exe` are all present.
4. - [ ] Tear down the rehearsal (no tag was pushed): `gh pr close release/0.28.0 --delete-branch` and `git switch main && git branch -D release/0.28.0` and `git push origin --delete release/0.28.0`. Verify `git log --oneline -1 origin/main` is untouched (C1: nothing reached main, no tag was created).
5. - [ ] Sub-package rehearsal (optional, validates `--bump-core`): `python scripts/release.py --set-version 0.28.0 --bump-core 1.2.0 --dry-run` → prints the ordered tag sequence (`pythinker-core-1.2.0` first, wait-for-PyPI note, then `v0.28.0`) and the intended pin rewrite `pythinker-core[contrib]==1.2.0`, writing nothing.

**Files relevant to this phase (absolute paths):**
- `/home/ai/Projects/pythinker-code-main/scripts/release.py`
- `/home/ai/Projects/pythinker-code-main/scripts/check_pythinker_dependency_versions.py`
- `/home/ai/Projects/pythinker-code-main/tests/test_version_lockstep.py`
- `/home/ai/Projects/pythinker-code-main/tests/test_release_py.py`
- `/home/ai/Projects/pythinker-code-main/tests/test_release_update_pipeline.py`
- `/home/ai/Projects/pythinker-code-main/src/pythinker_code/ui/shell/update.py`
- `/home/ai/Projects/pythinker-code-main/.github/workflows/ci-pythinker-cli.yml`
- `/home/ai/Projects/pythinker-code-main/.github/workflows/release-pythinker-cli.yml`
- `/home/ai/Projects/pythinker-code-main/docs/en/release-notes/breaking-changes.md`
- `/home/ai/Projects/pythinker-code-main/.agents/skills/release/SKILL.md`

---

## Review punch-list (apply in finalize pass)

**Verdict:** needs-fixes

**Summary:** Plan is structurally strong and spec-aligned: I verified the SSOT pins (core line 29 / host 47 / review 48, located by name per the recon header), tomlkit present (line 50), the two existing dep-check callers (ci :253-256, release :57-60), check_version_tag's --pyproject/--expected-version signature, update.py line refs (marker :61, _detect_upgrade_command :95-106, os imported :5), and the changelog/breaking-changes anchor state (breaking-changes.md has NO ## Unreleased anchor — correctly added by Task 4 step 5). I executed the promote_changelog and rewrite_version_strings logic against real file contents: both pass their tests and correctly preserve the --version flag examples (C5 / §3 exception). The lockstep test (Task 7) passes against the current 0.27.0 tree as designed. No C1-C5 violations: branch->PR->CodeRabbit->human-tag respected (C1/C2), zero new runtime deps (C3, tomlkit pre-existing), README+badges move with the bump (C4), changelog body preserved (C5); the Task 8 pyright-strict claim (:138) is accurate. Verdict needs-fixes for three blocking items: (1) MANAGED_CHANNEL_MARKER is returned but never consumed, so spec §6's channel-native hint is undelivered and any PYTHINKER_MANAGED env triggers a FileNotFoundError in _do_update — and Task 8's tests pass anyway (false confidence); (2)+(3) ruff E402 (mid-file module imports in Tasks 2 and 8) and F841 (dead v= in Task 7, plus the flagged text= in Task 6) turn the plan's own Task 10 ruff gate red. Plus a spec-coverage gap: the release/* + chore(release) <-> changelog-entry-required.yml contract is required to be asserted in a test but is not, and the install-native.sh:12 --version example is outside Task 7's flag-shape scope. Fix the marker consumption, move imports to file tops, delete the dead assignments, add the contract test, and widen the flag-shape scope to install-native.sh.


### Spec coverage gaps

- **Spec §6 'Required code change': PYTHINKER_MANAGED must yield a 'channel-native upgrade hint'. Task 8 adds MANAGED_CHANNEL_MARKER + the env read in _detect_upgrade_command(), but NEVER consumes the marker downstream. NATIVE_INSTALLER_MARKER is special-cased in three sites (update.py:613 _update_prompt_text, :719 _update_candidate_unavailable_reason, :1221 _do_update); the managed marker is parallel to none of them. Result: a managed channel renders 'Update method: __pythinker_managed_channel__ docker' and _do_update shells out ['__pythinker_managed_channel__','docker'] -> FileNotFoundError. The three Task-8 tests pass while only asserting the return value, giving false confidence; the hint spec requires is not delivered.** → Add a managed-marker case to Task 8: in _update_prompt_text() detect upgrade_command[0]==MANAGED_CHANNEL_MARKER and render a channel-native hint string; short-circuit _do_update() to print the hint and return (no shell-out), mirroring the NATIVE_INSTALLER_MARKER path. Add a test asserting the rendered hint text (not just the argv), and a test that _do_update does not call _run_upgrade_command for a managed channel.
- **Contract + Spec §2 step 6 / §9-P1: the release/* branch + chore(release) title contract with changelog-entry-required.yml must be 'documented + asserted in a test'. Verified the skip logic guards on both title 'chore(release)*' (changelog-entry-required.yml:54) and head branch release/* (:57). The plan uses branch release/{target} and title 'chore(release): prepare {target}' (correct), but adds NO test asserting this contract and no documentation beyond the PR body.** → Add a small stdlib test (e.g. in tests/test_release_py.py or test_version_lockstep.py) that reads .github/workflows/changelog-entry-required.yml and asserts both the 'chore(release)' title-skip and the 'release/*' branch-skip strings are present, and assert release.py emits the matching branch/title. Note the change-set coupling so a future edit to either side fails loudly.
- **Contract LOCKSTEP TEST: 'install-script --version flag examples are valid-semver SHAPE'. scripts/install-native.sh:12 carries a real '--version 0.27.0' example. Task 7's flag-shape assertion only scans README.md and docs/en/guides/getting-started.md, so the install-script example is uncovered.** → Add scripts/install-native.sh (and scripts/install.ps1 / scripts/install.sh if they grow version examples) to test_install_flag_examples_are_valid_semver_shape_only in Task 7. Verified now: only install-native.sh:12 carries a versioned flag example; install.ps1/install.sh do not.

### Consistency issues

- Branch juggling across tasks. Task 1 commits on p1/dep-check-review; Task 2 creates p1/release-tool; Task 10 step 3 tries to land one PR via a conditional cherry-pick of the Task-1 commit ('if not already included'). If Task 2 branched off the Task-1 branch the commit is already present and the cherry-pick errors; if off main it is not present. The plan leaves which is true unresolved. → Collapse to a single branch from Task 1 onward (e.g. create p1/release-tool in Task 1 and commit every task there). Remove the conditional cherry-pick in Task 10 step 3.
- Task 8 preamble claims 'tests/test_release_update_pipeline.py (existing file already covers the updater)'. Verified the existing file imports only re + pathlib and asserts workflow YAML text (prerelease flags, promote gating); it does NOT import or exercise update.py. The new tests import 'from pythinker_code.ui.shell import update as update_mod' and monkeypatch update_mod.sys — a net-new dependency surface, not coverage that 'already' exists. → Reword the claim to 'the existing file covers release-workflow YAML; Task 8 adds the first updater-module tests', so a reviewer is not misled about prior coverage. (Functionally fine; the file is a reasonable home for these tests.)

### Constraint issues

- [Task 10 local gate (mirrors CI): 'uv run ruff check tests/test_release_py.py ...'. Ruff select includes E (pycodestyle) and F (Pyflakes); per-file-ignores for tests/**/*.py only exempt E501. So E402 and F841 are active for test files.] Task 2 appends 'import importlib.util' plus the module-level _spec/module_from_spec/exec_module block AFTER the function defs already in tests/test_release_py.py (Task 1 created it with functions first). Module-level imports/statements after code trigger ruff E402 -> Task 10 step 1 ruff check goes red. Same shape in Task 8: appended 'import pytest' + 'from pythinker_code.ui.shell import update as update_mod' at module level after existing functions in test_release_update_pipeline.py (E402, and CI ruff covers tests/). → Place all module-level imports and the release_tool import-via-spec load block at the TOP of tests/test_release_py.py when Task 1 first creates it (not appended in Task 2). In Task 8, add 'import pytest' and the update_mod import to the top of test_release_update_pipeline.py rather than mid-file. Re-order the TDD steps so the file's import header is established up front.
- [Same Task 10 ruff gate (F841 unused-variable, active for tests).] Task 7 test_asset_names_match_version_across_files defines 'v = re.escape(VERSION)' which is never used (the shape_res regexes use SEMVER, not v). F841 -> ruff check red. → Delete the 'v = re.escape(VERSION)' line in Task 7.
- [Task 6 code block ships in the committed module (the plan flags it for deletion only in step 2, after the block is written).] validate() contains 'text = ROOT_PYPROJECT  # anchor existence ...' which is an unused assignment (F841) and dead. Task 6 step 2 says to delete it, but it is presented as part of the canonical code block, risking it being committed if step 2 is skipped. → Remove the 'text = ROOT_PYPROJECT' line from the Task 6 validate() code block itself rather than relying on a follow-up cleanup step.
