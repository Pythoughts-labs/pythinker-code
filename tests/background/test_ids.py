from __future__ import annotations

import re

import pytest

from pythinker_code.background.ids import generate_task_id
from pythinker_code.background.store import _VALID_TASK_ID

_AGENT_CODENAME_ID = re.compile(r"^agent-[a-z]+-[a-z]+(-\d+)?$")
_BASH_RANDOM_ID = re.compile(r"^bash-[0-9a-z]{8}$")


class TestTaskIdValidation:
    def test_generated_ids_pass_store_validation(self):
        """Ensure ids.py and store.py stay in sync."""
        for kind in ("bash", "agent"):
            task_id = generate_task_id(kind)
            assert _VALID_TASK_ID.match(task_id), f"{task_id!r} should pass validation"

    def test_agent_ids_are_codenames(self):
        """Agent task ids carry a human-distinguishable codename, not an opaque
        random suffix — they are the visible instance handle in TaskOutput
        headers, the task list, and notifications."""
        task_id = generate_task_id("agent")
        assert _AGENT_CODENAME_ID.match(task_id), task_id
        assert len(task_id) <= 25  # _VALID_TASK_ID length bound

    def test_bash_ids_keep_random_suffix(self):
        assert _BASH_RANDOM_ID.match(generate_task_id("bash"))

    def test_used_ids_are_never_reissued(self):
        """The store keys tasks by id, so a mint must avoid every existing id."""
        used: set[str] = set()
        for _ in range(40):
            task_id = generate_task_id("agent", used=used)
            assert task_id not in used
            assert _VALID_TASK_ID.match(task_id), task_id
            used.add(task_id)
        bash_id = generate_task_id("bash", used=used)
        assert bash_id not in used

    @pytest.mark.parametrize(
        "task_id",
        [
            "b1234567",
            "a1234567",
            "bmissing01",
        ],
    )
    def test_old_format_ids_still_accepted(self, task_id):
        assert _VALID_TASK_ID.match(task_id), f"old format {task_id!r} should still be valid"

    @pytest.mark.parametrize(
        "task_id",
        [
            "",
            "x",
            "-bash",
            "BASH-123",
            "bash_123",
            "../escape",
            "a" * 26,
        ],
    )
    def test_invalid_ids_rejected(self, task_id):
        assert not _VALID_TASK_ID.match(task_id), f"{task_id!r} should be rejected"
