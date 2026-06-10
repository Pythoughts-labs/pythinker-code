"""Tests for pythinker_code.utils.server shared utilities."""

from __future__ import annotations

import pytest

from pythinker_code.utils.server import (
    PYTHINKER_BANNER_ART,
    find_available_port,
    format_url,
    get_address_family,
    get_network_addresses,
    is_local_host,
    print_banner,
)

# ---------------------------------------------------------------------------
# format_url — IPv4 / IPv6 / hostname
# ---------------------------------------------------------------------------


class TestFormatUrl:
    def test_ipv4(self) -> None:
        assert format_url("127.0.0.1", 5495) == "http://127.0.0.1:5495"

    def test_hostname(self) -> None:
        assert format_url("localhost", 8080) == "http://localhost:8080"

    def test_ipv6_loopback(self) -> None:
        assert format_url("::1", 5495) == "http://[::1]:5495"

    def test_ipv6_all_interfaces(self) -> None:
        assert format_url("::", 3000) == "http://[::]:3000"

    def test_ipv6_full(self) -> None:
        assert format_url("fe80::1", 443) == "http://[fe80::1]:443"

    def test_zero_zero_zero_zero(self) -> None:
        """0.0.0.0 is IPv4 — no brackets."""
        assert format_url("0.0.0.0", 5495) == "http://0.0.0.0:5495"


# ---------------------------------------------------------------------------
# is_local_host
# ---------------------------------------------------------------------------


class TestIsLocalHost:
    def test_localhost(self) -> None:
        assert is_local_host("localhost") is True

    def test_ipv4_loopback(self) -> None:
        assert is_local_host("127.0.0.1") is True

    def test_ipv6_loopback(self) -> None:
        assert is_local_host("::1") is True

    def test_all_interfaces(self) -> None:
        assert is_local_host("0.0.0.0") is False

    def test_private_ip(self) -> None:
        assert is_local_host("192.168.1.1") is False


# ---------------------------------------------------------------------------
# get_address_family
# ---------------------------------------------------------------------------


class TestGetAddressFamily:
    def test_ipv4(self) -> None:
        import socket

        assert get_address_family("127.0.0.1") == socket.AF_INET

    def test_hostname(self) -> None:
        import socket

        assert get_address_family("localhost") == socket.AF_INET

    def test_ipv6(self) -> None:
        import socket

        assert get_address_family("::1") == socket.AF_INET6

    def test_zero_zero(self) -> None:
        import socket

        assert get_address_family("0.0.0.0") == socket.AF_INET


# ---------------------------------------------------------------------------
# find_available_port
# ---------------------------------------------------------------------------


class TestFindAvailablePort:
    def test_finds_port(self) -> None:
        port = find_available_port("127.0.0.1", 19876, max_attempts=5)
        assert 19876 <= port <= 19880

    def test_invalid_max_attempts(self) -> None:
        with pytest.raises(ValueError, match="max_attempts"):
            find_available_port("127.0.0.1", 5000, max_attempts=0)

    def test_invalid_port(self) -> None:
        with pytest.raises(ValueError, match="start_port"):
            find_available_port("127.0.0.1", 0)


# ---------------------------------------------------------------------------
# get_network_addresses
# ---------------------------------------------------------------------------


class TestGetNetworkAddresses:
    def test_returns_list(self) -> None:
        result = get_network_addresses()
        assert isinstance(result, list)

    def test_no_loopback(self) -> None:
        for addr in get_network_addresses():
            assert not addr.startswith("127.")


# ---------------------------------------------------------------------------
# print_banner — Unicode wordmark with ASCII fallbacks for legacy terminals
# ---------------------------------------------------------------------------


_GLYPH_ENV_VARS = ("PYTHINKER_TUI_GLYPHS", "PYTHINKER_ASCII_UI", "PYTHINKER_SAFE_GLYPHS")


def _sample_banner_lines() -> list[str]:
    return [
        *PYTHINKER_BANNER_ART,
        "",
        "<center>WEB UI (Technical Preview)",
        "<hr>",
        "<nowrap>  ➜  Local    http://localhost:5494/?token=abc123",
        "<nowrap>    • Use -n / --network to share on LAN",
        "<nowrap>  ⚠ Sensitive APIs are restricted",
    ]


class TestPrintBanner:
    def test_all_lines_share_one_width(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in _GLYPH_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        print_banner(_sample_banner_lines())
        widths = {len(line) for line in capsys.readouterr().out.splitlines()}
        assert len(widths) == 1

    def test_ascii_opt_in_strips_unicode_and_keeps_alignment(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PYTHINKER_ASCII_UI", "1")
        print_banner(_sample_banner_lines())
        out = capsys.readouterr().out
        assert out.isascii()
        assert "#" in out  # wordmark survives as its block silhouette
        assert len({len(line) for line in out.splitlines()}) == 1

    def test_legacy_windows_codepage_stdout_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PowerShell with redirected output encodes stdout as cp1252.

        The block/box wordmark is not representable there; the banner must
        degrade to ASCII instead of raising UnicodeEncodeError at startup.
        """
        import io
        import sys

        for var in _GLYPH_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="cp1252", newline="")
        monkeypatch.setattr(sys, "stdout", stream)
        print_banner(_sample_banner_lines())
        stream.flush()
        out = buffer.getvalue().decode("cp1252")
        assert "#" in out
        assert "+" in out  # box border intact

    def test_stream_rejecting_unicode_falls_back_per_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even when encoding detection can't see the limitation, a stream
        that raises UnicodeEncodeError gets the ASCII rendition, not a crash."""
        import io
        import sys

        for var in _GLYPH_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

        class _StrictAsciiStdout(io.TextIOBase):
            def __init__(self) -> None:
                self.chunks: list[str] = []

            def write(self, s: str) -> int:
                s.encode("ascii")
                self.chunks.append(s)
                return len(s)

        stream = _StrictAsciiStdout()
        monkeypatch.setattr(sys, "stdout", stream)
        print_banner(_sample_banner_lines())
        out = "".join(stream.chunks)
        assert "#" in out
        assert "share on LAN" in out

    def test_hr_only_banner_does_not_crash(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`max(60, *[])` is a TypeError; the minimum width must apply."""
        print_banner(["<hr>"])
        out = capsys.readouterr().out.splitlines()
        assert len({len(line) for line in out}) == 1
