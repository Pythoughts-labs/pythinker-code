# Security & Code Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply all confirmed findings from the 2026-05-21 comprehensive code scan: 12 security/config issues, 10 code quality issues, 2 architecture fixes, and 2 dependency fixes.

**Architecture:** Changes are organized into independent batches ordered by risk (low to high). Each task is a surgical change to a single concern. No cross-task dependencies.

**Tech Stack:** Python 3.14, asyncio, Jinja2, pydantic, pytest

---

## File Map

| File | Tasks |
|------|-------|
| `src/pythinker_code/config.py` | T1 |
| `src/pythinker_code/auth/oauth.py` | T1, T11 |
| `src/pythinker_code/wire/types.py` | T2 |
| `src/pythinker_code/hooks/engine.py` | T2 |
| `src/pythinker_code/soul/pythinkersoul.py` | T3 |
| `src/pythinker_code/web/api/sessions.py` | T4, T9 |
| `src/pythinker_code/soul/agent.py` | T4, T10 |
| `pyproject.toml` (root) | T5 |
| `packages/pythinker-core/pyproject.toml` | T5 |
| `src/pythinker_code/utils/broadcast.py` | T6 |
| `src/pythinker_code/events.py` | T7 |
| `src/pythinker_code/app.py` | T8 |
| `src/pythinker_code/web/store/sessions.py` | T9 |
| `src/pythinker_code/telemetry/otel.py` | T9 |
| `src/pythinker_code/telemetry/crash.py` | T9 |
| `src/pythinker_code/tools/utils.py` | T10 |
| `src/pythinker_code/web/api/config.py` | T12 |
| `examples/*/pyproject.toml` (8 files) | T13 |

---

### Task 1: File permission hardening — config.toml and credentials dir (A2, A4)

**Files:**
- Modify: `src/pythinker_code/config.py:450`
- Modify: `src/pythinker_code/auth/oauth.py:270`

The config.toml is written world-readable (umask default 0o644). The credentials dir is created 0o755. Both should be restricted to 0o600 / 0o700.

- [ ] **Step 1: Verify contextlib and os are imported in config.py**

Run: `grep -n "^import os\|^import contextlib" src/pythinker_code/config.py`

Expected: both present. If either is missing, add it at the top of the imports block.

- [ ] **Step 2: Add chmod after save_config write**

In `src/pythinker_code/config.py`, after the `with open(config_file, "w", ...) as f:` block (current line 454), add a chmod call. The complete function after the change:

```python
def save_config(config: Config, config_file: Path | None = None):
    config_file = config_file or get_config_file()
    logger.debug("Saving config to file: {file}", file=config_file)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_data = config.model_dump(mode="json", exclude_none=True)
    with open(config_file, "w", encoding="utf-8") as f:
        if config_file.suffix.lower() == ".json":
            f.write(json.dumps(config_data, ensure_ascii=False, indent=2))
        else:
            f.write(tomlkit.dumps(config_data))  # type: ignore[reportUnknownMemberType]
    with contextlib.suppress(OSError):
        os.chmod(config_file, 0o600)
```

- [ ] **Step 3: Add mode=0o700 to credentials dir mkdir**

In `src/pythinker_code/auth/oauth.py`, the `_credentials_dir()` function at line 268:

```python
def _credentials_dir() -> Path:
    path = get_share_dir() / "credentials"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/config.py src/pythinker_code/auth/oauth.py
git commit -m "fix(security): harden file permissions for config.toml and credentials dir"
```

---

### Task 2: Replace deprecated asyncio.get_event_loop() (R3)

**Files:**
- Modify: `src/pythinker_code/wire/types.py:320,413,464,564`
- Modify: `src/pythinker_code/hooks/engine.py:50`

`asyncio.get_event_loop()` is deprecated since Python 3.10 and will break in Python 3.14+. Replace with `asyncio.get_running_loop()` at all 5 call sites. These `_get_future()` methods are only called while a loop is running (from `wait()` / `resolve()` which are always called inside async contexts), so `get_running_loop()` is the correct replacement.

- [ ] **Step 1: Replace all 4 sites in wire/types.py**

Each site looks like:
```python
self._future = asyncio.get_event_loop().create_future()
```
Change to:
```python
self._future = asyncio.get_running_loop().create_future()
```

Affected lines: 320, 413, 464, 564.

Verify: `grep -n "get_event_loop" src/pythinker_code/wire/types.py`
Expected: no output.

- [ ] **Step 2: Replace in hooks/engine.py**

Same replacement at line 50.

Verify: `grep -n "get_event_loop" src/pythinker_code/hooks/engine.py`
Expected: no output.

- [ ] **Step 3: Confirm no remaining sites**

Run: `grep -rn "asyncio.get_event_loop()" src/pythinker_code/`
Expected: no output.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/wire/types.py src/pythinker_code/hooks/engine.py
git commit -m "fix(asyncio): replace deprecated get_event_loop() with get_running_loop()"
```

---

### Task 3: Fix steer queue TOCTOU race (R2)

**Files:**
- Modify: `src/pythinker_code/soul/pythinkersoul.py:595-596` and `927-928`

The pattern `while not queue.empty(): queue.get_nowait()` has a TOCTOU race — another coroutine can drain the queue between the `empty()` check and `get_nowait()`. Fix: use `try/except asyncio.QueueEmpty` which is atomic.

- [ ] **Step 1: Fix the drain loop in _flush_steer_queue (~line 595)**

Current code:
```python
while not self._steer_queue.empty():
    content = self._steer_queue.get_nowait()
    await self._inject_steer(content)
    wire_send(SteerInput(user_input=content))
    consumed = True
return consumed
```

Replace with:
```python
while True:
    try:
        content = self._steer_queue.get_nowait()
    except asyncio.QueueEmpty:
        break
    await self._inject_steer(content)
    wire_send(SteerInput(user_input=content))
    consumed = True
return consumed
```

- [ ] **Step 2: Fix the discard loop in _agent_loop (~line 927)**

Current code:
```python
while not self._steer_queue.empty():
    self._steer_queue.get_nowait()
```

Replace with:
```python
while True:
    try:
        self._steer_queue.get_nowait()
    except asyncio.QueueEmpty:
        break
```

- [ ] **Step 3: Verify asyncio.QueueEmpty is accessible**

Run: `python -c "import asyncio; print(asyncio.QueueEmpty)"`
Expected: `<class 'asyncio.queues.QueueEmpty'>`

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/soul/pythinkersoul.py
git commit -m "fix(concurrency): eliminate TOCTOU race in steer queue drain loops"
```

---

### Task 4: Code micro-fixes — redundant close, type annotation, rmtree (Q1, Q8, Q12)

**Files:**
- Modify: `src/pythinker_code/web/api/sessions.py:404` (remove `out.close()`)
- Modify: `src/pythinker_code/soul/agent.py:149` (fix type annotation)
- Modify: `src/pythinker_code/web/api/sessions.py:588` (add `ignore_errors=True`)

- [ ] **Step 1: Remove redundant out.close()**

In `src/pythinker_code/web/api/sessions.py`, the upload handler has `out.close()` inside a `with upload_path.open("wb") as out:` block. Delete the `out.close()` line — the context manager handles cleanup.

- [ ] **Step 2: Fix [None] * len() type annotation in agent.py**

In `src/pythinker_code/soul/agent.py`, line 149. Read lines 144–175 to understand the full `budgeted` usage. Change:
```python
budgeted: list[tuple[HostPath, str]] = [None] * len(discovered)  # type: ignore[list-item]
```
To:
```python
budgeted: list[tuple[HostPath, str] | None] = [None] * len(discovered)
```
Remove the `# type: ignore[list-item]` comment since the type is now correct.

After making this change, search for any downstream usage of `budgeted[i]` that assumes non-None and add explicit guards if needed (read lines 150–175 carefully).

- [ ] **Step 3: Add ignore_errors to shutil.rmtree**

In `src/pythinker_code/web/api/sessions.py`, line ~588:
```python
shutil.rmtree(session_dir)
```
Change to:
```python
shutil.rmtree(session_dir, ignore_errors=True)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/web/api/sessions.py src/pythinker_code/soul/agent.py
git commit -m "fix(quality): remove redundant close, fix budgeted type annotation, rmtree ignore_errors"
```

---

### Task 5: Dependency cleanup — remove ripgrepy, widen openai pin (D2, D4)

**Files:**
- Modify: `pyproject.toml` (root)
- Modify: `packages/pythinker-core/pyproject.toml`

- [ ] **Step 1: Remove ripgrepy from root pyproject.toml**

Find and delete the line `"ripgrepy==2.2.0",` from the `dependencies` list in `pyproject.toml`. The package is not imported anywhere in the codebase.

- [ ] **Step 2: Widen the openai version pin**

In `packages/pythinker-core/pyproject.toml`, change:
```
"openai>=2.14.0,<2.15.0",
```
To:
```
"openai>=2.14.0,<3",
```
This allows all 2.x security patch releases while blocking a potentially breaking 3.0 major.

- [ ] **Step 3: Update lockfile**

Run: `uv lock`
Expected: exits 0.

- [ ] **Step 4: Verify**

Run: `grep "ripgrepy" uv.lock`
Expected: no output.

Run: `grep 'name = "openai"' uv.lock -A3`
Expected: a version within `>=2.14.0,<3`.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml packages/pythinker-core/pyproject.toml uv.lock
git commit -m "fix(deps): remove unused ripgrepy, widen openai pin to <3"
```

---

### Task 6: BroadcastQueue — snapshot set before iterating (R10)

**Files:**
- Modify: `src/pythinker_code/utils/broadcast.py`

`publish()` and `publish_nowait()` iterate over `self._queues` while `subscribe()`/`unsubscribe()` can modify the set from concurrent coroutines. Fix: take a `list(self._queues)` snapshot before iterating.

- [ ] **Step 1: Write regression test**

Check if `tests/utils/` exists: `ls tests/utils/` — create `tests/utils/__init__.py` if the directory doesn't exist.

In `tests/utils/test_broadcast.py`:

```python
import asyncio
import pytest
from pythinker_code.utils.broadcast import BroadcastQueue


@pytest.mark.asyncio
async def test_publish_reaches_all_subscribers():
    bq: BroadcastQueue[int] = BroadcastQueue()
    q1 = bq.subscribe()
    q2 = bq.subscribe()
    await bq.publish(42)
    assert await q1.get() == 42
    assert await q2.get() == 42


@pytest.mark.asyncio
async def test_publish_nowait_after_unsubscribe_does_not_raise():
    bq: BroadcastQueue[int] = BroadcastQueue()
    q1 = bq.subscribe()
    q2 = bq.subscribe()
    bq.unsubscribe(q1)
    bq.publish_nowait(7)
    assert q2.get_nowait() == 7
```

Run: `python -m pytest tests/utils/test_broadcast.py -v 2>&1 | tail -20`
Expected: both pass (these verify basic behavior before and after the fix).

- [ ] **Step 2: Snapshot _queues in publish, publish_nowait, and shutdown**

In `src/pythinker_code/utils/broadcast.py`, update the three methods:

```python
async def publish(self, item: T) -> None:
    """Publish an item to all subscription queues."""
    queues = list(self._queues)
    await asyncio.gather(*(queue.put(item) for queue in queues))

def publish_nowait(self, item: T) -> None:
    """Publish an item to all subscription queues without waiting."""
    for queue in list(self._queues):
        queue.put_nowait(item)

def shutdown(self, immediate: bool = False) -> None:
    """Close all subscription queues."""
    for queue in list(self._queues):
        queue.shutdown(immediate=immediate)
    self._queues.clear()
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/utils/test_broadcast.py tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/utils/broadcast.py tests/utils/test_broadcast.py
git commit -m "fix(concurrency): snapshot BroadcastQueue._queues before iteration"
```

---

### Task 7: Store fire-and-forget task reference in events.py (Q2)

**Files:**
- Modify: `src/pythinker_code/events.py`

`loop.create_task(_runner())` at line 97 creates a task without keeping a reference. CPython may GC it before completion. Fix: add a module-level set that holds strong references until tasks complete.

- [ ] **Step 1: Read events.py lines 80–102**

Read `src/pythinker_code/events.py` offset 80, limit 25 to see the exact emit() method structure and the `loop.create_task(...)` call.

- [ ] **Step 2: Add _background_tasks set and wire up task lifecycle**

At the module level in `src/pythinker_code/events.py`, add:
```python
_background_tasks: set[asyncio.Task[None]] = set()
```

Then replace the `loop.create_task(_runner())` line with:
```python
_task = loop.create_task(_runner())
_background_tasks.add(_task)
_task.add_done_callback(_background_tasks.discard)
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_events.py tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/events.py
git commit -m "fix(async): retain strong reference to fire-and-forget event handler tasks"
```

---

### Task 8: Call PythinkerToolset.cleanup() from shutdown path (R8)

**Files:**
- Modify: `src/pythinker_code/app.py`

`PythinkerToolset.cleanup()` cancels MCP background loading and closes MCP client connections. It is never called. The right place is `PythinkerCLI.shutdown_background_tasks()` in `app.py`, which is invoked from `cli/__init__.py:843`.

- [ ] **Step 1: Verify contextlib is imported in app.py**

Run: `grep -n "^import contextlib" src/pythinker_code/app.py`
Expected: line present. If not, add it.

- [ ] **Step 2: Add toolset cleanup to shutdown_background_tasks**

Read `src/pythinker_code/app.py` at the start of `shutdown_background_tasks()` (line ~416). Add the following at the beginning of the method body, before any other shutdown logic:

```python
async def shutdown_background_tasks(self) -> None:
    # Cancel the startup managed-model refresh task
    if self._bg_refresh_task is not None and not self._bg_refresh_task.done():
        self._bg_refresh_task.cancel()

    # Cleanup MCP connections held by the toolset
    from pythinker_code.soul.toolset import PythinkerToolset

    toolset = self._soul._agent.toolset
    if isinstance(toolset, PythinkerToolset):
        with contextlib.suppress(Exception):
            await toolset.cleanup()

    # ... rest of existing method unchanged
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/app.py
git commit -m "fix(resource): call PythinkerToolset.cleanup() on CLI shutdown"
```

---

### Task 9: Add debug logging to silent exception swallowing (Q7)

**Files:**
- Modify: `src/pythinker_code/web/store/sessions.py:108`
- Modify: `src/pythinker_code/telemetry/otel.py:247,268,273,278`
- Modify: `src/pythinker_code/telemetry/crash.py:102,147`
- Modify: `src/pythinker_code/web/api/sessions.py:244`

All confirmed bare-swallow `except Exception: pass` sites. Add `logger.debug(...)` before each `pass` so failures surface in debug logs without changing behavior. The swallowing is intentional in all these locations — only logging is added.

For each file below, first verify `logger` is imported by running:
`grep -n "^logger\b\|^from.*import.*logger\|logger = " <file> | head -3`

- [ ] **Step 1: web/store/sessions.py — session title derivation**

Read lines 100–112. Add logging before `pass`:
```python
    except Exception:
        logger.debug("Failed to derive session title from context file", exc_info=True)
    return "Untitled"
```

- [ ] **Step 2: telemetry/otel.py — four shutdown failures**

Read lines 240–280. For the emit failure at ~247:
```python
    except Exception:
        logger.debug("OTel telemetry emit failed", exc_info=True)
```

For each of the three shutdown failures at ~268, ~273, ~278:
```python
    except Exception:
        logger.debug("OTel provider shutdown failed", exc_info=True)
```

- [ ] **Step 3: telemetry/crash.py — Sentry capture failures**

Read lines 95–150. At each `except Exception: pass` site (~102, ~147):
```python
    except Exception:
        logger.debug("Telemetry crash capture failed", exc_info=True)
```

- [ ] **Step 4: web/api/sessions.py — WebSocket replay**

Read lines 238–246. At the `except Exception: pass` at ~244:
```python
    except Exception:
        logger.debug("WebSocket wire replay failed", exc_info=True)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/web/store/sessions.py src/pythinker_code/telemetry/otel.py src/pythinker_code/telemetry/crash.py src/pythinker_code/web/api/sessions.py
git commit -m "fix(observability): add debug logging to intentional exception-swallowing sites"
```

---

### Task 10: Jinja2 SandboxedEnvironment for agent spec and tool descriptions (S2, S3)

**Files:**
- Modify: `src/pythinker_code/soul/agent.py:10-11`
- Modify: `src/pythinker_code/tools/utils.py:4`

Both files use `jinja2.Environment` for rendering file content. `SandboxedEnvironment` is a drop-in replacement that blocks attribute-access escape patterns. The custom delimiters (`${`, `}`) and all other constructor arguments work identically in `SandboxedEnvironment`.

- [ ] **Step 1: Write security regression test**

In `tests/core/test_agent_template_sandbox.py` (create):

```python
import pytest
from pathlib import Path


def test_sandboxed_env_blocks_dunder_attribute_access(tmp_path: Path):
    """SandboxedEnvironment must block attribute chain escapes."""
    from jinja2.sandbox import SandboxedEnvironment
    from jinja2 import StrictUndefined

    env = SandboxedEnvironment(
        variable_start_string="${",
        variable_end_string="}",
        undefined=StrictUndefined,
    )
    # A real attacker would chain .__class__.__mro__ etc.
    # The sandbox raises SecurityError on attribute access to __class__
    template = env.from_string("${'x'.__class__}")
    with pytest.raises(Exception):  # SecurityError
        template.render()
```

Run: `python -m pytest tests/core/test_agent_template_sandbox.py -v 2>&1 | tail -20`
Expected: PASS (this tests the sandbox itself works, before we wire it in).

- [ ] **Step 2: Update import in soul/agent.py**

Current:
```python
from jinja2 import Environment as JinjaEnvironment
from jinja2 import FileSystemLoader, StrictUndefined, TemplateError, UndefinedError
```

Replace with:
```python
from jinja2 import FileSystemLoader, StrictUndefined, TemplateError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment as JinjaEnvironment
```

- [ ] **Step 3: Update import in tools/utils.py**

Current:
```python
from jinja2 import Environment, Undefined
```

Replace with:
```python
from jinja2 import Undefined
from jinja2.sandbox import SandboxedEnvironment as Environment
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: no new failures. Existing templates using `${...}` syntax continue to work; sandbox only restricts dunder-attribute escapes.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/soul/agent.py src/pythinker_code/tools/utils.py tests/core/test_agent_template_sandbox.py
git commit -m "fix(security): use Jinja2 SandboxedEnvironment for agent spec and tool description rendering"
```

---

### Task 11: Enforce HTTPS for OAuth host env var override (A11)

**Files:**
- Modify: `src/pythinker_code/auth/oauth.py:185-190`

The `_oauth_host()` function accepts a `PYTHINKER_CODE_OAUTH_HOST` env var with no scheme validation. An HTTP URL would send OAuth tokens unencrypted.

- [ ] **Step 1: Write failing test**

In `tests/auth/test_oauth_host.py` (create or add to existing auth test file):

```python
import pytest


def test_oauth_host_rejects_http_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTHINKER_CODE_OAUTH_HOST", "http://evil.example.com")
    monkeypatch.delenv("PYTHINKER_OAUTH_HOST", raising=False)
    from pythinker_code.auth import oauth
    with pytest.raises(ValueError, match="HTTPS"):
        oauth._oauth_host()


def test_oauth_host_accepts_https_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTHINKER_CODE_OAUTH_HOST", "https://custom.example.com")
    monkeypatch.delenv("PYTHINKER_OAUTH_HOST", raising=False)
    from pythinker_code.auth import oauth
    assert oauth._oauth_host() == "https://custom.example.com"


def test_oauth_host_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PYTHINKER_CODE_OAUTH_HOST", raising=False)
    monkeypatch.delenv("PYTHINKER_OAUTH_HOST", raising=False)
    from pythinker_code.auth import oauth
    host = oauth._oauth_host()
    assert host.startswith("https://")
```

Run: `python -m pytest tests/auth/test_oauth_host.py -v 2>&1 | tail -20`
Expected: `test_oauth_host_rejects_http_override` FAILS (no ValueError raised yet).

- [ ] **Step 2: Add HTTPS enforcement**

In `src/pythinker_code/auth/oauth.py`, replace the existing `_oauth_host()`:

```python
def _oauth_host() -> str:
    host = os.getenv("PYTHINKER_CODE_OAUTH_HOST") or os.getenv("PYTHINKER_OAUTH_HOST")
    if host is not None and not host.startswith("https://"):
        raise ValueError(
            f"PYTHINKER_CODE_OAUTH_HOST must use HTTPS, got: {host!r}"
        )
    return host or DEFAULT_OAUTH_HOST
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/auth/test_oauth_host.py tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/auth/oauth.py tests/auth/test_oauth_host.py
git commit -m "fix(security): enforce HTTPS for PYTHINKER_CODE_OAUTH_HOST override"
```

---

### Task 12: Redact API keys in GET /api/config/toml response (A3)

**Files:**
- Modify: `src/pythinker_code/web/api/config.py:177-184`

The GET endpoint returns the raw config including plaintext API key values. Redact `api_key = "..."` values in the returned content. The PUT endpoint accepts full values (no change there).

- [ ] **Step 1: Write failing test**

In `tests/web/test_config_api_redaction.py` (create):

```python
from pythinker_code.web.api.config import _redact_api_keys


def test_redact_replaces_api_key_value():
    toml = 'api_key = "sk-ant-api-1234567890abcdef"\n'
    result = _redact_api_keys(toml)
    assert "sk-ant-api-1234567890abcdef" not in result
    assert 'api_key = "***"' in result


def test_redact_leaves_other_fields_unchanged():
    toml = 'base_url = "https://api.example.com"\nname = "gpt-4"\n'
    assert _redact_api_keys(toml) == toml


def test_redact_handles_empty_string():
    assert _redact_api_keys("") == ""


def test_redact_handles_no_api_keys():
    toml = '[model]\nname = "claude"\n'
    assert _redact_api_keys(toml) == toml
```

Run: `python -m pytest tests/web/test_config_api_redaction.py -v 2>&1 | tail -20`
Expected: FAIL (`_redact_api_keys` not found).

- [ ] **Step 2: Add helper and update GET handler**

In `src/pythinker_code/web/api/config.py`, add near the top of the file (after existing imports):

```python
import re as _re


def _redact_api_keys(content: str) -> str:
    """Replace api_key = "..." values with *** in TOML/JSON config content."""
    return _re.sub(r'(api_key\s*=\s*)"[^"]*"', r'\1"***"', content)
```

Then update the GET handler to apply redaction:
```python
@router.get("/toml", summary="Get pythinker-code config.toml")
async def get_config_toml(http_request: Request) -> ConfigToml:
    """Get pythinker-code config.toml."""
    _ensure_sensitive_apis_allowed(http_request)
    config_file = get_config_file()
    if not config_file.exists():
        return ConfigToml(content="", path=str(config_file))
    content = _redact_api_keys(config_file.read_text(encoding="utf-8"))
    return ConfigToml(content=content, path=str(config_file))
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/web/test_config_api_redaction.py tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/web/api/config.py tests/web/test_config_api_redaction.py
git commit -m "fix(security): redact api_key values in GET /api/config/toml response"
```

---

### Task 13: Add license field to example pyproject.toml files (D7)

**Files:**
- Modify: `examples/custom-echo-soul/pyproject.toml`
- Modify: `examples/custom-pythinker-soul/pyproject.toml`
- Modify: `examples/custom-tools/pyproject.toml`
- Modify: `examples/feedback-worker/pyproject.toml`
- Modify: `examples/pythinker-cli-stream-json/pyproject.toml`
- Modify: `examples/pythinker-cli-wire-messages/pyproject.toml`
- Modify: `examples/pythinker-psql/pyproject.toml`
- Modify: `examples/sample-plugin/pyproject.toml`

- [ ] **Step 1: Add license to each example**

For each file, add `license = "Apache-2.0"` on the line after `description = "..."` in the `[project]` section.

Run first to see what each file looks like:
```bash
grep -n "description\|license" examples/*/pyproject.toml
```

- [ ] **Step 2: Verify all examples now have license**

Run: `grep -rL "^license" examples/*/pyproject.toml`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add examples/*/pyproject.toml
git commit -m "fix(metadata): add Apache-2.0 license to example package manifests"
```

---

## Summary

| Task | Findings | Risk | New Tests |
|------|----------|------|-----------|
| T1: File permissions | A2, A4 | Low | None |
| T2: get_running_loop | R3 | Low | None |
| T3: Steer queue TOCTOU | R2 | Low | None |
| T4: Code micro-fixes | Q1, Q8, Q12 | Low | None |
| T5: Dependency cleanup | D2, D4 | Low | None |
| T6: BroadcastQueue snapshot | R10 | Low | tests/utils/test_broadcast.py |
| T7: Task reference | Q2 | Low | None |
| T8: Toolset cleanup | R8 | Low | None |
| T9: Exception logging | Q7 | Low | None |
| T10: Jinja2 sandbox | S2, S3 | Medium | tests/core/test_agent_template_sandbox.py |
| T11: OAuth HTTPS | A11 | Low | tests/auth/test_oauth_host.py |
| T12: Config redaction | A3 | Low | tests/web/test_config_api_redaction.py |
| T13: Example licenses | D7 | Low | None |
