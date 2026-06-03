# Scoped Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pythinker's single-file config with a three-scope system (User → Project → Local) using type-based merging, hard security locks on sensitive fields, and env-var overrides.

**Architecture:** Load raw TOML dicts from up to three files, check scope-locked fields before merging, then type-merge (scalars override deepest-wins, lists concatenate, dicts deep-merge) into a single dict, overlay `PYTHINKER_*` env vars, and validate once through Pydantic. A parallel provenance map tracks which scope each value came from so validation errors name the source file.

**Tech Stack:** Python 3.12+, `tomlkit` (already in deps), `pydantic` v2 (already in deps), `pytest` + `monkeypatch` for tests.

**Spec:** `docs/superpowers/specs/2026-06-03-pythinker-scope-config-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/pythinker_code/config.py` | All new constants, helpers, pipeline functions, `Config` field, `load_config` wiring |
| Create | `src/pythinker_code/utils/gitignore.py` | `ensure_gitignored` utility |
| Modify | `tests/core/test_config.py` | Unit + integration tests for pipeline functions |
| Create | `tests/utils/test_gitignore.py` | Tests for `ensure_gitignored` |

No other files need changes — all existing `load_config()` call sites automatically gain scope resolution.

---

## Task 1: Sync `_find_project_root` in `config.py`

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

> **Context:** `utils/path.py` already has an async `find_project_root` that returns `work_dir` when no `.git` is found. We need a sync version that returns `None` — different enough to warrant a new private function in `config.py` rather than changing the shared one.

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_config.py`:

```python
from pythinker_code.config import _find_project_root


def test_find_project_root_finds_git_root(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    subdir = tmp_path / "src" / "pkg"
    subdir.mkdir(parents=True)
    assert _find_project_root(subdir) == tmp_path


def test_find_project_root_returns_none_outside_git(tmp_path):
    # tmp_path itself has no .git ancestor in practice
    assert _find_project_root(tmp_path) is None


def test_find_project_root_finds_root_in_cwd(tmp_path):
    (tmp_path / ".git").mkdir()
    assert _find_project_root(tmp_path) == tmp_path
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/Projects/pythinker-code-main
.venv/bin/pytest tests/core/test_config.py::test_find_project_root_finds_git_root tests/core/test_config.py::test_find_project_root_returns_none_outside_git tests/core/test_config.py::test_find_project_root_finds_root_in_cwd -v
```

Expected: `ImportError` or `AttributeError` — `_find_project_root` does not exist yet.

- [ ] **Step 3: Implement `_find_project_root`**

Add after the `get_share_dir` import block in `src/pythinker_code/config.py`, before the `AgentExecutionProfile` definition:

```python
def _find_project_root(cwd: Path) -> Path | None:
    """Walk up from cwd to find the nearest directory containing .git/.

    Returns None when no .git marker is found before reaching the filesystem
    root, so callers can skip project/local scopes without a fallback.
    """
    current = cwd.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/core/test_config.py::test_find_project_root_finds_git_root tests/core/test_config.py::test_find_project_root_returns_none_outside_git tests/core/test_config.py::test_find_project_root_finds_root_in_cwd -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add sync _find_project_root helper"
```

---

## Task 2: `utils/gitignore.py` — `ensure_gitignored`

**Files:**
- Create: `src/pythinker_code/utils/gitignore.py`
- Create: `tests/utils/test_gitignore.py`

- [ ] **Step 1: Write failing tests**

Create `tests/utils/test_gitignore.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.utils.gitignore import ensure_gitignored


def test_creates_gitignore_when_absent(tmp_path):
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml", comment="Added by pythinker")
    gi = tmp_path / ".gitignore"
    assert gi.exists()
    content = gi.read_text()
    assert ".pythinker/config.local.toml" in content
    assert "Added by pythinker" in content


def test_appends_to_existing_gitignore(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("*.pyc\n", encoding="utf-8")
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml")
    content = gi.read_text()
    assert "*.pyc" in content
    assert ".pythinker/config.local.toml" in content


def test_no_op_when_pattern_already_present(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text(".pythinker/config.local.toml\n", encoding="utf-8")
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml")
    # No duplicate
    lines = [l for l in gi.read_text().splitlines() if l == ".pythinker/config.local.toml"]
    assert len(lines) == 1


def test_fixes_missing_trailing_newline(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("*.pyc", encoding="utf-8")  # no trailing newline
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml")
    content = gi.read_text()
    # Pattern must start on its own line, not appended to "*.pyc"
    assert "\n.pythinker/config.local.toml" in content


def test_omits_comment_when_empty(tmp_path):
    ensure_gitignored(tmp_path, ".pythinker/config.local.toml", comment="")
    content = (tmp_path / ".gitignore").read_text()
    assert ".pythinker/config.local.toml" in content
    assert "#" not in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/utils/test_gitignore.py -v
```

Expected: `ModuleNotFoundError` — `utils/gitignore.py` does not exist yet.

- [ ] **Step 3: Implement `ensure_gitignored`**

Create `src/pythinker_code/utils/gitignore.py`:

```python
from __future__ import annotations

from pathlib import Path


def ensure_gitignored(git_root: Path, pattern: str, comment: str = "") -> None:
    """Append *pattern* to <git_root>/.gitignore if not already present.

    Creates .gitignore if the file does not exist. Handles missing trailing
    newline before appending. Prepends a comment line when *comment* is given.
    """
    gi_path = git_root / ".gitignore"

    if gi_path.exists():
        content = gi_path.read_text(encoding="utf-8")
        # Check if pattern is already present as a standalone line
        if any(line.strip() == pattern for line in content.splitlines()):
            return
    else:
        content = ""

    lines_to_append: list[str] = []
    if content and not content.endswith("\n"):
        lines_to_append.append("\n")
    if comment:
        lines_to_append.append(f"# {comment}\n")
    lines_to_append.append(f"{pattern}\n")

    with gi_path.open("a", encoding="utf-8") as f:
        f.write("".join(lines_to_append))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/utils/test_gitignore.py -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/utils/gitignore.py tests/utils/test_gitignore.py
git commit -m "feat(utils): add ensure_gitignored utility"
```

---

## Task 3: Constants and helper functions in `config.py`

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

> **Context:** Add the constants (`SCOPE_LOCKED_PATHS`, `DEDUP_LIST_FIELDS`, `ENV_FIELD_MAP`) and the two small helper functions (`_set_nested`, `_lookup_provenance`). These are pure functions with no side effects and can be tested in isolation.

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_config.py`:

```python
from pythinker_code.config import _lookup_provenance, _set_nested


def test_set_nested_flat():
    d: dict = {}
    _set_nested(d, ("theme",), "light")
    assert d == {"theme": "light"}


def test_set_nested_deep():
    d: dict = {}
    _set_nested(d, ("tui", "style"), "card")
    assert d == {"tui": {"style": "card"}}


def test_set_nested_overwrites_existing():
    d = {"tui": {"style": "pythinker", "smooth_streaming": True}}
    _set_nested(d, ("tui", "style"), "card")
    assert d["tui"]["style"] == "card"
    assert d["tui"]["smooth_streaming"] is True  # sibling preserved


def test_lookup_provenance_scalar():
    prov = {"theme": ".pythinker/config.local.toml"}
    assert _lookup_provenance(prov, ("theme",)) == ".pythinker/config.local.toml"


def test_lookup_provenance_nested():
    prov = {"tui": {"style": ".pythinker/config.toml"}}
    assert _lookup_provenance(prov, ("tui", "style")) == ".pythinker/config.toml"


def test_lookup_provenance_list_index():
    # Pydantic gives loc=("hooks", 0, "command") for a bad list element.
    # Should return the collection scope, not crash.
    prov = {"hooks": "~/.pythinker/config.toml+.pythinker/config.toml"}
    assert _lookup_provenance(prov, ("hooks", 0, "command")) == "~/.pythinker/config.toml+.pythinker/config.toml"


def test_lookup_provenance_partial_path():
    prov = {"tui": {"style": ".pythinker/config.toml"}}
    assert _lookup_provenance(prov, ("tui", "nonexistent")) == "unknown scope"


def test_lookup_provenance_empty_loc():
    prov = "~/.pythinker/config.toml"
    assert _lookup_provenance(prov, ()) == "~/.pythinker/config.toml"


def test_lookup_provenance_unknown():
    prov: dict = {}
    assert _lookup_provenance(prov, ("missing_key",)) == "unknown scope"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_set_nested_flat tests/core/test_config.py::test_lookup_provenance_scalar -v
```

Expected: `ImportError` — `_set_nested`, `_lookup_provenance` not defined yet.

- [ ] **Step 3: Add constants and helpers to `config.py`**

Add after the `_find_project_root` function:

```python
# ---------------------------------------------------------------------------
# Scope system constants
# ---------------------------------------------------------------------------

SCOPE_LOCKED_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("providers",),  # contains api_key per provider — must stay in user scope
        ("services",),  # contains api_key fields — must stay in user scope
        ("feedback", "api_key"),  # only the key, not the whole feedback section
    }
)

DEDUP_LIST_FIELDS: frozenset[str] = frozenset({"allowed_domains", "extra_skill_dirs"})

ENV_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "PYTHINKER_DEFAULT_MODEL": ("default_model",),
    "PYTHINKER_DEFAULT_THINKING": ("default_thinking",),
    "PYTHINKER_DEFAULT_THINKING_EFFORT": ("default_thinking_effort",),
    "PYTHINKER_AGENT_EXECUTION_PROFILE": ("agent_execution_profile",),
    "PYTHINKER_DEFAULT_YOLO": ("default_yolo",),
    "PYTHINKER_ASK_USER_QUESTION_POLICY": ("ask_user_question_policy",),
    "PYTHINKER_AUTO_DELIBERATE_DESTRUCTIVE_ACTIONS": ("auto_deliberate_destructive_actions",),
    "PYTHINKER_SKIP_AUTO_PROMPT_INJECTION": ("skip_auto_prompt_injection",),
    "PYTHINKER_DEFAULT_PLAN_MODE": ("default_plan_mode",),
    "PYTHINKER_DEFAULT_EDITOR": ("default_editor",),
    "PYTHINKER_THEME": ("theme",),
    "PYTHINKER_SHOW_THINKING_STREAM": ("show_thinking_stream",),
    "PYTHINKER_PREVENT_IDLE_SLEEP": ("prevent_idle_sleep",),
    "PYTHINKER_TELEMETRY": ("telemetry",),
    "PYTHINKER_SESSION_RETENTION_DAYS": ("session_retention_days",),
    "PYTHINKER_MERGE_ALL_AVAILABLE_SKILLS": ("merge_all_available_skills",),
}


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _set_nested(d: dict, path: tuple[str, ...], value: object) -> None:
    """Walk *path* into *d*, creating intermediate dicts, then set the leaf."""
    node = d
    for part in path[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[path[-1]] = value


def _lookup_provenance(prov: "dict | str", loc: tuple) -> str:
    """Recursively follow *loc* through the provenance map.

    Integer elements (Pydantic list indices) are skipped — we map them back
    to the parent collection's scope string so error messages stay useful.
    Returns "unknown scope" when the path cannot be fully resolved.
    """
    if not loc or isinstance(prov, str):
        return prov if isinstance(prov, str) else "unknown scope"
    head, *tail = loc
    if isinstance(head, int):
        return prov if isinstance(prov, str) else _lookup_provenance(prov, tuple(tail))
    if isinstance(prov, dict) and head in prov:
        return _lookup_provenance(prov[head], tuple(tail))
    return "unknown scope"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/core/test_config.py::test_set_nested_flat tests/core/test_config.py::test_set_nested_deep tests/core/test_config.py::test_set_nested_overwrites_existing tests/core/test_config.py::test_lookup_provenance_scalar tests/core/test_config.py::test_lookup_provenance_nested tests/core/test_config.py::test_lookup_provenance_list_index tests/core/test_config.py::test_lookup_provenance_partial_path tests/core/test_config.py::test_lookup_provenance_empty_loc tests/core/test_config.py::test_lookup_provenance_unknown -v
```

Expected: all 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add scope constants and provenance helpers"
```

---

## Task 4: `_check_scope_locks`

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_config.py`:

```python
from pythinker_code.config import _check_scope_locks


def test_scope_lock_providers_in_project():
    with pytest.raises(ConfigError, match="'providers'.*project scope"):
        _check_scope_locks({"providers": {"openai": {}}}, ".pythinker/config.toml")


def test_scope_lock_services_in_local():
    with pytest.raises(ConfigError, match="'services'.*local scope"):
        _check_scope_locks({"services": {"pythinker_ai_search": {}}}, ".pythinker/config.local.toml")


def test_scope_lock_feedback_api_key():
    with pytest.raises(ConfigError, match="'feedback.api_key'"):
        _check_scope_locks(
            {"feedback": {"api_key": "secret"}}, ".pythinker/config.toml"
        )


def test_scope_lock_feedback_url_allowed():
    # feedback.endpoint_url is NOT locked — should not raise
    _check_scope_locks(
        {"feedback": {"endpoint_url": "https://internal.example.com"}},
        ".pythinker/config.toml",
    )


def test_scope_lock_clean_dict():
    _check_scope_locks({"theme": "light", "default_model": "gpt-4"}, ".pythinker/config.toml")


def test_scope_lock_error_mentions_env_var():
    with pytest.raises(ConfigError, match="PYTHINKER_PROVIDER"):
        _check_scope_locks({"providers": {}}, ".pythinker/config.toml")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_scope_lock_providers_in_project tests/core/test_config.py::test_scope_lock_clean_dict -v
```

Expected: `ImportError` — `_check_scope_locks` not defined yet.

- [ ] **Step 3: Implement `_check_scope_locks`**

Add after `_lookup_provenance` in `src/pythinker_code/config.py`:

```python
def _check_scope_locks(scope_dict: dict, scope_name: str) -> None:
    """Raise ConfigError if *scope_dict* contains any scope-locked field paths.

    Checks every path in SCOPE_LOCKED_PATHS by walking the raw dict before
    Pydantic validation, so secrets are blocked before they can be merged.
    """
    for path in SCOPE_LOCKED_PATHS:
        node: object = scope_dict
        for part in path:
            if not isinstance(node, dict) or part not in node:
                break
        else:
            field_path = ".".join(path)
            # Derive a short scope label for the error message
            if "local" in scope_name:
                scope_label = "local scope"
            elif "project" in scope_name or scope_name.startswith(".pythinker"):
                scope_label = "project scope"
            else:
                scope_label = scope_name
            raise ConfigError(
                f"'{field_path}' cannot be set in {scope_name} ({scope_label}).\n"
                f"  Move it to ~/.pythinker/config.toml or set "
                f"PYTHINKER_PROVIDER_<NAME>_API_KEY in the environment."
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/core/test_config.py::test_scope_lock_providers_in_project tests/core/test_config.py::test_scope_lock_services_in_local tests/core/test_config.py::test_scope_lock_feedback_api_key tests/core/test_config.py::test_scope_lock_feedback_url_allowed tests/core/test_config.py::test_scope_lock_clean_dict tests/core/test_config.py::test_scope_lock_error_mentions_env_var -v
```

Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add _check_scope_locks with path-level secret detection"
```

---

## Task 5: `_type_based_merge`

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_config.py`:

```python
from pythinker_code.config import _type_based_merge


def test_merge_scalar_override():
    prov: dict = {}
    result = _type_based_merge({"theme": "dark"}, {"theme": "light"}, prov, ".pythinker/config.local.toml")
    assert result["theme"] == "light"
    assert prov["theme"] == ".pythinker/config.local.toml"


def test_merge_scalar_three_scopes():
    prov: dict = {}
    base = _type_based_merge({}, {"theme": "dark"}, prov, "~/.pythinker/config.toml")
    base = _type_based_merge(base, {"theme": "solarized"}, prov, ".pythinker/config.toml")
    base = _type_based_merge(base, {"theme": "light"}, prov, ".pythinker/config.local.toml")
    assert base["theme"] == "light"
    assert prov["theme"] == ".pythinker/config.local.toml"


def test_merge_list_concat():
    prov: dict = {}
    base = _type_based_merge({}, {"hooks": [{"event": "Stop", "command": "a"}]}, prov, "~/.pythinker/config.toml")
    base = _type_based_merge(base, {"hooks": [{"event": "Stop", "command": "b"}]}, prov, ".pythinker/config.toml")
    assert len(base["hooks"]) == 2
    assert base["hooks"][0]["command"] == "a"
    assert base["hooks"][1]["command"] == "b"


def test_merge_list_concat_provenance():
    prov: dict = {}
    base = _type_based_merge({}, {"hooks": []}, prov, "~/.pythinker/config.toml")
    base = _type_based_merge(base, {"hooks": []}, prov, ".pythinker/config.toml")
    assert prov["hooks"] == "~/.pythinker/config.toml+.pythinker/config.toml"


def test_merge_list_base_case_provenance():
    prov: dict = {}
    _type_based_merge({}, {"hooks": []}, prov, "~/.pythinker/config.toml")
    assert prov["hooks"] == "~/.pythinker/config.toml"


def test_merge_list_dedup_extra_skill_dirs():
    prov: dict = {}
    base = _type_based_merge({}, {"extra_skill_dirs": ["/a", "/b"]}, prov, "~/.pythinker/config.toml")
    base = _type_based_merge(base, {"extra_skill_dirs": ["/b", "/c"]}, prov, ".pythinker/config.toml")
    # /b appears in both — should appear only once (first occurrence kept)
    assert base["extra_skill_dirs"] == ["/a", "/b", "/c"]


def test_merge_dict_deep():
    prov: dict = {}
    base = _type_based_merge(
        {}, {"tui": {"style": "pythinker", "smooth_streaming": True}}, prov, "~/.pythinker/config.toml"
    )
    base = _type_based_merge(
        base, {"tui": {"style": "card"}}, prov, ".pythinker/config.toml"
    )
    assert base["tui"]["style"] == "card"
    assert base["tui"]["smooth_streaming"] is True  # sibling preserved
    assert prov["tui"]["style"] == ".pythinker/config.toml"
    assert prov["tui"]["smooth_streaming"] == "~/.pythinker/config.toml"


def test_merge_key_only_in_overlay():
    prov: dict = {}
    result = _type_based_merge({}, {"theme": "dark"}, prov, "~/.pythinker/config.toml")
    assert result["theme"] == "dark"
    assert prov["theme"] == "~/.pythinker/config.toml"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_merge_scalar_override tests/core/test_config.py::test_merge_list_concat -v
```

Expected: `ImportError` — `_type_based_merge` not defined yet.

- [ ] **Step 3: Implement `_type_based_merge`**

Add after `_check_scope_locks` in `src/pythinker_code/config.py`:

```python
def _type_based_merge(base: dict, overlay: dict, provenance: dict, scope: str) -> dict:
    """Merge *overlay* into *base* using type-based rules, tracking provenance.

    Rules:
    - Scalar (str/bool/int/float/None): overlay wins, provenance records scope.
    - List: base + overlay concatenated; DEDUP_LIST_FIELDS deduplicated
      (order-preserving, first occurrence wins).
    - Dict: recurse so nested keys can be independently overridden.

    Mutates *base* and *provenance* in place; also returns *base* for chaining.
    """
    for key, value in overlay.items():
        if key not in base:
            base[key] = value
            provenance[key] = scope
        elif isinstance(value, list) and isinstance(base[key], list):
            combined = base[key] + value
            if key in DEDUP_LIST_FIELDS:
                combined = list(dict.fromkeys(combined))
            base[key] = combined
            existing = provenance.get(key)
            provenance[key] = f"{existing}+{scope}" if existing else scope
        elif isinstance(value, dict) and isinstance(base[key], dict):
            _type_based_merge(
                base[key],
                value,
                provenance.setdefault(key, {}),
                scope,
            )
        else:
            base[key] = value
            provenance[key] = scope
    return base
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/core/test_config.py::test_merge_scalar_override tests/core/test_config.py::test_merge_scalar_three_scopes tests/core/test_config.py::test_merge_list_concat tests/core/test_config.py::test_merge_list_concat_provenance tests/core/test_config.py::test_merge_list_base_case_provenance tests/core/test_config.py::test_merge_list_dedup_extra_skill_dirs tests/core/test_config.py::test_merge_dict_deep tests/core/test_config.py::test_merge_key_only_in_overlay -v
```

Expected: all 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add _type_based_merge with dedup and provenance tracking"
```

---

## Task 6: `_apply_env_vars`

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_config.py`:

```python
from pythinker_code.config import _apply_env_vars


def test_apply_env_vars_known_key(monkeypatch):
    monkeypatch.setenv("PYTHINKER_THEME", "light")
    merged: dict = {}
    prov: dict = {}
    _apply_env_vars(merged, prov)
    assert merged["theme"] == "light"
    assert prov["theme"] == "env PYTHINKER_THEME"


def test_apply_env_vars_unknown_key_ignored(monkeypatch):
    monkeypatch.setenv("PYTHINKER_XYZZY_UNKNOWN", "whatever")
    merged: dict = {}
    prov: dict = {}
    _apply_env_vars(merged, prov)
    assert "xyzzy_unknown" not in merged


def test_apply_env_vars_bool_coercion(monkeypatch):
    monkeypatch.setenv("PYTHINKER_DEFAULT_YOLO", "true")
    merged: dict = {}
    prov: dict = {}
    _apply_env_vars(merged, prov)
    # Stored as string; Pydantic coerces during model_validate
    assert merged["default_yolo"] == "true"
    assert prov["default_yolo"] == "env PYTHINKER_DEFAULT_YOLO"


def test_apply_env_vars_overrides_existing(monkeypatch):
    monkeypatch.setenv("PYTHINKER_THEME", "light")
    merged = {"theme": "dark"}
    prov = {"theme": "~/.pythinker/config.toml"}
    _apply_env_vars(merged, prov)
    assert merged["theme"] == "light"
    assert prov["theme"] == "env PYTHINKER_THEME"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_apply_env_vars_known_key tests/core/test_config.py::test_apply_env_vars_unknown_key_ignored -v
```

Expected: `ImportError` — `_apply_env_vars` not defined yet.

- [ ] **Step 3: Implement `_apply_env_vars`**

Add after `_type_based_merge` in `src/pythinker_code/config.py`:

```python
def _apply_env_vars(merged: dict, provenance: dict) -> None:
    """Overlay PYTHINKER_* env vars onto *merged*, updating *provenance*.

    Values are stored as raw strings; Pydantic coerces them during
    model_validate(). Only keys in ENV_FIELD_MAP are recognised; all others
    are silently ignored.
    """
    for env_key, path in ENV_FIELD_MAP.items():
        value = os.environ.get(env_key)
        if value is not None:
            _set_nested(merged, path, value)
            _set_nested(provenance, path, f"env {env_key}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/core/test_config.py::test_apply_env_vars_known_key tests/core/test_config.py::test_apply_env_vars_unknown_key_ignored tests/core/test_config.py::test_apply_env_vars_bool_coercion tests/core/test_config.py::test_apply_env_vars_overrides_existing -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add _apply_env_vars with ENV_FIELD_MAP"
```

---

## Task 7: `source_scopes` field on `Config`

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

> **Context:** Add `source_scopes: dict[str, Path]` as an `exclude=True` metadata field alongside the existing `source_file` and `is_from_default_location` fields. It is never serialised.

- [ ] **Step 1: Write a failing test**

Add to `tests/core/test_config.py`:

```python
def test_config_source_scopes_default_empty():
    config = get_default_config()
    assert config.source_scopes == {}


def test_config_source_scopes_not_in_dump():
    config = get_default_config()
    dumped = config.model_dump()
    assert "source_scopes" not in dumped
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_config_source_scopes_default_empty tests/core/test_config.py::test_config_source_scopes_not_in_dump -v
```

Expected: `AttributeError` — `source_scopes` does not exist yet.

- [ ] **Step 3: Add `source_scopes` to `Config`**

In `src/pythinker_code/config.py`, inside the `Config` class, add alongside the existing `source_file` field:

```python
source_scopes: dict[str, Path] = Field(
    default_factory=dict,
    description=(
        "Paths of config files that contributed to this resolved config, keyed by scope name. "
        "e.g. {'user': Path('~/.pythinker/config.toml'), 'project': Path('.pythinker/config.toml')}."
    ),
    exclude=True,
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/core/test_config.py::test_config_source_scopes_default_empty tests/core/test_config.py::test_config_source_scopes_not_in_dump -v
```

Expected: both PASS.

- [ ] **Step 5: Run existing config tests to confirm no regression**

```bash
.venv/bin/pytest tests/core/test_config.py -v
```

Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add source_scopes metadata field to Config"
```

---

## Task 8: `_load_scoped` pipeline function

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

> **Context:** This is the heart of the feature. It wires all previous functions into the five-step pipeline: Ingest → Guard → Merge → Env → Validate.

- [ ] **Step 1: Write integration tests**

Add to `tests/core/test_config.py`:

```python
import tomlkit
from pythinker_code.config import _load_scoped


def _write_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(data), encoding="utf-8")  # type: ignore[arg-type]


def test_load_scoped_user_only(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {"theme": "light"})
    config = _load_scoped(project_root=None)
    assert config.theme == "light"
    assert config.source_scopes["user"] == (tmp_path / "config.toml").resolve()


def test_load_scoped_project_overrides_user(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {"theme": "dark"})
    project_root = tmp_path / "myproject"
    _write_toml(project_root / ".pythinker" / "config.toml", {"theme": "solarized"})
    config = _load_scoped(project_root=project_root)
    assert config.theme == "solarized"


def test_load_scoped_local_overrides_project(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {"theme": "dark"})
    project_root = tmp_path / "myproject"
    _write_toml(project_root / ".pythinker" / "config.toml", {"theme": "solarized"})
    _write_toml(project_root / ".pythinker" / "config.local.toml", {"theme": "light"})
    config = _load_scoped(project_root=project_root)
    assert config.theme == "light"


def test_load_scoped_hooks_concatenate(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {"hooks": [{"event": "Stop", "command": "user-hook"}]})
    project_root = tmp_path / "myproject"
    _write_toml(
        project_root / ".pythinker" / "config.toml",
        {"hooks": [{"event": "Stop", "command": "project-hook"}]},
    )
    config = _load_scoped(project_root=project_root)
    commands = [h.command for h in config.hooks]
    assert "user-hook" in commands
    assert "project-hook" in commands


def test_load_scoped_scope_lock_violation(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {})
    project_root = tmp_path / "myproject"
    _write_toml(
        project_root / ".pythinker" / "config.toml",
        {"providers": {"bad": {"type": "openai", "base_url": "x", "api_key": "sk-x"}}},
    )
    with pytest.raises(ConfigError, match="'providers'"):
        _load_scoped(project_root=project_root)


def test_load_scoped_validation_error_attributes_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {})
    project_root = tmp_path / "myproject"
    _write_toml(
        project_root / ".pythinker" / "config.local.toml",
        {"theme": "neon"},  # invalid value
    )
    with pytest.raises(ConfigError, match="config.local.toml"):
        _load_scoped(project_root=project_root)


def test_load_scoped_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    monkeypatch.setenv("PYTHINKER_THEME", "light")
    _write_toml(tmp_path / "config.toml", {"theme": "dark"})
    project_root = tmp_path / "myproject"
    _write_toml(project_root / ".pythinker" / "config.toml", {"theme": "solarized"})
    config = _load_scoped(project_root=project_root)
    assert config.theme == "light"  # env beats all file scopes


def test_load_scoped_source_scopes_populated(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    _write_toml(tmp_path / "config.toml", {})
    project_root = tmp_path / "myproject"
    _write_toml(project_root / ".pythinker" / "config.toml", {})
    config = _load_scoped(project_root=project_root)
    assert "user" in config.source_scopes
    assert "project" in config.source_scopes
    assert "local" not in config.source_scopes  # local file absent
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_load_scoped_user_only tests/core/test_config.py::test_load_scoped_scope_lock_violation -v
```

Expected: `ImportError` — `_load_scoped` not defined yet.

- [ ] **Step 3: Implement `_load_scoped`**

Add after `_apply_env_vars` in `src/pythinker_code/config.py`. Also add `import copy` at the top of the file if not already present:

```python
def _load_scoped(project_root: Path | None) -> Config:
    """Run the five-step scoped config resolution pipeline.

    Steps: Ingest → Guard → Merge → Env → Validate.
    Returns a fully-validated Config with source_scopes populated.
    """
    from pythinker_code.utils.gitignore import ensure_gitignored

    # ── INGEST ────────────────────────────────────────────────────────────
    default_user_file = get_config_file().expanduser().resolve(strict=False)
    # Trigger JSON→TOML migration if needed (existing logic)
    if not default_user_file.exists():
        migration_error = _migrate_json_config_to_toml()
        if migration_error is not None:
            raise ConfigError(
                f"Legacy config file has incompatible settings; please fix or "
                f"rename/delete {migration_error.config_file} to continue. "
                f"Errors: {migration_error.errors}"
            ) from None

    def _read_toml(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return dict(tomlkit.loads(path.read_text(encoding="utf-8")))
        except TOMLKitError as exc:
            raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc

    user_file = default_user_file
    user_dict = _read_toml(user_file)

    project_file: Path | None = None
    local_file: Path | None = None
    project_dict: dict = {}
    local_dict: dict = {}

    if project_root is not None:
        project_file = project_root / ".pythinker" / "config.toml"
        local_file = project_root / ".pythinker" / "config.local.toml"
        project_dict = _read_toml(project_file)
        local_dict = _read_toml(local_file)

    # ── GUARD ─────────────────────────────────────────────────────────────
    if project_file is not None:
        _check_scope_locks(project_dict, str(project_file))
    if local_file is not None:
        _check_scope_locks(local_dict, str(local_file))

    # ── MERGE ─────────────────────────────────────────────────────────────
    provenance: dict = {}
    merged = _type_based_merge({}, user_dict, provenance, str(user_file))
    if project_dict:
        merged = _type_based_merge(merged, project_dict, provenance, str(project_file))
    if local_dict:
        merged = _type_based_merge(merged, local_dict, provenance, str(local_file))

    # ── ENV OVERLAY ───────────────────────────────────────────────────────
    _apply_env_vars(merged, provenance)

    # ── VALIDATE ──────────────────────────────────────────────────────────
    try:
        config = Config.model_validate(merged)
    except ValidationError as exc:
        enriched: list[str] = []
        for err in exc.errors():
            scope = _lookup_provenance(provenance, tuple(err["loc"]))
            field = ".".join(str(p) for p in err["loc"])
            enriched.append(f"  {field}: {err['msg']}  [from {scope}]")
        raise ConfigError("Invalid configuration:\n" + "\n".join(enriched)) from exc

    # ── METADATA ──────────────────────────────────────────────────────────
    config.is_from_default_location = True
    config.source_file = user_file
    if user_file.exists():
        config.source_scopes["user"] = user_file
    if project_file is not None and project_file.exists():
        config.source_scopes["project"] = project_file
    if local_file is not None and local_file.exists():
        config.source_scopes["local"] = local_file
        # Auto-gitignore local config so it is never accidentally committed
        ensure_gitignored(
            project_root,  # type: ignore[arg-type]
            ".pythinker/config.local.toml",
            comment="Added by pythinker",
        )

    return config
```

- [ ] **Step 4: Verify `import copy` is present** (we use `_type_based_merge` which mutates in-place, so no `copy` needed — but double-check the imports at the top of `config.py` include `os` which `_apply_env_vars` uses)

```bash
grep "^import os" /home/ai/Projects/pythinker-code-main/src/pythinker_code/config.py
```

Expected: `import os` found. If not, add `import os` to the imports.

- [ ] **Step 5: Run integration tests**

```bash
.venv/bin/pytest tests/core/test_config.py::test_load_scoped_user_only tests/core/test_config.py::test_load_scoped_project_overrides_user tests/core/test_config.py::test_load_scoped_local_overrides_project tests/core/test_config.py::test_load_scoped_hooks_concatenate tests/core/test_config.py::test_load_scoped_scope_lock_violation tests/core/test_config.py::test_load_scoped_validation_error_attributes_scope tests/core/test_config.py::test_load_scoped_env_override tests/core/test_config.py::test_load_scoped_source_scopes_populated -v
```

Expected: all 8 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): add _load_scoped five-step pipeline"
```

---

## Task 9: Wire `load_config` + full regression sweep

**Files:**
- Modify: `src/pythinker_code/config.py`
- Test: `tests/core/test_config.py`

> **Context:** Update `load_config` to route through `_load_scoped` when called with no explicit file path. When an explicit path is given, use the original code path unchanged. Run the full test suite to verify no regression.

- [ ] **Step 1: Write a backward-compatibility test**

Add to `tests/core/test_config.py`:

```python
def test_load_config_explicit_path_bypasses_scoping(tmp_path):
    """--config flag must bypass scope resolution entirely."""
    config_file = tmp_path / "explicit.toml"
    config_file.write_text('theme = "light"\n', encoding="utf-8")
    config = load_config(config_file)
    assert config.theme == "light"
    assert config.source_file == config_file.resolve()
    # source_scopes is empty because no scope pipeline was run
    assert config.source_scopes == {}


def test_load_config_no_args_uses_scope_resolution(tmp_path, monkeypatch):
    """load_config() with no args routes through scoped pipeline."""
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text('theme = "light"\n', encoding="utf-8")
    # No git root in tmp_path — falls back to user-only
    config = load_config()
    assert config.theme == "light"
    assert "user" in config.source_scopes
```

- [ ] **Step 2: Run these tests to verify they fail**

```bash
.venv/bin/pytest tests/core/test_config.py::test_load_config_explicit_path_bypasses_scoping tests/core/test_config.py::test_load_config_no_args_uses_scope_resolution -v
```

Expected: `test_load_config_no_args_uses_scope_resolution` FAIL (source_scopes empty because `load_config` hasn't been updated yet).

- [ ] **Step 3: Update `load_config` in `config.py`**

Replace the start of `load_config` so it routes through `_load_scoped` when no explicit file is given:

```python
def load_config(config_file: Path | None = None) -> Config:
    """Load configuration, resolving up to three scopes when no explicit file is given.

    When *config_file* is None (the default), the scoped pipeline runs:
    User (~/.pythinker/config.toml) → Project (.pythinker/config.toml) →
    Local (.pythinker/config.local.toml), merged with type-based rules.

    When *config_file* is given explicitly (e.g. via --config), that single
    file is loaded directly with no scope resolution — preserving the legacy
    behaviour used by tests and the CLI --config flag.
    """
    if config_file is None:
        project_root = _find_project_root(Path.cwd())
        return _load_scoped(project_root)

    # ── Explicit path: legacy single-file load (unchanged) ────────────────
    default_config_file = get_config_file().expanduser().resolve(strict=False)
    config_file = config_file.expanduser().resolve(strict=False)
    is_default_config_file = config_file == default_config_file
    logger.debug("Loading config from file: {file}", file=config_file)

    if is_default_config_file and not config_file.exists():
        migration_error = _migrate_json_config_to_toml()
        if migration_error is not None:
            raise ConfigError(
                f"Legacy config file has incompatible settings; please fix or "
                f"rename/delete {migration_error.config_file} to continue. "
                f"Errors: {migration_error.errors}"
            ) from None

    if not config_file.exists():
        config = get_default_config()
        logger.debug("No config file found, creating default config: {config}", config=config)
        save_config(config, config_file)
        config.is_from_default_location = is_default_config_file
        config.source_file = config_file
        return config

    try:
        config_text = config_file.read_text(encoding="utf-8")
        if config_file.suffix.lower() == ".json":
            data = json.loads(config_text)
        else:
            data = tomlkit.loads(config_text)
        config = Config.model_validate(data)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in configuration file {config_file}: {e}") from e
    except TOMLKitError as e:
        raise ConfigError(f"Invalid TOML in configuration file {config_file}: {e}") from e
    except ValidationError as e:
        raise ConfigError(f"Invalid configuration file {config_file}: {e}") from e
    config.is_from_default_location = is_default_config_file
    config.source_file = config_file
    return config
```

- [ ] **Step 4: Run the two new tests**

```bash
.venv/bin/pytest tests/core/test_config.py::test_load_config_explicit_path_bypasses_scoping tests/core/test_config.py::test_load_config_no_args_uses_scope_resolution -v
```

Expected: both PASS.

- [ ] **Step 5: Run the full config test suite**

```bash
.venv/bin/pytest tests/core/test_config.py -v
```

Expected: all tests PASS. If `test_load_config_sets_source_file` fails because `source_scopes` is now non-empty, update its assertion to only check `source_file` and `is_from_default_location`.

- [ ] **Step 6: Run the broader test suite**

```bash
.venv/bin/pytest tests/ -x -q --ignore=tests/e2e 2>&1 | tail -30
```

Expected: no new failures. Fix any failures before committing.

- [ ] **Step 7: Run the linter/formatter**

```bash
cd /home/ai/Projects/pythinker-code-main && make check-pythinker-code
```

Expected: all checks pass. Fix any ruff errors before committing.

- [ ] **Step 8: Commit**

```bash
git add src/pythinker_code/config.py tests/core/test_config.py
git commit -m "feat(config): wire load_config to scope resolution pipeline

When called with no explicit file path, load_config now discovers
User → Project → Local scopes relative to the nearest .git root,
merges them with type-based rules, overlays PYTHINKER_* env vars,
and validates once through Pydantic with provenance-enriched errors.
Explicit --config path continues to bypass scope resolution."
```

---

## Self-Review Checklist

- [x] **`_find_project_root`** — Task 1 ✓
- [x] **`ensure_gitignored`** — Task 2 ✓ (including FileNotFoundError / create-if-absent, trailing newline, comment hygiene)
- [x] **`SCOPE_LOCKED_PATHS`, `DEDUP_LIST_FIELDS`, `ENV_FIELD_MAP`** — Task 3 ✓
- [x] **`_set_nested`, `_lookup_provenance`** — Task 3 ✓ (integer index bypass in lookup)
- [x] **`_check_scope_locks`** with path-level check — Task 4 ✓ (`feedback.api_key` locked, `feedback.endpoint_url` allowed)
- [x] **`_type_based_merge`** with all three dispatch branches + dedup — Task 5 ✓
- [x] **`_apply_env_vars`** with full `ENV_FIELD_MAP` — Task 6 ✓
- [x] **`source_scopes` field** on `Config` — Task 7 ✓ (exclude=True, not serialised)
- [x] **`_load_scoped`** five-step pipeline — Task 8 ✓ (auto-gitignore in metadata step)
- [x] **`load_config` wiring + regression sweep** — Task 9 ✓
- [x] **Backward compatibility** — explicit `--config` path still bypasses scoping (Task 9 Step 3)
- [x] **All test names** reference functions defined in earlier tasks — no forward references
- [x] **Human-readable scope strings** passed as `scope` param (file paths, not tags like `"local"`)
- [x] **Provenance base-case** for list: `scope` alone when no prior entry (Task 5 impl)
