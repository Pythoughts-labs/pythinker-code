"""Shared utilities for pythinker dashboard and pythinker web server startup."""

from __future__ import annotations

import importlib
import socket
import sys
import textwrap

from pythinker_code.ui.terminal_capabilities import ascii_glyphs_enabled

# Shared "PYTHINKER" wordmark used by the web and dashboard startup banners.
PYTHINKER_BANNER_ART = [
    "<center>██████╗ ██╗   ██╗████████╗██╗  ██╗██╗███╗   ██╗██╗  ██╗███████╗██████╗ ",
    "<center>██╔══██╗╚██╗ ██╔╝╚══██╔══╝██║  ██║██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗",
    "<center>██████╔╝ ╚████╔╝    ██║   ███████║██║██╔██╗ ██║█████╔╝ █████╗  ██████╔╝",
    "<center>██╔═══╝   ╚██╔╝     ██║   ██╔══██║██║██║╚██╗██║██╔═██╗ ██╔══╝  ██╔══██╗",
    "<center>██║        ██║      ██║   ██║  ██║██║██║ ╚████║██║  ██╗███████╗██║  ██║",
    "<center>╚═╝        ╚═╝      ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝",
]

# Single-cell ASCII stand-ins for every non-ASCII character the banners emit.
# All replacements are 1:1 so box alignment is preserved. Used when the
# terminal can't render Unicode (legacy Windows code pages such as cp1252,
# TERM=dumb, or an explicit PYTHINKER_ASCII_UI/PYTHINKER_TUI_GLYPHS opt-in);
# raw print() of the block art would otherwise garble or raise
# UnicodeEncodeError on those streams.
_BANNER_ASCII_FALLBACKS = str.maketrans(
    {
        "█": "#",
        "╔": " ",
        "╗": " ",
        "╚": " ",
        "╝": " ",
        "║": " ",
        "═": " ",
        "➜": ">",
        "•": "*",
        "⚠": "!",
    }
)


def _print_banner_line(text: str) -> None:
    """Print one banner line, degrading to ASCII if the stream rejects it."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        fallback = text.translate(_BANNER_ASCII_FALLBACKS)
        print(fallback.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def get_address_family(host: str) -> socket.AddressFamily:
    """Return AF_INET6 for IPv6 addresses, AF_INET for IPv4 and hostnames."""
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def format_url(host: str, port: int) -> str:
    """Build ``http://host:port``, bracketing IPv6 literals per RFC 2732."""
    if ":" in host:
        return f"http://[{host}]:{port}"
    return f"http://{host}:{port}"


def is_local_host(host: str) -> bool:
    """Check whether *host* resolves to a loopback address."""
    return host in {"127.0.0.1", "localhost", "::1"}


def find_available_port(host: str, start_port: int, max_attempts: int = 10) -> int:
    """Find an available port starting from *start_port*.

    Raises ``RuntimeError`` if no port is available within the range.
    """
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if start_port < 1 or start_port > 65535:
        raise ValueError("start_port must be between 1 and 65535")

    family = get_address_family(host)
    for offset in range(max_attempts):
        port = start_port + offset
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"Cannot find available port in range {start_port}-{start_port + max_attempts - 1}"
    )


def get_network_addresses() -> list[str]:
    """Get non-loopback IPv4 addresses for this machine."""
    addresses: list[str] = []

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if isinstance(ip, str) and not ip.startswith("127.") and ip not in addresses:
                addresses.append(ip)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith("127.") and ip not in addresses:
            addresses.append(ip)
    except OSError:
        pass

    try:
        netifaces = importlib.import_module("netifaces")
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr_info in addrs[netifaces.AF_INET]:
                    addr = addr_info.get("addr")
                    if addr and not addr.startswith("127.") and addr not in addresses:
                        addresses.append(addr)
    except (ImportError, Exception):
        pass

    return addresses


def missing_ui_page(asset_path: str, build_command: str) -> str:
    """HTML served on ``/`` when the bundled frontend assets are absent.

    Packaged builds that skipped the frontend build would otherwise answer
    ``/`` with a bare 404, which reads like a routing bug instead of a
    packaging one.
    """
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Pythinker UI unavailable</title>
  </head>
  <body style="font-family: system-ui, sans-serif; max-width: 40rem;
               margin: 4rem auto; line-height: 1.5;">
    <h1>UI assets are missing</h1>
    <p>This Pythinker build was packaged without its frontend bundle
    (<code>{asset_path}</code> was not found).</p>
    <p>If you installed a packaged build (Windows installer, winget, scoop,
    .deb/.rpm), update to the latest release or report this as a packaging
    bug. When running from source, build the frontend first:</p>
    <pre><code>{build_command}</code></pre>
    <p>The REST API is unaffected and remains available under <code>/api</code>.</p>
  </body>
</html>
"""


def print_banner(lines: list[str]) -> None:
    """Print a boxed banner with tag conventions (<center>, <nowrap>, <hr>)."""
    if ascii_glyphs_enabled():
        lines = [line.translate(_BANNER_ASCII_FALLBACKS) for line in lines]

    processed: list[str] = []
    for line in lines:
        if line == "<hr>":
            processed.append(line)
        elif not line:
            processed.append("")
        elif line.startswith("<center>") or line.startswith("<nowrap>"):
            processed.append(line)
        else:
            processed.extend(textwrap.wrap(line, width=78))

    def strip_tags(s: str) -> str:
        return s.removeprefix("<center>").removeprefix("<nowrap>")

    content_lines = [strip_tags(line) for line in processed if line != "<hr>"]
    # The leading 60 lives inside the list: `max(60, *[])` is a TypeError when
    # every line is an <hr>.
    width = max([60, *(len(line) for line in content_lines)])
    top = "+" + "=" * (width + 2) + "+"

    _print_banner_line(top)
    for line in processed:
        if line == "<hr>":
            _print_banner_line("|" + "-" * (width + 2) + "|")
        elif line.startswith("<center>"):
            content = line.removeprefix("<center>")
            _print_banner_line(f"| {content.center(width)} |")
        elif line.startswith("<nowrap>"):
            content = line.removeprefix("<nowrap>")
            _print_banner_line(f"| {content.ljust(width)} |")
        else:
            _print_banner_line(f"| {line.ljust(width)} |")
    _print_banner_line(top)
