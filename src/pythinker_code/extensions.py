"""In-process extension API.

This module exposes Pythinker's extension hooks for the registries that
already exist in the codebase:

* tool renderers           — :func:`register_tool_renderer`
* keybindings              — :func:`register_keybinding`
* footer status badges     — :func:`register_footer_status`
* event handlers           — :func:`register_event_handler`
* lifecycle hooks          — :func:`register_extension`

The footer status registry is a thin placeholder for the day the card-style
:class:`FooterState` is wired into the live prompt; until then it just
stores entries that callers can read out.

the ``register_command`` overlaps with Pythinker's existing
``SlashCommandRegistry`` — extensions should use that registry directly.

Extensions are registered with::

    from pythinker_code.extensions import register_extension

    def setup(ctx):
        ctx.register_tool_renderer(my_renderer)
        ctx.register_keybinding("app.tools.expand", "alt+e")
        ctx.bus.on("assistant.message", on_assistant_message)

    register_extension(name="my-ext", setup=setup)

The host calls :func:`run_pending_extensions` once at startup; setup
errors are logged but do not crash the host.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pythinker_code.events import EventBus, EventHandler, create_event_bus
from pythinker_code.ui.shell.keymap import register_keybinding as _register_keybinding
from pythinker_code.ui.shell.tool_renderers import (
    ToolRenderDefinition,
)
from pythinker_code.ui.shell.tool_renderers import (
    register_tool_renderer as _register_tool_renderer,
)
from pythinker_code.utils.logging import logger

__all__ = [
    "ExtensionContext",
    "ExtensionSetup",
    "footer_statuses",
    "register_extension",
    "registered_extensions",
    "run_pending_extensions",
    "shared_event_bus",
]


_GLOBAL_BUS: EventBus = create_event_bus()
"""Process-wide bus extensions write to. Independent from any per-session
event streams to keep the surface stable."""

_FOOTER_STATUSES: dict[str, str] = {}
"""Read-only-from-outside map of extension id → status text."""


def shared_event_bus() -> EventBus:
    """Return the global :class:`EventBus` extensions subscribe to."""
    return _GLOBAL_BUS


def footer_statuses() -> dict[str, str]:
    """Return a copy of the current extension footer-status map."""
    return dict(_FOOTER_STATUSES)


@dataclass(slots=True)
class ExtensionContext:
    """Handle passed into an extension's setup function.

    Each method delegates to the appropriate global registry. Method names
    mirror the ``register*`` API surface so porting an extension between
    runtimes is mostly mechanical.
    """

    name: str
    bus: EventBus = field(default_factory=lambda: _GLOBAL_BUS)

    def register_tool_renderer(self, definition: ToolRenderDefinition) -> None:
        _register_tool_renderer(definition)

    def register_keybinding(self, semantic_id: str, *keys: str) -> None:
        _register_keybinding(semantic_id, *keys)

    def register_footer_status(self, key: str, text: str) -> None:
        """Add or replace an extension's footer status badge.

        ``key`` is normally the extension name. Pass an empty *text* to
        clear it. The footer reads :func:`footer_statuses` when rendering.
        """
        if not text:
            _FOOTER_STATUSES.pop(key, None)
            return
        _FOOTER_STATUSES[key] = text

    def register_event_handler(self, channel: str, handler: EventHandler) -> Callable[[], None]:
        return self.bus.on(channel, handler)


ExtensionSetup = Callable[[ExtensionContext], None]


@dataclass(frozen=True, slots=True)
class _Extension:
    name: str
    setup: ExtensionSetup
    started: bool = False


_PENDING: list[_Extension] = []
_LOADED: list[str] = []


def register_extension(*, name: str, setup: ExtensionSetup) -> None:
    """Queue *setup* to run when :func:`run_pending_extensions` is next called."""
    _PENDING.append(_Extension(name=name, setup=setup))


def run_pending_extensions() -> list[str]:
    """Execute every pending extension's setup. Returns the names that ran.

    Errors are logged and the rest of the queue continues — the same behavior.
    """
    started: list[str] = []
    while _PENDING:
        ext = _PENDING.pop(0)
        ctx = ExtensionContext(name=ext.name)
        try:
            ext.setup(ctx)
        except Exception:  # noqa: BLE001 — extension error must not crash host
            logger.exception("Extension '{name}' setup failed", name=ext.name)
            continue
        _LOADED.append(ext.name)
        started.append(ext.name)
    return started


def registered_extensions() -> list[str]:
    """Snapshot of extension names that have been successfully started."""
    return list(_LOADED)
