"""memory-2: opt-in "durable memory" profile.

The harvest -> scratch -> journal -> recall pipeline ships inert (all three durable
flags default off). Rather than flip the privacy-affecting defaults, ``durable_memory``
is a single opt-in profile that turns on harvest + journal via effective-value
properties, leaving the stored individual flags (and consolidation) untouched.
"""

from __future__ import annotations

from pythinker_code.config import MemoryConfig


def test_durable_memory_defaults_off() -> None:
    m = MemoryConfig()
    assert m.durable_memory is False
    assert m.harvest_enabled is False
    assert m.journal_enabled is False


def test_durable_memory_profile_enables_harvest_and_journal() -> None:
    m = MemoryConfig(durable_memory=True)
    # The profile is sugar: it does NOT rewrite the stored individual flags...
    assert m.harvest_on_compaction is False
    assert m.journal_recaps is False
    # ...but the effective gates honor it.
    assert m.harvest_enabled is True
    assert m.journal_enabled is True
    # consolidation writes durable MEMORY.md and stays separately opt-in.
    assert m.consolidation is False


def test_individual_harvest_flag_still_works_without_profile() -> None:
    m = MemoryConfig(harvest_on_compaction=True)
    assert m.harvest_enabled is True
    assert m.journal_enabled is False


def test_individual_journal_flag_still_works_without_profile() -> None:
    m = MemoryConfig(journal_recaps=True)
    assert m.journal_enabled is True
    assert m.harvest_enabled is False
