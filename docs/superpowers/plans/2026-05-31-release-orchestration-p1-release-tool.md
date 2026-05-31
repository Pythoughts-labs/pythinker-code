# Release Tool + Version Single-Source-of-Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make `pyproject.toml:3` the single authoritative version, build `scripts/release.py` to rewrite every derived file + `uv.lock` from it and open a `release/X.Y.Z` PR, and enforce the version relationship (including the frozen `pythinker-review==0.1.0` pin) with an extended dependency-check script + a new `tests/test_version_lockstep.py` that runs on every PR.

**Architecture:** `scripts/release.py` is stdlib + shells out to `git`/`gh`/`uv` (C3-exempt CI/release tooling — the shipped agent gains zero runtime deps). It is factored so all rewrite logic is pure functions (semver/monotonic validation, tomlkit rewrites with a `tomllib` parse-back assertion, CHANGELOG `## Unreleased`→`## X.Y.Z (DATE)` promotion, pattern-targeted README/asset rewrites) — those get real failing-test-first pytest; the orchestration (git/gh/uv) is verified via `--dry-run`. The lockstep test asserts every version-bearing string on every main commit; `--version` flag examples are asserted shape-only (the documented §3 exception). `update.py` gains a `PYTHINKER_MANAGED` env hook ahead of the existing brew path-sniff (with a usable channel-native hint wired into both consumer paths) so P2 channels ship self-updating, with a mandatory brew-unchanged regression test.

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
- `tests/test_version_lockstep.py` — stdlib+tomllib CI test (every PR): semver shape; core/host/review pins == sub-pkg versions; review frozen at 0.1.0; README heading + pip snippet; asset-name shapes == VERSION across README + linux-installer README + getting-started.md; CHANGELOG `## X (`; `--version` flag examples are valid-semver shape only.
- `tests/test_release_py.py` — unit tests for the pure functions of `scripts/release.py` (and the extended dep-check script).

**Modified**
- `scripts/check_pythinker_dependency_versions.py` — add a `--pythinker-review-pyproject` arg + a third `("pythinker-review", ...)` tuple so the `pythinker-review==0.1.0` pin must match `packages/pythinker-review`.
- `.github/workflows/ci-pythinker-cli.yml:253-256` — pass `--pythinker-review-pyproject` to the dep-check call (or argparse fails CI red, since the new arg is `required=True`).
- `.github/workflows/release-pythinker-cli.yml:57-60` — same new arg for the release-time dep-check call.
- `src/pythinker_code/ui/shell/update.py` — `MANAGED_CHANNEL_MARKER` constant (after `NATIVE_INSTALLER_MARKER:61`); `PYTHINKER_MANAGED` env read at the top of `_detect_upgrade_command()` (line 95); a managed-channel branch in `_update_prompt_text()` (line 615) so the rendered "Update method" is a real channel-native hint; a managed-channel early-return in `do_update()` (after the detection at line 1215, before the readiness gate at line 1216) so a managed install neither mis-fires the PyPI readiness check nor tries to exec the marker. Brew path left unchanged.
- `tests/ui_and_conv/test_shell_update.py` — add the brew-unchanged + `PYTHINKER_MANAGED` regression tests (this is the file that actually imports `update`; `tests/test_release_update_pipeline.py` is workflow-text only and does NOT import `update`).
- `tests/test_release_update_pipeline.py` — add a test asserting `changelog-entry-required.yml` skips on both the `chore(release)*` title (line 54) and the `release/*` head branch (line 57) — the skip-contract that `release.py.open_pr()` depends on. (Workflow-text file, the correct home for this assertion.)
- `docs/en/release-notes/breaking-changes.md` — add a `## Unreleased` anchor (currently absent) so `release.py`'s heading promotion is uniform across all three changelog files.
- `.agents/skills/release/SKILL.md` — repoint the `update_files` (lines 22-25) and `uv_sync` (line 35) nodes at `uv run python scripts/release.py`.

---

## Task 1 — Extend `check_pythinker_dependency_versions.py` with the `pythinker-review` tuple

**Branch:** `git switch -c p1/release-tool` (created here; **all** subsequent tasks commit to this one branch — the required-arg change and both workflow-caller edits MUST ship in the same PR, or a partial merge turns CI red with `argparse: the following arguments are required: --pythinker-review-pyproject`).

**Files:**
- Modify: `scripts/check_pythinker_dependency_versions.py:43-68`
- Modify: `.github/workflows/ci-pythinker-cli.yml:253-256`
- Modify: `.github/workflows/release-pythinker-cli.yml:57-60`
- Test: `tests/test_release_py.py` (new — `subprocess`-invokes the script)

1. - [ ] Create the branch. `git switch -c p1/release-tool`.
2. - [ ] Write the failing test. Create `tests/test_release_py.py` with:

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

   (The expected substring matches the script's existing `f"{name} version mismatch: ..."` error format at `check_pythinker_dependency_versions.py:82`.)
3. - [ ] Run it and see it fail. `uv run pytest tests/test_release_py.py -q` → both tests fail (non-zero exit because argparse rejects the unknown flag: `error: unrecognized arguments: --pythinker-review-pyproject`).
4. - [ ] Add the argparse flag. In `scripts/check_pythinker_dependency_versions.py`, after `parser.add_argument("--pythinker-host-pyproject", type=Path, required=True)` (line 47), add:

   ```python
       parser.add_argument("--pythinker-review-pyproject", type=Path, required=True)
   ```

5. - [ ] Add the third tuple. Change the loop header (lines 65-68) from:

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

6. - [ ] Run and see it pass. `uv run pytest tests/test_release_py.py -q` → `2 passed`.
7. - [ ] Update the CI caller. In `.github/workflows/ci-pythinker-cli.yml`, change the existing dependency-check block to use the project-managed launcher and include review:

   ```yaml
           uv run python scripts/check_pythinker_dependency_versions.py \
             --root-pyproject pyproject.toml \
             --pythinker-core-pyproject packages/pythinker-core/pyproject.toml \
             --pythinker-host-pyproject packages/pythinker-host/pyproject.toml \
             --pythinker-review-pyproject packages/pythinker-review/pyproject.toml
   ```

8. - [ ] Update the release caller. In `.github/workflows/release-pythinker-cli.yml`, apply the identical change to the block at lines 57-60 (same trailing-`\` addition on the host line + the new review line).
9. - [ ] Sanity-check the real workspace passes. `uv run python scripts/check_pythinker_dependency_versions.py --root-pyproject pyproject.toml --pythinker-core-pyproject packages/pythinker-core/pyproject.toml --pythinker-host-pyproject packages/pythinker-host/pyproject.toml --pythinker-review-pyproject packages/pythinker-review/pyproject.toml` → `ok: pythinker-code dependencies match workspace package versions`.
10. - [ ] Lint the workflows. `uvx actionlint .github/workflows/ci-pythinker-cli.yml .github/workflows/release-pythinker-cli.yml` (if `actionlint` is unavailable, fall back to `uv run python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/ci-pythinker-cli.yml .github/workflows/release-pythinker-cli.yml`) → no output / exit 0.
11. - [ ] Commit. `git add scripts/check_pythinker_dependency_versions.py tests/test_release_py.py .github/workflows/ci-pythinker-cli.yml .github/workflows/release-pythinker-cli.yml && git commit -m "feat(release): enforce pythinker-review pin in dependency check"`

---

## Task 2 — `release.py` Phase-1 validation helpers (pure, TDD)

**Files:**
- Create: `scripts/release.py` (validation helpers + changelog-path constant only this task)
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
3. - [ ] Create the module with the validation helpers + the shared changelog-path constant. Write `scripts/release.py`:

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

   # Single source for the three hand-authored changelog files. validate() asserts
   # the `## Unreleased` anchor in ALL of them before any write, and rewrite()
   # promotes the SAME list — defined once so the two can never drift (atomic
   # Phase-2 guarantee: no partial-write if a docs file is missing its anchor).
   CHANGELOG_FILES = (
       REPO_ROOT / "CHANGELOG.md",
       REPO_ROOT / "docs" / "en" / "release-notes" / "changelog.md",
       REPO_ROOT / "docs" / "en" / "release-notes" / "breaking-changes.md",
   )

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
5. - [ ] Commit. `git add scripts/release.py tests/test_release_py.py && git commit -m "feat(release): add release.py validation helpers"`

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
- Modify: `docs/en/release-notes/breaking-changes.md:1-5`
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

Rewrite **only** these patterns (everything else — including the `--version 0.27.0` flag examples at README:303 and getting-started.md:34 — is left untouched, per §3): the `## 🆕 What's New in X` heading, the `pythinker-code==X` pip snippet, `PythinkerSetup-X.Y.Z.exe`, `pythinker-code_X.Y.Z_<arch>.deb`, `pythinker-code-X.Y.Z.<arch>.rpm`, and `/releases/download/vX.Y.Z/`. **Badges are a deliberate no-op:** the only version-bearing badge, the PyPI badge at README:12, is shields.io-live (`https://img.shields.io/pypi/v/pythinker-code...`) and the Python badge at README:13 is a `3.12%2B` requires-python floor — no badge carries a literal package version, so the contract's "badges" clause is satisfied by zero rewrites (a lockstep guard in Task 7 prevents future hardcoded-version-badge drift).

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

The git/gh/uv orchestration is genuine I/O and is verified by `--dry-run` + a rehearsal in "Phase verification". `--dry-run` runs Phase 1 (validate) + prints the intended rewrites and tag order, but writes no files, runs no `uv lock`, and creates no branch/PR. Note: `validate()` asserts the `## Unreleased` anchor in **all three** changelog files (via `CHANGELOG_FILES`) before any write, so a missing anchor in a docs file fails loud in Phase 1 and never leaves a partially-rewritten tree (atomic Phase-2 guarantee).

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
       # Assert the `## Unreleased` anchor in ALL changelog files BEFORE any write
       # (same list rewrite() promotes) so Phase 2 cannot partially rewrite the tree.
       for changelog in CHANGELOG_FILES:
           if _UNRELEASED_RE.search(changelog.read_text(encoding="utf-8")) is None:
               raise ReleaseError(f"{changelog} has no `## Unreleased` section")
       # The primary CHANGELOG's body may legitimately be empty (CI-only/docs release):
       # warn, do not abort.
       primary = CHANGELOG_FILES[0].read_text(encoding="utf-8")
       m = _UNRELEASED_RE.search(primary)
       assert m is not None  # guaranteed by the loop above
       body = primary[m.end():].split("\n## ", 1)[0].strip()
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
       for changelog in CHANGELOG_FILES:
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

   (No dead `text = ROOT_PYPROJECT` line — the anchor check is the `CHANGELOG_FILES` loop inside `validate()`.)
2. - [ ] Lint the module. `uv run ruff check scripts/release.py && uv run ruff format --check scripts/release.py` → exit 0 (run `uv run ruff format scripts/release.py` first if formatting fails). There should be zero F841/unused-variable findings.
3. - [ ] Confirm the unit tests still pass. `uv run pytest tests/test_release_py.py -q` → all pure-function tests pass (orchestration is not under pytest).
4. - [ ] Dry-run verification (no writes). On a clean tree synced to origin/main: `uv run python scripts/release.py --set-version 0.28.0 --dry-run`. Expected: prints the `warning` only if Unreleased body is empty, then `[dry-run] would rewrite SSOT -> 0.28.0`, `[dry-run] git switch -c release/0.28.0`, ... `[dry-run] gh pr create ...`, and the tag-order block ending `git tag v0.28.0 && git push origin v0.28.0`. Confirm `git status --porcelain` is still empty afterward (dry-run wrote nothing).
5. - [ ] Commit. `git add scripts/release.py && git commit -m "feat(release): add 4-phase orchestration with uv lock + frozen-sync gate"`

---

## Task 7 — `tests/test_version_lockstep.py` (runs on every PR; equality on assets, shape on flags, TDD)

**Files:**
- Create: `tests/test_version_lockstep.py`
- Test: itself — it must pass against the current repo at `0.27.0` / core `1.1.1` / host `1.0.0` / review `0.1.0`.

This test is the CI safety net. It asserts only relationships true on every main commit (never "a tag exists"). The real tree was verified: CHANGELOG.md has `## 0.27.0 (` at line 20 and `## Unreleased` at line 16, so `test_changelog_has_dated_heading_for_version` is green as-is.

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


   def test_no_hardcoded_version_badge_in_readme() -> None:
       # Guard the contract's "badges" clause: the only version-bearing badge is the
       # shields.io-live PyPI badge (img.shields.io/pypi/v/...). Fail if a future edit
       # hardcodes VERSION into a shields.io badge label/path, which would silently drift.
       readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
       for line in readme.splitlines():
           if "img.shields.io" in line and re.search(rf"badge/[^)]*{re.escape(VERSION)}", line):
               raise AssertionError(f"hardcoded-version badge found: {line!r}")


   def test_install_flag_examples_are_valid_semver_shape_only() -> None:
       # The documented §3 exception: `--version <x.y.z>` teaches flag syntax and
       # is NOT lockstepped to VERSION — only asserted to be valid semver shape.
       flag_re = re.compile(rf"--version ({SEMVER})")
       for rel in ("README.md", "docs/en/guides/getting-started.md"):
           text = (REPO_ROOT / rel).read_text(encoding="utf-8")
           for found in flag_re.findall(text):
               assert re.fullmatch(SEMVER, found), found
   ```

   (No dead `v = re.escape(VERSION)` line — the asset test iterates `shape_res` over `SEMVER` and compares each capture to `VERSION` directly, so ruff F841 cannot fire.)
2. - [ ] Run against the real tree and see it pass. `uv run pytest tests/test_version_lockstep.py -q` → all pass (current repo: VERSION `0.27.0`, review pin `0.1.0`, asset names all `0.27.0`, flag examples `0.27.0` valid shape, no hardcoded-version badge).
3. - [ ] Lint the test (F841 guard). `uv run ruff check tests/test_version_lockstep.py` → exit 0 (proves no dead-assignment regression slipped in).
4. - [ ] Prove the lockstep actually bites (temporary mutation). Edit `README.md` heading to `What's New in 0.99.0`, run `uv run pytest tests/test_version_lockstep.py -q -k readme_heading` → it FAILS. Revert the edit (`git checkout README.md`), re-run → passes. This confirms the equality assertion is load-bearing.
5. - [ ] Confirm the gate set in `release.py` already invokes this test (Task 6 `GATES` includes `pytest tests/test_version_lockstep.py`). No change needed; just verify the path matches.
6. - [ ] Commit. `git add tests/test_version_lockstep.py && git commit -m "test(release): add version lockstep guard for every PR"`

---

## Task 8 — `PYTHINKER_MANAGED` env hook in `update.py` + consumer handling + brew-unchanged regression test (TDD)

**Files:**
- Modify: `src/pythinker_code/ui/shell/update.py` — `MANAGED_CHANNEL_MARKER` (after line 61), env read in `_detect_upgrade_command()` (line 95), branch in `_update_prompt_text()` (line 615), early-return in `do_update()` (after line 1215).
- Test: `tests/ui_and_conv/test_shell_update.py` (this file imports `from pythinker_code.ui.shell import update`; `tests/test_release_update_pipeline.py` is workflow-text only and does NOT import `update`).

Brew must NOT set `PYTHINKER_MANAGED`; it keeps its existing cellar path-sniff (line 98). The env read is the literal first logic of `_detect_upgrade_command()` so non-brew managed channels (Docker/Nix/Scoop/WinGet) short-circuit. Crucially, the marker return must be *consumed*, not rendered raw: there are exactly two call sites of `_detect_upgrade_command()` — `_update_prompt_text()` (615) and `do_update()` (1215). `_update_prompt_text` needs its own branch (else it renders `__pythinker_managed_channel__ docker` as the "Update method"); `do_update` needs an early-return placed **after detection (1215) but before the `_update_candidate_unavailable_reason` readiness gate (1216)** so a managed install does not mis-fire the PyPI-still-publishing check and never reaches the exec path. The managed early-return mirrors the existing native-can't-auto-update path (lines 1246-1252): print a manual-action hint and return `UpdateResult.UPDATE_AVAILABLE`.

1. - [ ] Write the failing tests. Append to `tests/ui_and_conv/test_shell_update.py`:

   ```python
   def test_brew_unchanged_when_pythinker_managed_unset(monkeypatch):
       monkeypatch.delenv("PYTHINKER_MANAGED", raising=False)
       monkeypatch.setattr(
           update.sys, "executable",
           "/opt/homebrew/Cellar/pythinker-code/0.27.0/libexec/bin/python",
       )
       monkeypatch.setattr(update, "_is_native_build", lambda: False)
       assert update._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


   def test_brew_unchanged_even_with_native_marker(monkeypatch):
       # The .pythinker-native marker also trips _is_native_build(); the cellar
       # path-sniff must win first so brew installs stay on `brew upgrade`.
       monkeypatch.delenv("PYTHINKER_MANAGED", raising=False)
       monkeypatch.setattr(
           update.sys, "executable",
           "/opt/homebrew/Cellar/pythinker-code/0.27.0/libexec/bin/python",
       )
       monkeypatch.setattr(update, "_is_native_build", lambda: True)
       assert update._detect_upgrade_command() == ["brew", "upgrade", "pythinker-code"]


   def test_pythinker_managed_channel_short_circuits(monkeypatch):
       monkeypatch.setenv("PYTHINKER_MANAGED", "docker")
       monkeypatch.setattr(update.sys, "executable", "/usr/local/bin/python")
       cmd = update._detect_upgrade_command()
       assert cmd == [update.MANAGED_CHANNEL_MARKER, "docker"]


   def test_update_prompt_text_renders_managed_channel_hint(monkeypatch):
       # The contract requires a usable channel-native hint, not a raw marker.
       monkeypatch.setenv("PYTHINKER_MANAGED", "docker")
       monkeypatch.setattr(update.sys, "executable", "/usr/local/bin/python")
       text = update._update_prompt_text("0.27.0", "0.28.0")
       rendered = text.plain
       assert "docker" in rendered
       assert update.MANAGED_CHANNEL_MARKER not in rendered
   ```

2. - [ ] Run and see it fail. `uv run pytest tests/ui_and_conv/test_shell_update.py -q -k "pythinker_managed or brew_unchanged or managed_channel_hint"` → `test_pythinker_managed_channel_short_circuits` fails (`AttributeError: ... MANAGED_CHANNEL_MARKER`); the others fail too because the constant does not exist at import time.
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
5. - [ ] Add the managed branch to `_update_prompt_text()`. Change lines 615-619 from:

   ```python
       upgrade_command = _detect_upgrade_command()
       if upgrade_command == [NATIVE_INSTALLER_MARKER]:
           update_method = "downloads the native updater automatically"
       else:
           update_method = _format_upgrade_command(upgrade_command)
   ```

   to:

   ```python
       upgrade_command = _detect_upgrade_command()
       if upgrade_command[:1] == [MANAGED_CHANNEL_MARKER]:
           update_method = f"managed by {upgrade_command[1]} — update via your {upgrade_command[1]} channel"
       elif upgrade_command == [NATIVE_INSTALLER_MARKER]:
           update_method = "downloads the native updater automatically"
       else:
           update_method = _format_upgrade_command(upgrade_command)
   ```

6. - [ ] Add the managed early-return to `do_update()`. Change lines 1215-1218 from:

   ```python
           upgrade_command = _detect_upgrade_command()
           unavailable_reason = await _update_candidate_unavailable_reason(
               session, latest_version, upgrade_command
           )
   ```

   to (insert the early-return BEFORE the readiness gate, so a managed channel never mis-fires the PyPI check or the exec path):

   ```python
           upgrade_command = _detect_upgrade_command()
           if upgrade_command[:1] == [MANAGED_CHANNEL_MARKER]:
               channel = upgrade_command[1]
               _print(
                   f"[{_t.warning}]Pythinker is managed by your {channel} channel. "
                   f"Update {current_version} → {latest_version} via {channel} "
                   "(rebuild/repull the image or run the channel's upgrade command).[/]"
               )
               return UpdateResult.UPDATE_AVAILABLE
           unavailable_reason = await _update_candidate_unavailable_reason(
               session, latest_version, upgrade_command
           )
   ```

7. - [ ] Run and see it pass. `uv run pytest tests/ui_and_conv/test_shell_update.py -q -k "pythinker_managed or brew_unchanged or managed_channel_hint"` → `4 passed`.
8. - [ ] Confirm no regression in the existing updater tests + types. `uv run pytest tests/ui_and_conv/test_shell_update.py -q` → all pass; `uv run pyright src/pythinker_code/ui/shell/update.py` → 0 errors (the file is in the `strict` set at `pyproject.toml:138`).
9. - [ ] Commit. `git add src/pythinker_code/ui/shell/update.py tests/ui_and_conv/test_shell_update.py && git commit -m "feat(update): add PYTHINKER_MANAGED channel hint with consumer handling; keep brew unchanged"`

---

## Task 9 — Assert the `release/*` + `chore(release)` skip-contract (P1-scope guard, TDD)

**Files:**
- Modify: `tests/test_release_update_pipeline.py` (append — this is the existing workflow-text assertion home)

`release.py.open_pr()` emits a branch named `release/X.Y.Z` and a PR title `chore(release): prepare X.Y.Z`. The `changelog-entry-required.yml` workflow must skip its "require a CHANGELOG entry" check for exactly that shape (title `chore(release)*` at line 54, head branch `release/*` at line 57), because a release-prep PR consumes `## Unreleased` into a dated block and resets it, which would otherwise read as a net removal and fail. This coupling is real and load-bearing, so it is asserted here (kept out of the version-string-focused lockstep test, per the punch-list).

1. - [ ] Write the test. Append to `tests/test_release_update_pipeline.py`:

   ```python
   def test_changelog_workflow_skips_release_prep_prs() -> None:
       """release.py opens `release/X.Y.Z` PRs titled `chore(release): prepare X.Y.Z`.

       changelog-entry-required.yml MUST skip its required check for that shape,
       or every release PR is blocked under branch protection. Assert both the
       title guard and the head-branch guard so neither half silently regresses.
       """
       wf = (WORKFLOWS / "changelog-entry-required.yml").read_text()
       # Title guard: chore(release)* → skip.
       assert '"chore(release)"*)' in wf, "missing chore(release) title skip"
       # Head-branch guard: release/* → skip.
       assert "release/*)" in wf, "missing release/* branch skip"
   ```

2. - [ ] Run against the real workflow and see it pass. `uv run pytest tests/test_release_update_pipeline.py -q -k changelog_workflow_skips_release_prep` → `1 passed` (the guards exist today at `changelog-entry-required.yml:54` and `:57`).
3. - [ ] Prove the guard bites (temporary mutation). Comment out the `release/*)` case line in `.github/workflows/changelog-entry-required.yml`, re-run the test → it FAILS. Restore the line (`git checkout .github/workflows/changelog-entry-required.yml`), re-run → passes.
4. - [ ] Commit. `git add tests/test_release_update_pipeline.py && git commit -m "test(release): assert changelog workflow skips release-prep PRs"`

---

## Task 10 — Repoint the release SKILL at `scripts/release.py`

**Files:**
- Modify: `.agents/skills/release/SKILL.md` (the `update_files` node at lines 22-25 and the `uv_sync` node at line 35)

1. - [ ] Read the current nodes. Use the Read tool on `.agents/skills/release/SKILL.md` lines 1-55 (covers the `---` front matter, the `update_files` node body at 22-25, and the `uv_sync: "Run uv sync."` line at 35 — both edited nodes are in view; prefer Read over sed per repo CLAUDE.md).
2. - [ ] Replace the manual-bump prose in `update_files`. Change the node body (lines 22-25) from:

   ```
   update_files: |md
     Update the relevant pyproject.toml (and rust/Cargo.toml if root version changes),
     CHANGELOG.md (keep the Unreleased header), and breaking-changes.md in both languages.
   |
   ```

   to:

   ```
   update_files: |md
     Run `uv run python scripts/release.py --set-version X.Y.Z [--bump-core A.B.C --bump-host A.B.C]`.
     It rewrites pyproject.toml:3, the sub-package pins, uv.lock, all three changelog files
     (preserving the authored Unreleased body), and the README/asset names from the single
     source of truth, then runs the local gates and opens the `release/X.Y.Z` PR.
     There is no `--bump-review` (review is frozen at 0.1.0).
   |
   ```

3. - [ ] Update the `uv_sync` node. Change line 35 from:

   ```
   uv_sync: "Run uv sync."
   ```

   to:

   ```
   uv_sync: "release.py already runs `uv lock` + `uv sync --frozen --all-extras --all-packages` as Phase-2/3 steps; no separate uv sync needed."
   ```

4. - [ ] Verify the front matter + d2 graph still parse (no structural breakage): Read lines 1-6 → unchanged `---`/`name:`/`description:`/`type:` front matter, and confirm the edited node lines are still inside the ```` ```d2 ```` fenced block.
5. - [ ] Commit. `git add .agents/skills/release/SKILL.md && git commit -m "docs(release): repoint release skill at scripts/release.py"`

---

## Task 11 — Open the P1 PR (C1) and merge gate (C2)

**Files:** none (process)

Because every task committed to the single `p1/release-tool` branch (Task 1 onward), the required dep-check arg and both workflow-caller edits are atomic in one PR — there is no cherry-pick or stacked-PR reconciliation to do.

1. - [ ] Confirm the full local gate set is green before pushing. `uv run pytest tests/test_release_py.py tests/test_version_lockstep.py tests/ui_and_conv/test_shell_update.py tests/test_release_update_pipeline.py -q` → all pass; `uv run ruff check scripts/release.py tests/test_release_py.py tests/test_version_lockstep.py && uv run ruff format --check scripts/release.py tests/test_release_py.py tests/test_version_lockstep.py` → exit 0; `uv run pyright src/pythinker_code/ui/shell/update.py` → 0 errors.
2. - [ ] Confirm the workspace version checks pass exactly as CI will run them: `uv run python scripts/check_pythinker_dependency_versions.py --root-pyproject pyproject.toml --pythinker-core-pyproject packages/pythinker-core/pyproject.toml --pythinker-host-pyproject packages/pythinker-host/pyproject.toml --pythinker-review-pyproject packages/pythinker-review/pyproject.toml` → `ok: pythinker-code dependencies match workspace package versions`.
3. - [ ] Confirm the branch history is one coherent stack. `git log --oneline -8 p1/release-tool` shows the dep-check, release.py (validation/rewrites/promotion/asset/orchestration), lockstep, skip-contract, updater, and SKILL commits all on `p1/release-tool`. Push: `git push -u origin p1/release-tool`.
4. - [ ] Open the PR. `gh pr create --base main --head p1/release-tool --title "feat(release): release.py + version lockstep SSOT (P1)" --body "Adds scripts/release.py (4-phase SSOT release orchestrator), tests/test_version_lockstep.py (every-PR version guard), the pythinker-review dependency-check tuple (with both CI callers updated atomically), the changelog-workflow skip-contract assertion, and the PYTHINKER_MANAGED updater hook with a brew-unchanged regression test and a managed-channel rendered hint. No new agent runtime deps (C3)."`
5. - [ ] Wait for CI and CodeRabbit. Confirm required checks (`check`, `test`, `changelog`, `release-validate` as applicable) pass and the `CodeRabbit` commit status on the PR head SHA is `success` (C2) before merging. Read CodeRabbit's "Actionable comments" and resolve or surface them — do not merge past unresolved findings. Per the project CLAUDE.md / MEMORY note, reject a CodeRabbit camelCase-for-Python finding if one appears (false positive; codebase is snake_case).
6. - [ ] Merge after C2 is satisfied. `gh pr merge p1/release-tool --squash` (the local CodeRabbit merge-gate hook enforces the status check).

---

## Phase verification

**What "done" looks like:** `pyproject.toml:3` is the only place a human edits the version; everything else is derived by `scripts/release.py` or guarded by `tests/test_version_lockstep.py`; the `pythinker-review==0.1.0` freeze is enforced in the dependency check (both CI callers updated atomically) and the lockstep test; `_detect_upgrade_command()` honors `PYTHINKER_MANAGED` with a real channel-native hint in BOTH consumer paths while brew behavior is provably unchanged; and the `release/*` + `chore(release)` skip-contract is asserted so release PRs are never blocked by `changelog-entry-required.yml`.

**End-to-end rehearsal (the proof, no tag pushed):**

1. - [ ] On a clean tree synced to `origin/main`, run a real (non-dry-run) rehearsal to a throwaway version: `uv run python scripts/release.py --set-version 0.28.0`. Expected: Phase 1 validates all three changelog anchors; Phase 2 rewrites the files + runs `uv lock`; Phase 3 runs all four gates (`check_version_tag`, the extended `check_pythinker_dependency_versions`, `uv sync --frozen --all-extras --all-packages`, `pytest tests/test_version_lockstep.py`) plus the `grep -qF` checks — all green; Phase 4 creates branch `release/0.28.0`, commits `chore(release): prepare 0.28.0`, pushes, and opens a PR, then prints `git tag v0.28.0 && git push origin v0.28.0`.
2. - [ ] Prove the stress-test catch is covered: confirm `uv.lock` changed in the rehearsal commit (`git show --stat release/0.28.0 | grep uv.lock`) and that `uv sync --frozen --all-extras --all-packages` ran clean inside Phase 3 (no "lockfile out of date" error). This is the exact failure that would otherwise turn the release PR's own CI red.
3. - [ ] Confirm the documented exception held: `grep -n "version 0.28.0" docs/en/guides/getting-started.md` returns nothing — the `--version 0.27.0` flag example is unchanged (still `--version 0.27.0`), while `What's New in 0.28.0`, `pythinker-code==0.28.0`, and `PythinkerSetup-0.28.0.exe` are all present in their respective files.
4. - [ ] Confirm the skip-contract makes the rehearsal PR pass the changelog gate: the PR head branch is `release/0.28.0` and the title is `chore(release): prepare 0.28.0`, so `changelog-entry-required.yml` skips (matching the guards Task 9 asserts) and does not block on the now-empty `## Unreleased`.
5. - [ ] Tear down the rehearsal (no tag was pushed): `gh pr close release/0.28.0 --delete-branch` and `git switch main && git branch -D release/0.28.0` and `git push origin --delete release/0.28.0`. Verify `git log --oneline -1 origin/main` is untouched (C1: nothing reached main, no tag was created).
6. - [ ] Sub-package rehearsal (optional, validates `--bump-core`): `uv run python scripts/release.py --set-version 0.28.0 --bump-core 1.2.0 --dry-run` → prints the ordered tag sequence (`pythinker-core-1.2.0` first, wait-for-PyPI note, then `v0.28.0`) and the intended pin rewrite `pythinker-core[contrib]==1.2.0`, writing nothing.

**Files relevant to this phase (absolute paths):**
- `/home/ai/Projects/pythinker-code-main/scripts/release.py`
- `/home/ai/Projects/pythinker-code-main/scripts/check_pythinker_dependency_versions.py`
- `/home/ai/Projects/pythinker-code-main/tests/test_version_lockstep.py`
- `/home/ai/Projects/pythinker-code-main/tests/test_release_py.py`
- `/home/ai/Projects/pythinker-code-main/tests/ui_and_conv/test_shell_update.py`
- `/home/ai/Projects/pythinker-code-main/tests/test_release_update_pipeline.py`
- `/home/ai/Projects/pythinker-code-main/src/pythinker_code/ui/shell/update.py`
- `/home/ai/Projects/pythinker-code-main/.github/workflows/ci-pythinker-cli.yml`
- `/home/ai/Projects/pythinker-code-main/.github/workflows/release-pythinker-cli.yml`
- `/home/ai/Projects/pythinker-code-main/.github/workflows/changelog-entry-required.yml`
- `/home/ai/Projects/pythinker-code-main/docs/en/release-notes/breaking-changes.md`
- `/home/ai/Projects/pythinker-code-main/.agents/skills/release/SKILL.md`

---

## Punch-list resolution notes (how each review item was addressed)

- **specCoverageGaps #1 (PYTHINKER_MANAGED hint not consumed):** Fixed in Task 8 — added consumer handling in the exactly-two call sites (`_update_prompt_text` branch + `do_update` early-return placed before the readiness gate at line 1216), returning `UPDATE_AVAILABLE` like the native-can't-auto-update path, plus a `text.plain` rendered-hint test. The marker is never rendered raw or exec'd.
- **specCoverageGaps #2 (release/* + chore(release) skip-contract):** Added Task 9 — a real failing-first workflow-text test in `tests/test_release_update_pipeline.py` asserting both guards (`chore(release)*` title line 54, `release/*` branch line 57), with a bite-proof mutation step. Kept out of the version-focused lockstep test.
- **placeholders #1 (`v = re.escape(VERSION)` dead in lockstep):** Removed — Task 7's asset test iterates `shape_res` over `SEMVER` and compares captures to `VERSION` directly; added a ruff-check step (Task 7 step 3) to prove no F841.
- **placeholders #2 (`text = ROOT_PYPROJECT` dead in validate):** Removed from the step-1 code block — `validate()` now does the `CHANGELOG_FILES` anchor loop directly; no committed-then-deleted dead line.
- **consistencyIssues #1 (incoherent branch strategy):** Fixed — single `p1/release-tool` branch created in Task 1; the cherry-pick/stacked-PR fork is gone (Task 11). The required-arg + both workflow callers are atomic in one PR.
- **consistencyIssues #2 (SKILL recon sed range):** Fixed — Task 10 uses Read over lines 1-55 (covers `update_files` at 22-25 and `uv_sync` at 35; the real `uv_sync` line is 35, not 46).
- **consistencyIssues #3 (badges no-op):** Documented in Task 5 (PyPI badge is shields.io-live, Python badge is a `3.12%2B` floor) + added an optional lockstep guard `test_no_hardcoded_version_badge_in_readme` (Task 7) to prevent future drift.
- **constraintIssues #1 (validate only checks CHANGELOG anchor):** Fixed — introduced the module-level `CHANGELOG_FILES` constant (Task 2); `validate()` loops it to assert the `## Unreleased` anchor in all three files before any write, and `rewrite()` promotes the same list, so they cannot drift and Phase 2 stays atomic.
- **Bonus (test file mismatch):** `tests/test_release_update_pipeline.py` is workflow-text and does not import `update`; the updater unit tests were moved to `tests/ui_and_conv/test_shell_update.py` (which does), and Task 11 step 1's pytest command lists both files correctly.
