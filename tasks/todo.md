# Plan: Full rename `pythinker-cli` → `pythinker-code`

**Status**: Planning — DO NOT execute yet. User to review and approve.
**Created**: 2026-05-07
**Estimated effort**: 4–6 hours focused work, plus 1–2 hours of unanticipated breakage debugging.
**Risk**: HIGH. Touches 393 Python files (3,061 occurrences) plus binary build, web UI, telemetry, agents, examples, and 4 CI workflows. One missed reference can break the standalone binary build, the web UI, or runtime tool-loading.

---

## Goal

Make `pythinker-code` the canonical Python package and module name. After this rename:

```bash
pip install pythinker-code     # canonical install
pythinker --help               # CLI command (unchanged)
python -c "import pythinker_code"   # canonical import
```

`pythinker-cli` (the PyPI name + Python module) is retired. Existing PyPI releases of `pythinker-cli==1.0.0` continue to work for anyone who installed them, but no new versions of `pythinker-cli` will ship.

---

## Why this is risky

Discovered during inventory:

1. **Attribute naming, not just imports**: `joint_session.pythinker_cli_session` and `session.pythinker_cli_session` are property names used across `src/pythinker_cli/web/api/sessions.py` (10+ uses) and `src/pythinker_cli/web/runner/worker.py`. Renaming these is a structural code change, not a search-and-replace.

2. **Dynamic tool imports** in agent YAMLs: `agents/default/coder.yaml` and others reference tool classes via dotted import path strings: `"pythinker_cli.tools.shell:Shell"`. Runtime errors if the import path is wrong, AND lots of these are in user-facing example agents.

3. **PyInstaller binary build**: `pythinker.spec` line 4: `from pythinker_cli.utils.pyinstaller import datas, hiddenimports`, line 13: `["src/pythinker_cli/cli/__main__.py"]`. Standalone executables won't build if these aren't updated, and PyInstaller errors are notoriously cryptic.

4. **Telemetry path regex**: `src/pythinker_cli/telemetry/sentry.py` filters stack frames with `r"^(.*?)(site-packages|pythinker_cli|src/pythinker_cli)/"`. After rename, error reports get noisier until this is fixed.

5. **60+ references in `examples/`** including `pyproject.toml` dependencies — these are reference code users copy. They have to match the canonical name post-rename.

6. **50+ docs files** (`docs/en/`, `tasks_ai/`, `AGENTS.md`, `CONTRIBUTING.md`, `README.md`) reference `pythinker-cli` and `pythinker_cli`.

7. **Workflow files**: 4 `.github/workflows/release-pythinker-*.yml` files. The cli workflow file is referenced in PyPI's trusted publisher records — renaming the file means re-registering the publishers on PyPI dashboard.

8. **PyPI dashboard state**: trusted publishers configured today reference `release-pythinker-cli.yml`. Either keep the workflow filename (less ideal — naming inconsistency) or rename and re-register on PyPI.

---

## Scope summary

| Item | Count |
|------|-------|
| Python files w/ `pythinker_cli` references | 393 |
| Total `pythinker_cli` occurrences in Python | 3,061 |
| Non-Python files w/ references | 50+ |
| Examples referencing the name | 60 |
| Workflow YAMLs to update | 4 |
| `pyproject.toml` files affected | 5 |
| Agent YAML files w/ dotted import paths | 5+ |
| Files touched in total | ~470 |

---

## Architecture decision

**Option A (chosen):** Make `packages/pythinker-code/` the new ROOT package. The current root `pyproject.toml` becomes a thin alias declaring `pythinker-cli` (kept for one release as a deprecation shim, then dropped in 1.1.0).

**Why this layout:**
- The Python module rename `pythinker_cli` → `pythinker_code` is ONE tree move, not a directory swap
- Workspace tooling stays sane
- Existing GitHub Actions workflow filenames can stay (just updated content)
- We keep PyPI's trusted publisher registrations intact (workflow filenames stable)

**Trade-off:** The root directory contains the alias instead of the canonical package, which is mildly weird structurally. But it's far less invasive than a full directory swap.

---

## Phases

### Phase 0 — Pre-flight (15 min)

- [ ] **Confirm test suite passes on `main`** before any changes:
  ```bash
  uv sync --frozen --all-extras --all-packages
  uv run pytest tests -x --co -q | head -30   # smoke: tests collect
  ```
- [ ] **Create branch** `rename/pythinker-code` from current `main` (db9545e or later):
  ```bash
  git switch -c rename/pythinker-code
  ```
- [ ] **Snapshot current state**: tag `pre-rename-snapshot` so we can `git diff` later:
  ```bash
  git tag pre-rename-snapshot
  ```
- [ ] **Document the old → new mapping** in this file (below) so we can grep-verify completeness.

#### Name mappings reference

| Old | New |
|-----|-----|
| `pythinker-cli` (PyPI name) | `pythinker-code` |
| `pythinker_cli` (Python module) | `pythinker_code` |
| `pythinker_cli_session` (attribute) | `pythinker_code_session` |
| `src/pythinker_cli/` | `src/pythinker_code/` |
| `release-pythinker-cli.yml` (workflow) | **KEEP** — see Phase 5 |
| `[tool.uv.workspace]` member `pythinker-cli` | `pythinker-code` |
| Telemetry/log service name `pythinker_cli` | `pythinker_code` |

The CLI command `pythinker` stays. The `pythinker-cli` CLI alias also stays (we publish `pythinker-cli` as a thin alias package for one release).

---

### Phase 1 — Module directory rename (30 min)

Single atomic move with git so history is preserved:

- [ ] `git mv src/pythinker_cli src/pythinker_code`
- [ ] Spot-check that `git log --follow src/pythinker_code/__main__.py` shows full history.
- [ ] DO NOT touch any file contents yet. Commit:
  ```bash
  git commit -m "chore: rename src/pythinker_cli/ -> src/pythinker_code/"
  ```

At this point the tree is broken (393 files import a module that doesn't exist by that name). Phase 2 fixes it.

---

### Phase 2 — Python import rewrite (60 min)

This is the biggest mechanical change. Use `sed` for the bulk pass, then verify by hand.

- [ ] **Bulk substitution** (preserving identifiers and strings):
  ```bash
  # All Python files
  find src tests tests_ai tests_e2e packages sdks scripts examples -name "*.py" -type f \
    -exec sed -i 's/\bpythinker_cli\b/pythinker_code/g' {} +
  ```

- [ ] **Verify no orphan `pythinker_cli` strings remain in *.py**:

  ```bash
  grep -rn "pythinker_cli" --include="*.py" src/ packages/ sdks/ tests/ tests_e2e/ tests_ai/ scripts/ examples/
  ```

  Expect: empty output (all references should now be `pythinker_code`).

- [ ] **Verify `pythinker_code_session` attribute usage**:
  Confirm that attribute references like `joint_session.pythinker_code_session` and `session.pythinker_code_session` are correctly updated in web API and worker files.

- [ ] **Run the test collector** to confirm all imports resolve:

  ```bash
  uv sync --frozen --all-extras --all-packages
  uv run pytest tests --co -q 2>&1 | tail -20
  ```

- [ ] Commit.

---

### Phase 3 — pyproject.toml + workspace surgery (45 min)

- [ ] **Move root pyproject contents** to `packages/pythinker-code/pyproject.toml`
- [ ] **Decide root pyproject's fate** — Option C (recommended): keep as thin `pythinker-cli==1.1.0` alias for one release
- [ ] **Update `[tool.uv.workspace]`** members list
- [ ] **Adjust `[project.scripts]`** in `packages/pythinker-code/pyproject.toml`
- [ ] **Build all packages locally**
- [ ] Commit.

---

### Phase 4 — Build/release infrastructure (30 min)

- [ ] Update `pythinker.spec` (PyInstaller)
- [ ] Update `Makefile` targets
- [ ] Update `scripts/build_web.py` and `scripts/build_vis.py`
- [ ] Update `scripts/check_pythinker_dependency_versions.py`
- [ ] Local PyInstaller dry run
- [ ] Commit.

---

### Phase 5 — Workflow files & PyPI publisher records (45 min)

- [ ] Edit `.github/workflows/release-pythinker-cli.yml` (keep filename, update content)
- [ ] Update `scripts/check_version_tag.py` callsites
- [ ] Verify PyPI dashboard trusted publishers still valid
- [ ] Commit.

---

### Phase 6 — Documentation, examples, agent YAMLs (60 min)

- [ ] README.md, CONTRIBUTING.md, CHANGELOG.md
- [ ] `docs/en/**/*.md`, AGENTS.md, skills, tasks_ai
- [ ] `examples/**` (60 references — pyproject + READMEs + yamls)
- [ ] Agent YAMLs: tool import paths `"pythinker_cli.tools.*"` → `"pythinker_code.tools.*"`
- [ ] Commit.

---

### Phase 7 — Verification (60 min)

- [ ] Full test suite vs pre-rename-snapshot
- [ ] `uv sync` clean (rm .venv + uv.lock)
- [ ] pyright + ruff
- [ ] Smoke import + CLI run
- [ ] PyInstaller binary
- [ ] TestPyPI dry run

---

### Phase 8 — Tag and release (30 min)

- [ ] CHANGELOG 1.1.0 entry with migration notes
- [ ] Squash-merge to main and push tag
- [ ] Watch release workflow
- [ ] Verify on PyPI

---

### Phase 9 — Post-release cleanup (deferred to 1.2.0)

- [ ] Drop `pythinker-cli` alias package
- [ ] Rename workflow file + re-register PyPI publishers
- [ ] Remove `pythinker-cli` script entry
- [ ] Bump to 1.2.0

---

## Open questions — ANSWER BEFORE EXECUTION

1. **Alias or cold-turkey?** Ship `pythinker-cli==1.1.0` as a one-shot deprecation alias (Option C), or drop at 1.1.0?
2. **Workflow filename**: keep `release-pythinker-cli.yml` for one release, or rename immediately?
3. **Module name**: confirm `pythinker_code` (vs. bare `pythinker`)?
4. **Migration callout** in README?
5. **Versioning**: breaking layout change at 1.1.0 or 2.0.0?
