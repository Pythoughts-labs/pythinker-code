"""Generate the Homebrew Formula for pythinker-code from the just-published
PyPI release.

Runs in the homebrew-tap.yml workflow after PyPI has the new version.
Expects ``pythinker-code==<VERSION>`` to already be installed into the
current Python environment so ``homebrew-pypi-poet`` can introspect its
dependency tree.

Usage:
    python generate-formula.py \\
        --version 0.13.0 \\
        --template packages/homebrew-tap/pythinker-code.rb.tmpl \\
        --output Formula/pythinker-code.rb

The generated formula uses ``virtualenv_install_with_resources`` and lists
every transitive dependency as a ``resource`` block with its PyPI URL +
SHA-256, which is the standard Homebrew pattern for Python CLIs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PYPI_JSON = "https://pypi.org/pypi/pythinker-code/{version}/json"


def fetch_sdist_metadata(version: str) -> tuple[str, str]:
    """Return (sdist_url, sdist_sha256) for the given pythinker-code version."""
    with urllib.request.urlopen(PYPI_JSON.format(version=version), timeout=30) as resp:
        data = json.load(resp)
    for f in data.get("urls", []):
        if f.get("packagetype") == "sdist":
            return f["url"], f["digests"]["sha256"]
    raise RuntimeError(f"no sdist found on PyPI for pythinker-code=={version}")


def run_poet(package: str) -> str:
    """Run homebrew-pypi-poet against an installed package.

    homebrew-pypi-poet only ships a ``poet`` console script (no runnable
    ``poet`` module), so ``python -m poet`` raises. Resolve the script that
    sits next to the running interpreter — that's the venv we just
    installed ``homebrew-pypi-poet`` into in the workflow.
    """
    poet = Path(sys.executable).parent / "poet"
    res = subprocess.run(
        [str(poet), package],
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout


def indent_resources(block: str, spaces: int = 2) -> str:
    """Indent every line so the resource blocks sit inside the class body."""
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in block.splitlines())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    sdist_url, sdist_sha = fetch_sdist_metadata(args.version)
    resources = indent_resources(run_poet("pythinker-code"))
    tmpl = args.template.read_text(encoding="utf-8")
    formula = (
        tmpl.replace("__SDIST_URL__", sdist_url)
        .replace("__SDIST_SHA256__", sdist_sha)
        .replace("__RESOURCES__", resources)
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(formula, encoding="utf-8")

    # Print a short summary for the workflow log.
    digest = hashlib.sha256(formula.encode("utf-8")).hexdigest()
    print(f"formula written to {args.output}")
    print(f"sdist URL    : {sdist_url}")
    print(f"sdist sha256 : {sdist_sha}")
    print(f"formula sha  : {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
