"""Distinctive instance codenames for launched subagents.

Parallel children launched with generic names (typically the model echoes the
subagent type, yielding rows like ``code-reviewer:code-reviewer``) are
indistinguishable in the TUI tree, task list, and notifications. A codename
gives each instance a stable, human-friendly identity (``amber-falcon``)
while the subagent type stays visible in its own column/field. Background
agent task ids reuse the same generator (``agent-tidal-wren``) so the id —
the visible handle in TaskOutput headers and notifications — is
distinguishable too.
"""

from __future__ import annotations

import secrets
from collections.abc import Collection

_ADJECTIVES = (
    "amber",
    "brisk",
    "cobalt",
    "crimson",
    "dapper",
    "ember",
    "frosty",
    "gilded",
    "hazel",
    "indigo",
    "jade",
    "keen",
    "lunar",
    "mellow",
    "nimble",
    "opal",
    "plucky",
    "quartz",
    "rustic",
    "sable",
    "tidal",
    "umber",
    "velvet",
    "zesty",
)

_NOUNS = (
    "badger",
    "comet",
    "falcon",
    "gecko",
    "heron",
    "ibis",
    "jackal",
    "kestrel",
    "lemur",
    "lynx",
    "marmot",
    "narwhal",
    "ocelot",
    "otter",
    "panther",
    "quokka",
    "raven",
    "sparrow",
    "tapir",
    "urchin",
    "vole",
    "walrus",
    "wren",
    "zephyr",
)

# Names that carry no identity: empty, role fillers, or the agent type itself
# (checked separately, since the type varies per child).
_GENERIC_NAMES = {"", "agent", "subagent", "child", "worker", "task"}


def generate_codename(used: Collection[str] = ()) -> str:
    """Return an ``adjective-noun`` codename not present in *used*.

    With 24x24 combinations collisions are rare; after a bounded number of
    draws a numeric suffix guarantees termination and uniqueness.
    """
    taken = {name.lower() for name in used}
    codename = f"{secrets.choice(_ADJECTIVES)}-{secrets.choice(_NOUNS)}"
    for _ in range(64):
        if codename not in taken:
            return codename
        codename = f"{secrets.choice(_ADJECTIVES)}-{secrets.choice(_NOUNS)}"
    suffix = 2
    while f"{codename}-{suffix}" in taken:
        suffix += 1
    return f"{codename}-{suffix}"


def is_generic_agent_name(name: str, subagent_type: str) -> bool:
    """Whether *name* carries no instance identity (so a codename should replace it)."""
    normalized = name.strip().lower().replace("_", "-").replace(" ", "-")
    return normalized in _GENERIC_NAMES or normalized == subagent_type.strip().lower()
