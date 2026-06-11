"""Session cost + cumulative token totals surface in StatusSnapshot."""

import pythinker_code.soul.pythinkersoul as _soul_mod

from pythinker_code.soul import StatusSnapshot


def test_status_snapshot_new_fields_default():
    snap = StatusSnapshot(context_usage=0.0)
    assert snap.session_cost_usd == 0.0
    assert snap.total_input_tokens == 0
    assert snap.total_output_tokens == 0


def test_estimate_cost_usd_wired_into_pythinkersoul():
    """Lightweight wiring check: estimate_cost_usd must be imported in the soul module."""
    assert hasattr(_soul_mod, "estimate_cost_usd"), (
        "estimate_cost_usd was not imported into pythinkersoul; cost accumulation is broken"
    )
