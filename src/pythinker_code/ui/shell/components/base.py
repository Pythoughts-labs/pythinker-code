"""Component protocol shared by Pythinker TUI components."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rich.console import RenderableType


@runtime_checkable
class TuiComponent(Protocol):
    """Renders to one or more Rich renderables, sized to a target cell width.

    Implementations should be pure: identical inputs produce identical output.
    State changes are signalled via :meth:`invalidate` so a host renderer can
    drop any cached output.
    """

    def render(self, width: int) -> RenderableType | list[RenderableType]:
        """Return Rich renderable(s) sized to *width* terminal cells."""
        ...

    def invalidate(self) -> None:
        """Drop cached render output. Called when component state changes."""
        ...
