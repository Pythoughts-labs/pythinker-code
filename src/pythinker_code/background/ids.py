from __future__ import annotations

import secrets
from collections.abc import Collection

from pythinker_code.subagents.codenames import generate_codename

from .models import TaskKind

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

# Total-length bound enforced by _VALID_TASK_ID in store.py.
_MAX_TASK_ID_LEN = 25


_TASK_ID_PREFIXES: dict[TaskKind, str] = {
    "bash": "bash",
    "agent": "agent",
}


def generate_task_id(kind: TaskKind, used: Collection[str] = ()) -> str:
    """Return a task id of the form ``<prefix>-<suffix>`` not present in *used*.

    Agent tasks get a human-distinguishable codename suffix (``agent-tidal-wren``)
    because the id is the visible instance handle in TaskOutput headers, the task
    list, and notifications. Bash tasks keep the opaque random suffix.
    """
    prefix = _TASK_ID_PREFIXES[kind]
    taken = {task_id.lower() for task_id in used}
    if kind == "agent":
        codename = generate_codename({task_id.removeprefix(f"{prefix}-") for task_id in taken})
        task_id = f"{prefix}-{codename}"
        if len(task_id) <= _MAX_TASK_ID_LEN:
            return task_id
        # A suffix-overflowed codename (theoretical) falls back to the random form.
    while True:
        task_id = f"{prefix}-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if task_id not in taken:
            return task_id
