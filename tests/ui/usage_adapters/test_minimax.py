from __future__ import annotations

from pythinker_code.ui.shell.usage_adapters.minimax import (
    MINIMAX_TOKEN_PLAN_URL,
    MiniMaxAdapter,
    parse_minimax_payload,
)


def test_minimax_metadata() -> None:
    assert MiniMaxAdapter.platform_id == "minimax"
    assert MiniMaxAdapter.requires_admin_key is False


def test_minimax_uses_documented_api_endpoint() -> None:
    # Per https://platform.minimax.io/docs/token-plan/faq (verified
    # 2026-05-06), the API-key-authenticated endpoint lives at minimax.io,
    # NOT the cookie-only portal at
    # minimaxi.com/v1/api/openplatform/coding_plan/remains.
    assert MINIMAX_TOKEN_PLAN_URL == "https://www.minimax.io/v1/token_plan/remains"


def test_parse_minimax_payload_real_shape() -> None:
    """Live response shape sourced from `slkiser/opencode-quota`'s
    minimax-coding-plan provider, which has exercised this endpoint
    against real Token-Plan accounts.

    The `*_usage_count` field names are misleading — MiniMax actually
    returns *remaining* counts there, not used. We compute
    used = min(total, max(0, total - remaining)) so the renderer's
    progress bar shows actual consumption, not the leftover quota."""
    payload = {
        "base_resp": {"status_code": 0, "status_msg": ""},
        "model_remains": [
            {
                "model_name": "MiniMax-M2.7",
                "current_interval_total_count": 1500,
                "current_interval_usage_count": 1473,  # REMAINING, not used
                "remains_time": 12345,
                "current_weekly_total_count": 15000,
                "current_weekly_usage_count": 14500,  # REMAINING, not used
                "weekly_remains_time": 432000,
            },
        ],
    }
    report = parse_minimax_payload(payload)
    assert report.summary is not None
    assert report.summary.label == "MiniMax-M2.7 5h"
    assert report.summary.unit == "requests"
    assert report.summary.used == 27  # 1500 - 1473 = consumed
    assert report.summary.limit == 1500
    assert "resets in" in (report.summary.reset_hint or "")

    assert len(report.limits) == 1
    weekly = report.limits[0]
    assert weekly.label == "MiniMax-M2.7 weekly"
    assert weekly.used == 500  # 15000 - 14500 = consumed
    assert weekly.limit == 15000


def test_parse_minimax_payload_percent_metered_real_shape() -> None:
    """Verified 2026-06-15 against a live sk-cp-* key. The plan meters by
    percentage (count fields are 0) and reports reset times in milliseconds, with
    `model_name` as a resource category. The old parser showed "0 requests used"
    and absurd ("171d") resets; this asserts the corrected percent + ms handling."""
    payload = {
        "model_remains": [
            {
                "start_time": 1781449200000,
                "end_time": 1781467200000,
                "remains_time": 13224928,  # ms -> ~3h40m, NOT 153 days
                "current_interval_total_count": 0,
                "current_interval_usage_count": 0,
                "model_name": "general",
                "current_weekly_total_count": 0,
                "current_weekly_usage_count": 0,
                "weekly_remains_time": 27624928,
                "current_interval_remaining_percent": 100,
                "current_weekly_remaining_percent": 82,
            },
            {
                "model_name": "video",
                "remains_time": 27624928,
                "current_interval_total_count": 0,
                "current_weekly_total_count": 0,
                "weekly_remains_time": 27624928,
                "current_interval_remaining_percent": 100,
                "current_weekly_remaining_percent": 100,
            },
        ],
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }
    report = parse_minimax_payload(payload)
    rows = [report.summary, *report.limits]
    by_label = {r.label: r for r in rows if r is not None}

    # Percent-metered: 82% remaining -> 18% used, on a 0..100 scale.
    weekly = by_label["general weekly"]
    assert weekly.unit == "%"
    assert weekly.used == 18
    assert weekly.limit == 100

    interval = by_label["general 5h"]
    assert interval.unit == "%"
    assert interval.used == 0

    # Reset times are milliseconds: ~3h40m, never days.
    assert interval.reset_hint is not None
    assert "resets in" in interval.reset_hint
    assert "d" not in interval.reset_hint  # not "171d"

    assert "video 5h" in by_label and "video weekly" in by_label


def test_parse_minimax_payload_multiple_models() -> None:
    payload = {
        "base_resp": {"status_code": 0},
        "model_remains": [
            {
                "model_name": "MiniMax-M2.7",
                "current_interval_total_count": 1500,
                "current_interval_usage_count": 100,
                "remains_time": 1,
                "current_weekly_total_count": 15000,
                "current_weekly_usage_count": 1000,
                "weekly_remains_time": 1,
            },
            {
                "model_name": "MiniMax-M2.7-highspeed",
                "current_interval_total_count": 4500,
                "current_interval_usage_count": 4000,
                "remains_time": 1,
                "current_weekly_total_count": 45000,
                "current_weekly_usage_count": 40000,
                "weekly_remains_time": 1,
            },
        ],
    }
    report = parse_minimax_payload(payload)
    # Summary = first model's 5h row; remaining 3 rows go in limits.
    assert report.summary is not None
    assert report.summary.label == "MiniMax-M2.7 5h"
    labels = [r.label for r in report.limits]
    assert "MiniMax-M2.7 weekly" in labels
    assert "MiniMax-M2.7-highspeed 5h" in labels
    assert "MiniMax-M2.7-highspeed weekly" in labels


def test_parse_minimax_payload_clamps_remaining_above_total() -> None:
    payload = {
        "model_remains": [
            {
                "model_name": "MiniMax-M2.7",
                "current_interval_total_count": 100,
                # Bogus value — MiniMax sometimes returns remaining > total
                # during edge cases. used = max(0, total - remaining) clamps
                # the floor to 0 (can't have negative consumption).
                "current_interval_usage_count": 99999,
                "remains_time": 0,
                "current_weekly_total_count": 1000,
                "current_weekly_usage_count": 1000,
                "weekly_remains_time": 0,
            }
        ]
    }
    report = parse_minimax_payload(payload)
    assert report.summary is not None
    assert report.summary.used == 0  # max(0, 100 - 99999) = 0


def test_parse_minimax_payload_error_status_surfaces_message() -> None:
    payload = {"base_resp": {"status_code": 1004, "status_msg": "auth failed"}}
    report = parse_minimax_payload(payload)
    assert report.summary is None
    assert any("1004" in n and "auth failed" in n for n in report.notes)


def test_parse_minimax_payload_unknown_shape_surfaces_keys() -> None:
    payload = {"foo": 1, "bar": 2}
    report = parse_minimax_payload(payload)
    assert report.summary is None
    assert any("foo" in n and "bar" in n for n in report.notes)
