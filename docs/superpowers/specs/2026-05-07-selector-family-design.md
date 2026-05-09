# Selector Family Port — Design Spec

**Date:** 2026-05-07
**Branch:** tui-pi-foundation
**Status:** Approved (revised after reading Pi source)

---

## Summary

Port all 11 Pi-style selector screens to Pythinker using Approach B: `run_selector()` where the UX fits a flat filterable list; focused standalone modules for UX paradigms that fundamentally differ (model with scope-toggle, session with full tree/search/delete UX, settings key/value editor, multi-toggle ordering, grouped resource manager).

This spec covers three implementation tiers that should ship as three separate plans:

- **Plan A** — Tier 1–2: theme, thinking, show\_images, extension, oauth + `selector.py` extensions
- **Plan B** — Tier 3: model migration, session migration (complex)
- **Plan C** — Tier 4: settings, scoped\_models, config

---

## File Map

```
src/pythinker_code/ui/shell/
  selector.py                 ← extend: SelectorHeader + on_change callback
  selectors/
    __init__.py               ← re-exports all run_* functions
    theme.py                  ← run_theme_selector()
    thinking.py               ← run_thinking_selector()
    show_images.py            ← run_show_images_selector()
    extension.py              ← run_extension_selector()
    oauth.py                  ← run_oauth_selector()
    model.py                  ← run_model_selector()  (replaces model_picker.py)
    session.py                ← run_session_selector() (replaces session_picker.py)
    session_search.py         ← pure search/sort functions (port of session-selector-search.ts)
    settings.py               ← run_settings_selector()
    scoped_models.py          ← run_scoped_models_selector()
    config.py                 ← run_config_selector()
    # tree.py intentionally deferred — blocked on session tree data model

tests/ui_and_conv/
  test_selectors_simple.py       ← Tier 1 unit tests
  test_selector_groups.py        ← SelectorHeader nav unit tests
  test_settings_selector.py      ← SettingItem cycling + cancel
  test_scoped_models_selector.py ← toggle / reorder / enable-all / clear-all
```

Existing `model_picker.py` and `session_picker.py` become one-line delegation wrappers for one release cycle, then are deleted once all callers are updated.

---

## Section 1: `selector.py` Extensions

Two small additions to `selector.py` — no behavior changes to existing code:

### 1a. `SelectorHeader`

```python
@dataclass(frozen=True, slots=True)
class SelectorHeader:
    label: str  # rendered as a section divider, not selectable
```

`SelectorConfig.items` type changes from `Sequence[SelectorItem[T]]` to
`Sequence[SelectorItem[T] | SelectorHeader]`.

Render loop: header rows use a distinct style (`class:slash-completion-menu.meta`)
and are skipped by cursor nav (up/down wraps past them).

Used by: `selectors/config.py` (user-scope / project-scope group dividers).
Not used by `model_selector` — Pi renders models in a flat list sorted by provider.

### 1b. `on_change` callback

```python
@dataclass(frozen=True, slots=True)
class SelectorConfig[T]:
    ...
    on_change: Callable[[T], None] | None = None
```

Called whenever the cursor moves to a new `SelectorItem`. Used by `theme_selector`
for live preview. No-op when `None`.

### 1c. Width note

`selector.py` currently hardcodes `width = 80` in `items_text()`. Model and oauth
selectors use `truncateToWidth` in Pi. For this port, keep `width = 80` as the
default since prompt_toolkit `FormattedTextControl` doesn't expose render width.
Revisit if long model names truncate badly in practice.

---

## Section 2: Tier 1 — Simple Selectors (Plan A)

All four call `run_selector()` directly. Each file is ~20–40 lines.

### `selectors/theme.py`

```python
run_theme_selector(
    current_theme: str,
    available_themes: list[str],
    on_preview: Callable[[str], None] | None = None,
) -> str | None
```

- Items built from `available_themes`; item matching `current_theme` gets `is_current=True`.
- `SelectorConfig.on_change = on_preview` for live preview.

### `selectors/thinking.py`

```python
ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]

LEVEL_DESCRIPTIONS: dict[ThinkingLevel, str] = {
    "off": "No reasoning",
    "minimal": "Very brief reasoning (~1k tokens)",
    "low": "Light reasoning (~2k tokens)",
    "medium": "Moderate reasoning (~8k tokens)",
    "high": "Deep reasoning (~16k tokens)",
    "xhigh": "Maximum reasoning (~32k tokens)",
}

run_thinking_selector(
    current_level: ThinkingLevel,
    available_levels: list[ThinkingLevel],
) -> ThinkingLevel | None
```

Also replaces the `ChoiceInput` call for thinking on/off in the `/model` slash command.

### `selectors/show_images.py`

```python
run_show_images_selector(current: bool) -> bool | None
```

2-item list: `Yes` / `No`. Filter disabled (`enable_filter=False`).

### `selectors/extension.py`

```python
run_extension_selector(
    title: str,
    options: list[str],
    *,
    current: str | None = None,
    timeout: float | None = None,
) -> str | None
```

Generic caller-supplied option list. `timeout` is implemented in `extension.py`
using `asyncio.wait_for` — not a `selector.py` concern.

---

## Section 3: Tier 2 — OAuth Selector Migration (Plan A)

`selectors/oauth.py` extracts the provider-picker from the existing `oauth.py` handler.

```python
@dataclass(frozen=True, slots=True)
class OAuthProviderEntry:
    id: str                          # platform id (e.g. "anthropic", "openrouter")
    name: str                        # display name
    auth_type: Literal["oauth", "api_key"]

@dataclass(frozen=True, slots=True)
class OAuthProviderStatus:
    source: Literal["environment", "runtime", "fallback", "models_json_key",
                    "models_json_command", "configured", "unconfigured"]
    label: str | None = None

run_oauth_selector(
    providers: list[OAuthProviderEntry],
    get_status: Callable[[str], OAuthProviderStatus],
    *,
    action: Literal["login", "logout"] = "login",
) -> str | None  # returns provider id
```

Each row shows the provider name + status indicator (✓ configured, ✓ env: API key,
• unconfigured). Pi's `formatStatusIndicator()` logic is ported inline.
Auth steps remain in `oauth.py`; only the list picker is extracted.

---

## Section 4: Tier 3 — Existing Picker Migration (Plan B)

### `selectors/model.py` — migrates `model_picker.py`

Pi's model selector is a **flat list** (not group-divided), sorted: current model
first, then sorted by provider label. Provider names appear as a `[provider]` badge
on each row, not as group headers. `SelectorHeader` is NOT used here.

Additional Pi features to port:

- **Scope toggle** (Tab): all models ↔ scoped models (session-local subset from
  `run_scoped_models_selector`). Only shown when a scoped set is active.
- **Async load** with error display (models.json parse errors shown in red).
- Scroll indicator `(N/total)` when list exceeds visible window.
- Model name displayed below the list for the selected item.
- Fuzzy filter (type-to-search, same as current `model_picker.py`).

The caller passes a flat `list[ModelEntry]` — not `list[ProviderGroup]`. The
existing `ProviderGroup` grouping in `model_picker.py` is a Pythinker-specific
concept not present in Pi; the new selector does not use it. `ModelEntry` already
exists in `model_picker.py` (`name`, `display`, `model_id`).

```python
@dataclass(frozen=True, slots=True)
class ScopedModelItem:
    model_name: str      # config key
    thinking_level: str | None = None

run_model_selector(
    models: list[ModelEntry],
    *,
    current_model_name: str | None = None,
    scoped_models: list[ScopedModelItem] | None = None,
) -> str | None  # returns model config key (ModelEntry.name)
```

Custom `Application` (preserves `model_picker.py` pattern; scope-toggle requires
state that doesn't fit `run_selector()`). `model_picker.py` becomes a one-line
wrapper that flattens its `ProviderGroup` list into `ModelEntry` items and delegates.

### `selectors/session.py` — migrates `session_picker.py`

Pi's session selector (1023 lines) is the most feature-rich picker. Full feature
list to port:

**Navigation & display:**
- Scope toggle (Tab): current folder ↔ all sessions
- Sort mode toggle: threaded / recent / fuzzy (separate keybinding)
- Name filter toggle: all / named only (separate keybinding)
- Path toggle: show/hide working directory per session row
- Scroll with `(N/total)` indicator

**Search:**
- Type-to-filter (fuzzy by default)
- Regex mode: `re:<pattern>`
- Phrase mode: `"quoted string"` exact match
- Sort switches to "relevance" mode when query is non-empty

**Tree display (threaded mode, no query):**
- Sessions organized as parent/child tree based on `parentSessionPath`
- ASCII box-drawing connectors (depth + isLast + ancestorContinues tracking)
- Root-level nodes sorted by modified date descending

**Destructive actions:**
- Delete selected session: dedicated key → confirmation prompt (separate hint line) → execute
- Cannot delete current session (guarded with error message)
- Rename selected session: opens inline input

**Status:**
- Loading progress indicator while sessions are fetched
- Transient status messages (info / error) with auto-hide

```python
run_session_selector(
    work_dir: HostPath,
    current_session: Session,
) -> str | None  # returns session ID (not file path)
```

**Return value is session ID, not file path.** Both existing callers compare the
result to `current_session.id` (`slash.py:622`) and pass it to
`Reload(session_id=...)` (`slash.py:635`) or treat it as `session_id`
(`cli/__init__.py:979`). File paths are used *internally* only (tree rendering,
delete/rename operations). The session list is loaded with `Session` objects that
carry both `id` and `path`; the selector resolves path → id before returning.

`session_search.py` — pure functions ported from Pi's `session-selector-search.ts`:

```python
# session_search.py
class SortMode(Enum):
    THREADED = "threaded"
    RECENT = "recent"
    FUZZY = "fuzzy"

class NameFilter(Enum):
    ALL = "all"
    NAMED_ONLY = "named"

@dataclass(frozen=True, slots=True)
class ParsedSearchQuery:
    raw: str
    mode: Literal["fuzzy", "regex", "phrase"]
    pattern: str  # normalized (stripped quotes for phrase, stripped "re:" for regex)

def parse_search_query(raw: str) -> ParsedSearchQuery: ...
def filter_and_sort_sessions(
    sessions: list[Session],
    query: ParsedSearchQuery,
    sort_mode: SortMode,
    name_filter: NameFilter,
    work_dir: HostPath,
) -> list[Session]: ...
def has_session_name(session: Session) -> bool: ...
```

Custom `Application` — scope/sort/name toggles with async reload don't fit
`run_selector()`. `session_picker.py` becomes a one-line wrapper.

---

## Section 5: Tier 4 — Complex New Selectors (Plan C)

### `selectors/settings.py`

Mirrors Pi's `SettingsList`. A key/value editor where Enter cycles a setting's
value; Esc exits.

```python
@dataclass(frozen=True, slots=True)
class SettingItem:
    id: str
    label: str
    description: str
    current_value: str
    values: list[str]   # options to cycle through

run_settings_selector(items: list[SettingItem]) -> dict[str, str] | None
# Returns {id: new_value} for changed items, or None on cancel.
```

Custom `Application`. No type-to-filter — settings list is short.
Key bindings: ↑↓ navigate, Enter cycle value, Esc cancel, Ctrl+C cancel.

The `/settings` slash command currently shows a Rich table (read-only). After this
work it gains an interactive editor: builds `SettingItem` rows from `Config` fields,
applies returned diffs to the live config, then shows the updated table.

### `selectors/scoped_models.py`

Multi-toggle with ordering. Session-local override of which models are active.

```python
@dataclass(frozen=True, slots=True)
class ScopedResult:
    kind: Literal["unchanged", "all_enabled", "subset"]
    ids: list[str]  # non-empty only when kind == "subset"

SCOPED_UNCHANGED = ScopedResult(kind="unchanged", ids=[])

run_scoped_models_selector(
    all_models: list[ModelEntry],
    enabled_ids: list[str] | None,  # None = all enabled
) -> ScopedResult
# Returns:
#   ScopedResult(kind="unchanged", ...)  — user cancelled (Esc)
#   ScopedResult(kind="all_enabled", ...)— cleared filter ("all")
#   ScopedResult(kind="subset", ids=...) — explicit ordered list
```

Key bindings: ↑↓ navigate, Space toggle, Alt+↑/↓ reorder, `a` enable-all,
`A` clear-all, Enter commit, Esc cancel. Custom `Application`.

### `selectors/config.py`

Grouped resource manager. Enables/disables extensions, skills, prompts, themes
by source scope (user / project). Uses `SelectorHeader` for scope group dividers.

```python
@dataclass
class ConfigResource:
    path: str
    display_name: str
    resource_type: Literal["extensions", "skills", "prompts", "themes"]
    scope: Literal["user", "project"]
    enabled: bool

run_config_selector(resources: list[ConfigResource]) -> dict[str, bool] | None
# Returns {path: enabled} for changed items, or None on cancel.
```

Key bindings: ↑↓ navigate, Space toggle, type to filter, Enter commit, Esc cancel.
Custom `Application` with `SelectorHeader` group rows.

### `tree_selector` — deferred

Intentionally not implemented in this spec. Blocked on verifying the session tree
data model (`SessionManager.get_tree()` or equivalent). Will be a separate spec
once the data model is confirmed. Do not create a stub file.

---

## Section 6: Slash-Command Wiring

Updates to `slash.py`:

| Command | Calls | Notes |
|---------|-------|-------|
| `/model` | `run_model_selector()` | Replace `ModelPickerApp` call |
| `/theme` | `run_theme_selector()` | New command |
| `/thinking` | `run_thinking_selector()` | New command; also replaces ChoiceInput in `/model` handler |
| `/settings` | `run_settings_selector()` | Upgrades read-only table to interactive editor |
| `/login` | `run_oauth_selector()` | Migrate provider picker from `oauth.py` |
| `/models-scope` | `run_scoped_models_selector()` | New command |
| `/config` | `run_config_selector()` | New command |
| `/session` | `run_session_selector()` | Replace `SessionPickerApp` call |

Remaining `ChoiceInput` calls in `slash.py` (editor picker at line 356,
undo turn picker at line 957) are out of scope for this spec.

---

## Section 7: Testing

All tests follow the pattern in `test_tui_card_selector.py` — pure state/render
logic, no TTY.

| Test file | What it tests |
|-----------|---------------|
| `test_selectors_simple.py` | `SelectorConfig` builds correctly for theme, thinking, show\_images, extension; `is_current` placement; on\_change fires on move |
| `test_selector_groups.py` | `SelectorHeader` rows appear in correct positions; cursor nav skips them; wraps correctly |
| `test_settings_selector.py` | Cycling values; multi-item changes accumulate; cancel returns `None` |
| `test_scoped_models_selector.py` | Toggle, reorder (Alt+↑↓), enable-all, clear-all, cancel returns `ScopedResult(kind="unchanged")` |
| `test_session_search.py` | `parse_search_query` handles fuzzy/regex/phrase; `filter_and_sort_sessions` correct results per sort mode and name filter |

Session selector UI tests are integration/manual — state machine is async and TTY-bound.

---

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Model selector: flat list, not group-divided | Pi renders models flat with `[provider]` badge, current-first. Group headers were assumed from the old `model_picker.py` pattern but not present in Pi source. |
| `SelectorHeader` kept for config\_selector | Grouped resource display (user-scope / project-scope dividers) still benefits from inline headers. |
| Session picker: custom `Application` | 1023-line Pi source with scope, sort, name-filter, tree display, search, delete, rename — far more than a scope toggle. Not reducible to `run_selector()`. |
| OAuth: add `auth_type` + status display | Pi shows ✓ configured / • unconfigured / ✓ env: per-provider. Without this, the picker loses meaningful signal. |
| Settings: new interactive `/settings` | Current command is read-only Rich table. This upgrades it to a proper editor. Not a ChoiceInput replacement — ChoiceInput is not used in `/settings`. |
| `ScopedResult` dataclass vs. `| object` | Typed discriminated result; `| object` defeats Pyright and hides caller bugs. |
| `tree_selector` deferred, no stub file | No stub — a file that always raises `NotImplementedError` is dead code that creates a false import surface. |
| Three implementation plans | Plan B (session) and Plan C (settings/config) are each substantial; splitting avoids one giant plan that can't be reviewed or shipped incrementally. |
| Timeout in `extension.py`, not `selector.py` | `asyncio.wait_for` in the callee keeps `selector.py` clean; timeout is only needed for the extension use case. |
| Session selector returns ID, not path | Pi's session selector returns a file path; Pythinker's callers at `slash.py:622/635` and `cli/__init__.py:979` all treat the return value as a session ID. Translating path → ID inside `run_session_selector` avoids touching all callers in Plan B scope. |
| `session_search.py` as a separate module | Pi separates `session-selector-search.ts` as pure, testable functions. Same split here makes the search/sort logic independently unit-testable without spinning up a full `Application`. |
| Model selector takes `list[ModelEntry]`, not `list[ProviderGroup]` | Pi renders a flat list; `ProviderGroup` is a Pythinker-only concept from the old `model_picker.py`. The one-line delegation wrapper flattens groups → entries so existing callers of `model_picker.py` need no changes in Plan B. |
