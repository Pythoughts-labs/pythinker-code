# Pythinker Multi-Scope Configuration Design

**Date:** 2026-06-03
**Branch:** `feat/scoped-config`
**Status:** Approved — ready for implementation planning

---

## Overview

Pythinker currently loads a single flat config from `~/.pythinker/config.toml` (user-global only). This design adds a three-scope layered system — **User**, **Project**, and **Local** — with type-based merging and hard security locks, inspired by Claude Code's settings architecture.

---

## Scope Hierarchy

```text
Priority    Scope       File Location                             Secrets Allowed?
──────────────────────────────────────────────────────────────────────────────────
  1 (high)  Env Vars    PYTHINKER_* environment variables         ✅ yes
  2         Local       .pythinker/config.local.toml              ❌ locked
  3         Project     .pythinker/config.toml                    ❌ locked
  4 (low)   User        ~/.pythinker/config.toml                  ✅ yes
```

**Project root resolution:** Walk up from `cwd` to the nearest `.git/`. If no git root is found, project and local scopes are silently skipped — pythinker stays fully usable outside git repositories.

**Mental model for users:**
> *Project configs dictate behavior and structure. User configs dictate identity and access.*

---

## File Locations

```text
~/.pythinker/
└── config.toml               ← User scope (existing file, unchanged format)

<git-root>/
└── .pythinker/
    ├── config.toml           ← Project scope (committed to git)
    └── config.local.toml     ← Local scope (gitignored, personal overrides)
```

`.pythinker/config.local.toml` is automatically added to the project's `.gitignore` when pythinker first detects or creates it.

---

## Merge Rules

Applied in order: User → Project → Local (Local wins for scalars).

| Field type | Behavior | Example |
|---|---|---|
| **Scalar** (str, bool, int, float) | Deepest scope wins | `theme = "light"` in local overrides `"dark"` in user |
| **List** | Concatenate widest→deepest | All `hooks` from user + project + local run |
| **List (dedup fields)** | Concatenate then deduplicate, preserving first-seen order | `extra_skill_dirs`, `allowed_domains` |
| **Dict** (nested object) | Deep-merge recursively | `tui.style` overrides without wiping `tui.smooth_streaming` |

**Dedup fields:** `extra_skill_dirs`, `allowed_domains`. Order-preserving deduplication via `dict.fromkeys()`.

**Env vars** always win over all file scopes for scalars. They are not subject to scope-lock checks.

---

## Security: Scope-Locked Paths

The following paths are **invalid in project and local scope** because they contain secrets that must not be committed to git:

```python
SCOPE_LOCKED_PATHS: frozenset[tuple[str, ...]] = frozenset({
    ("providers",),            # entire providers block (contains api_key per provider)
    ("services",),             # entire services block (contains api_key fields)
    ("feedback", "api_key"),   # only the api_key leaf; feedback.endpoint_url is allowed
})
```

Non-secret feedback fields (`endpoint_url`, `github_client_id`, `github_repo`) are **allowed** in project scope.

**Violation error message:**

```text
ConfigError: 'providers' cannot be set in .pythinker/config.toml (project scope).
  Move it to ~/.pythinker/config.toml or set PYTHINKER_PROVIDER_<NAME>_API_KEY
  in the environment.
```

---

## Environment Variable Map

Flat top-level scalar fields map to `PYTHINKER_<FIELD_NAME_UPPER>` env vars. Pydantic coerces string values to the correct type during `model_validate()`.

```python
ENV_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "PYTHINKER_DEFAULT_MODEL":   ("default_model",),
    "PYTHINKER_THEME":           ("theme",),
    "PYTHINKER_DEFAULT_YOLO":    ("default_yolo",),
    "PYTHINKER_DEFAULT_PLAN_MODE": ("default_plan_mode",),
    "PYTHINKER_TELEMETRY":       ("telemetry",),
    # … one entry per top-level scalar field in Config
}
```

Env var provenance is recorded as `f"env {env_key}"` (e.g. `"env PYTHINKER_THEME"`) so validation errors attribute the exact variable.

---

## Resolution Pipeline

```text
cwd → _find_project_root()
        found: /my-project/.git  →  project_root = /my-project
        not found                →  project_root = None  (skip project + local)

─── INGEST ──────────────────────────────────────────────────────────────────
user_dict    = tomlkit.loads(~/.pythinker/config.toml)       or {}
project_dict = tomlkit.loads(.pythinker/config.toml)         or {}  (skipped if no root)
local_dict   = tomlkit.loads(.pythinker/config.local.toml)   or {}  (skipped if no root)

  TOMLKitError on any file → ConfigError("Invalid TOML in <file>: …")

─── GUARD ───────────────────────────────────────────────────────────────────
_check_scope_locks(project_dict, ".pythinker/config.toml")
_check_scope_locks(local_dict,   ".pythinker/config.local.toml")

  Walks SCOPE_LOCKED_PATHS in the raw dict; raises ConfigError on first violation.

─── MERGE ───────────────────────────────────────────────────────────────────
provenance: dict = {}
merged = _type_based_merge({},     user_dict,    provenance, "~/.pythinker/config.toml")
merged = _type_based_merge(merged, project_dict, provenance, ".pythinker/config.toml")
merged = _type_based_merge(merged, local_dict,   provenance, ".pythinker/config.local.toml")

  Scalar:  provenance["theme"] = ".pythinker/config.local.toml"
  List:    provenance["hooks"] = "~/.pythinker/config.toml+.pythinker/config.toml"
           (base-case: if no existing entry, provenance[key] = scope)
  Dict:    provenance["tui"]["style"] = ".pythinker/config.toml"

─── ENV OVERLAY ─────────────────────────────────────────────────────────────
For each (env_key, path) in ENV_FIELD_MAP:
  if os.environ.get(env_key) is not None:
    _set_nested(merged, path, value)
    _set_nested(provenance, path, f"env {env_key}")

─── VALIDATE ────────────────────────────────────────────────────────────────
try:
    config = Config.model_validate(merged)
except ValidationError as exc:
    enriched = []
    for err in exc.errors():
        scope = _lookup_provenance(provenance, tuple(err["loc"]))
        field = ".".join(str(p) for p in err["loc"])
        enriched.append(f"  {field}: {err['msg']}  [from {scope}]")
    raise ConfigError("Invalid configuration:\n" + "\n".join(enriched)) from exc
```

---

## Key Internal Functions

### `_find_project_root(cwd: Path) -> Path | None`

Walks parent directories from `cwd` looking for `.git/`. Returns the directory containing `.git/`, or `None`.

### `_check_scope_locks(scope_dict: dict, scope_name: str) -> None`

For each path in `SCOPE_LOCKED_PATHS`, walks `scope_dict` following the path tuple. Raises `ConfigError` on the first found violation. Check is on raw dict keys before Pydantic validation.

### `_type_based_merge(base: dict, overlay: dict, provenance: dict, scope: str) -> dict`

Recursive merge with type dispatch:
- **Scalar:** `base[key] = overlay[key]`; `provenance[key] = scope`
- **List:** `base[key] = base[key] + overlay[key]`; apply `dict.fromkeys()` if key in `DEDUP_LIST_FIELDS`; `provenance[key] = f"{existing}+{scope}" if existing else scope`
- **Dict:** recurse into `_type_based_merge(base[key], overlay[key], provenance.setdefault(key, {}), scope)`

### `_apply_env_vars(merged: dict, provenance: dict) -> None`

Iterates `ENV_FIELD_MAP`. For each key present in `os.environ`, calls `_set_nested` on both `merged` and `provenance`. Stores the raw string; Pydantic coerces the type during `model_validate()`.

### `_set_nested(d: dict, path: tuple[str, ...], value: object) -> None`

Walks `path` into `d`, creating intermediate dicts as needed, sets the leaf.

### `_lookup_provenance(prov: dict | str, loc: tuple) -> str`

```python
def _lookup_provenance(prov: dict | str, loc: tuple) -> str:
    if not loc or isinstance(prov, str):
        return prov if isinstance(prov, str) else "unknown scope"
    head, *tail = loc
    # Pydantic uses integer indices for list elements — map back to collection scope
    if isinstance(head, int):
        return prov if isinstance(prov, str) else _lookup_provenance(prov, tuple(tail))
    if isinstance(prov, dict) and head in prov:
        return _lookup_provenance(prov[head], tuple(tail))
    return "unknown scope"
```

---

## `utils/gitignore.py` — `ensure_gitignored`

```text
ensure_gitignored(git_root: Path, pattern: str, comment: str = "") -> None
```

1. Locate `git_root / ".gitignore"`.
2. If absent: create file from scratch (handles `FileNotFoundError`).
3. Read current content; if `pattern` already appears as a line, return (no-op).
4. Check for trailing newline; append one if missing.
5. Append `# {comment}\n{pattern}\n` (comment line omitted if `comment` is empty).

Called during `_load_scoped` when local config is first written or detected, with:

```python
ensure_gitignored(project_root, ".pythinker/config.local.toml", comment="Added by pythinker")
```

---

## `Config` Model Changes

Two new metadata fields (both `exclude=True` — never serialised):

```python
source_scopes: dict[str, Path] = Field(default_factory=dict, exclude=True)
# e.g. {"user": Path("~/.pythinker/config.toml"),
#        "project": Path(".pythinker/config.toml"),
#        "local": Path(".pythinker/config.local.toml")}
```

`source_file` and `is_from_default_location` retain their existing semantics:
- `source_file` → user config path when resolved via scope pipeline; explicit path when `--config` is used
- `is_from_default_location` → `True` when user scope came from the default `~/.pythinker/config.toml`

---

## Backward Compatibility

| Scenario | Behavior |
|---|---|
| `load_config(explicit_path)` | Unchanged — single file, no scope resolution |
| `load_config()` outside git repo | User config only — identical to today |
| `load_config()` in git repo, no `.pythinker/` | User config only — silent fallback |
| Existing `~/.pythinker/config.toml` format | No change — still the user scope file |
| JSON→TOML migration logic | Unaffected — applies only to user scope file |
| `--config` CLI flag | Bypasses scope resolution entirely |

---

## Public API Changes

```python
# Unchanged signature — now routes through scope resolution when config_file is None
def load_config(config_file: Path | None = None) -> Config: ...

# New internal entry point (not exported)
def _load_scoped(project_root: Path | None) -> Config: ...
```

No call sites in `cli/__init__.py`, `app.py`, or elsewhere need changes — existing `load_config()` calls automatically get scope resolution.

---

## Error Message Examples

```text
# Scope-lock violation
ConfigError: 'providers' cannot be set in .pythinker/config.toml (project scope).
  Move it to ~/.pythinker/config.toml or set PYTHINKER_PROVIDER_<NAME>_API_KEY
  in the environment.

# Validation error with scope attribution
ConfigError: Invalid configuration:
  default_model: Value 'gpt-9-turbo' not found in models  [from .pythinker/config.local.toml]
  tui.style: Invalid value 'rainbow'                       [from .pythinker/config.toml]

# Env var validation error
ConfigError: Invalid configuration:
  theme: Invalid value 'neon'  [from env PYTHINKER_THEME]
```

---

## Test Plan

### Unit tests (`tests/core/test_config.py`)

**Merge algorithm (`_type_based_merge`)**
- `scalar_override` — local beats project beats user
- `list_concat` — user + project + local order preserved
- `list_dedup` — duplicate path in `extra_skill_dirs` appears once
- `dict_deep_merge` — nested key override without wiping siblings
- `provenance_scalar` — `provenance["theme"] == ".pythinker/config.local.toml"`
- `provenance_list` — composite string for multi-scope list
- `provenance_nested` — `provenance["tui"]["style"] == ".pythinker/config.toml"`
- `list_base_case` — single scope list → scope name only (no `+`)

**Scope locks (`_check_scope_locks`)**
- `providers_in_project` — ConfigError, message cites file
- `services_in_local` — ConfigError
- `feedback_api_key_locked` — ConfigError on `{"feedback": {"api_key": "x"}}`
- `feedback_url_allowed` — no error on `{"feedback": {"endpoint_url": "https://…"}}`
- `clean_dict` — no error when locked paths absent

**Provenance lookup (`_lookup_provenance`)**
- `scalar_path` — `loc=("theme",)` → correct scope string
- `nested_path` — `loc=("tui","style")` → correct scope string
- `list_index` — `loc=("hooks", 0, "command")` → parent collection scope (no crash)
- `partial_path` — `loc=("tui","nonexistent")` → `"unknown scope"`
- `empty_loc` — `loc=()` → returns provenance root value

**Env var overlay (`_apply_env_vars`)**
- `known_key` — `PYTHINKER_THEME=light` → `merged["theme"]=="light"`, provenance set
- `unknown_key` — `PYTHINKER_XYZZY` ignored (not in `ENV_FIELD_MAP`)
- `bool_coercion` — `PYTHINKER_DEFAULT_YOLO=true` stored as string; Pydantic coerces on validate

### Integration tests (full pipeline)
- `all_three_scopes` — three TOML files on disk → correct merged Config
- `user_only` — no git root → user config only
- `project_absent` — git root found, no `.pythinker/` → user config only
- `local_absent` — project present, local absent → user + project merged
- `scope_lock_violation` — providers in project → ConfigError before validation
- `validation_error_attribution` — bad `default_model` in local → error names local file
- `env_override` — `PYTHINKER_THEME` beats local file value
