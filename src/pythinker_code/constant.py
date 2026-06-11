from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

NAME = "Pythinker CLI"
ORGANIZATION = "Pythoughts-labs"
CONTACT = "hello@pythoughts.com"

if TYPE_CHECKING:
    VERSION: str
    USER_AGENT: str


def source_checkout_version() -> str | None:
    """Version from the live ``pyproject.toml`` when running from a source tree.

    Editable installs keep a dist-info snapshot from the last ``uv sync``, so
    ``importlib.metadata`` reports a stale version between syncs — which then
    mis-attributes telemetry to old releases. Wheel and PyInstaller layouts have
    no adjacent ``pyproject.toml`` and fall through to metadata.
    """
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject.open("rb") as f:
            project = tomllib.load(f).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if project.get("name") != "pythinker-code":
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


@cache
def get_version() -> str:
    source_version = source_checkout_version()
    if source_version:
        return source_version
    from importlib import metadata

    return metadata.version("pythinker-code")


@cache
def get_user_agent() -> str:
    return f"PythinkerCLI/{get_version()}"


def __getattr__(name: str) -> str:
    if name == "VERSION":
        return get_version()
    if name == "USER_AGENT":
        return get_user_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "NAME",
    "ORGANIZATION",
    "CONTACT",
    "VERSION",
    "USER_AGENT",
    "get_version",
    "source_checkout_version",
    "get_user_agent",
]
