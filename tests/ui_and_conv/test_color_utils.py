"""Tests for the color-math helpers in ``pythinker_code.ui.color_utils``."""

from __future__ import annotations

import pytest

from pythinker_code.ui.color_utils import blend, is_light, luma, parse_hex_color, to_hex_color


def test_parse_hex_color_accepts_six_digit_forms() -> None:
    assert parse_hex_color("#ffffff") == (255, 255, 255)
    assert parse_hex_color("000000") == (0, 0, 0)
    assert parse_hex_color("#AbCdEf") == (171, 205, 239)
    assert parse_hex_color(" #112233 ") == (17, 34, 51)


def test_parse_hex_color_rejects_invalid_input() -> None:
    assert parse_hex_color("") is None
    assert parse_hex_color("#fff") is None
    assert parse_hex_color("nope") is None
    assert parse_hex_color("#11223344") is None


def test_to_hex_color_round_trips_and_clamps() -> None:
    assert to_hex_color((255, 255, 255)) == "#ffffff"
    assert to_hex_color((300, -5, 16)) == "#ff0010"
    assert parse_hex_color(to_hex_color((18, 52, 86))) == (18, 52, 86)


def test_blend_endpoints_midpoint_and_clamping() -> None:
    assert blend((255, 0, 0), (0, 0, 255), 1.0) == (255, 0, 0)
    assert blend((255, 0, 0), (0, 0, 255), 0.0) == (0, 0, 255)
    assert blend((255, 0, 0), (0, 0, 255), 0.5) == (128, 0, 128)
    assert blend((255, 0, 0), (0, 0, 255), 2.0) == (255, 0, 0)
    assert blend((255, 0, 0), (0, 0, 255), -1.0) == (0, 0, 255)


def test_luma_is_bt601_weighted() -> None:
    assert luma((255, 255, 255)) == pytest.approx(255.0)
    assert luma((0, 0, 0)) == 0.0
    # Green dominates perceived brightness.
    assert luma((0, 255, 0)) > luma((255, 0, 0)) > luma((0, 0, 255))


def test_is_light_classifies_real_terminal_backgrounds() -> None:
    assert is_light((255, 255, 255))
    assert not is_light((0, 0, 0))
    assert not is_light((30, 30, 46))  # Catppuccin Mocha base
    assert is_light((239, 241, 245))  # Catppuccin Latte base
