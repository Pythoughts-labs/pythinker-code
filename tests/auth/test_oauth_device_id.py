"""Tests for get_device_id atomic creation, private permissions, and first_launch telemetry."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import patch

from pythinker_code.auth.oauth import get_device_id


def test_get_device_id_stable_private_and_fires_first_launch_once(tmp_path, monkeypatch):
    """
    Verify:
    1. First call returns a 32-hex id, the file is mode 0o600, first_launch fires once.
    2. Second call returns the same id and does NOT fire first_launch again.
    3. Race (loser) path: if the file already exists at the point of creation
       (simulating two processes passing the path.exists() fast-path simultaneously),
       get_device_id returns the pre-existing sentinel id and track is NOT called.
       This is the primary regression guard for the O_EXCL TOCTOU fix.
    """
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))

    # --- Part A: fresh creation path ---
    call_count: list[int] = [0]

    def fake_track(event: str, **_kwargs: object) -> None:
        if event == "first_launch":
            call_count[0] += 1

    with patch("pythinker_code.telemetry.track", side_effect=fake_track):
        first_id = get_device_id()

    assert re.fullmatch(r"[0-9a-f]{32}", first_id), f"Expected 32-hex device id, got {first_id!r}"

    device_id_file = tmp_path / "device_id"
    assert device_id_file.exists(), "device_id file must be created"
    assert (device_id_file.stat().st_mode & 0o777) == 0o600, (
        "device_id file must be 0o600 (owner-read/write only)"
    )
    assert call_count[0] == 1, "first_launch must fire exactly once on creation"

    # --- Part B: stable re-read, no duplicate telemetry ---
    with patch("pythinker_code.telemetry.track", side_effect=fake_track):
        second_id = get_device_id()

    assert second_id == first_id, "Repeated call must return the same id"
    assert call_count[0] == 1, "first_launch must NOT fire on a repeated read"

    # --- Part C: race / loser path ---
    # Simulate two processes simultaneously passing path.exists() == False:
    # pre-create the file with a sentinel id, then force get_device_id() to
    # skip the fast-path (by patching Path.exists to return False for the
    # device_id file), so execution proceeds to the creation branch.
    # With os.open(O_CREAT|O_EXCL), that branch gets FileExistsError → reads
    # the sentinel without firing track.  With write_text it overwrites the
    # sentinel and fires track (bug).
    sentinel_id = "aabbccddeeff00112233445566778899"
    device_id_file.write_text(sentinel_id, encoding="utf-8")
    os.chmod(device_id_file, 0o600)

    race_call_count: list[int] = [0]

    def fake_track_race(event: str, **_kwargs: object) -> None:
        if event == "first_launch":
            race_call_count[0] += 1

    # Patch Path.exists to return False specifically for our device_id file,
    # so the fast-path is bypassed and execution reaches the write/create branch.
    real_exists = Path.exists

    def patched_exists(self: Path) -> bool:
        if self == device_id_file:
            return False
        return real_exists(self)

    with (
        patch("pythinker_code.telemetry.track", side_effect=fake_track_race),
        patch.object(Path, "exists", patched_exists),
    ):
        loser_id = get_device_id()

    assert loser_id == sentinel_id, f"Loser path must return the sentinel id, got {loser_id!r}"
    assert race_call_count[0] == 0, (
        "first_launch must NOT fire on the loser/EEXIST path (double-mint guard)"
    )
