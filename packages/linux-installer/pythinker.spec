# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Pythinker Code Linux native packages (.deb / .rpm
# / tarball). Mode: --onedir — fpm wraps the directory into the package and
# install-native.sh tar-gzips it for the curl-bash flow.

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# The web/vis frontends are gitignored build artifacts. collect_data_files()
# silently collects nothing when they are missing, which shipped installers
# whose web UI answered "/" with a 404. Fail the freeze loudly instead.
_pkg_spec = importlib.util.find_spec("pythinker_code")
if _pkg_spec is None or _pkg_spec.origin is None:
    raise SystemExit("pythinker.spec: pythinker_code is not installed in the build environment")
_pkg_root = Path(_pkg_spec.origin).resolve().parent
_missing_ui = [
    rel
    for rel in ("web/static/index.html", "vis/static/index.html")
    if not (_pkg_root / rel).is_file()
]
if _missing_ui:
    raise SystemExit(
        f"pythinker.spec: UI bundles missing from pythinker_code ({', '.join(_missing_ui)}). "
        "Run `make build-web build-vis` (or scripts/build_web.py and scripts/build_vis.py) "
        "before freezing, or the packaged web UI will 404 on '/'."
    )

block_cipher = None

hiddenimports = []
datas = []
for pkg in (
    "pythinker_code",
    "pythinker_core",
    "fastmcp",
    "mcp",
    "typer",
    "aiohttp",
    "anyio",
    "rich",
    # trafilatura and its justext fallback read bundled data by path at
    # runtime (settings.cfg, stoplists/). Unlike the tarball build
    # (pythinker.spec, which imports the shared datas list), this installer
    # spec collects data per-package, so these must be listed explicitly or
    # the native web Fetch tool crashes on the first extraction.
    "trafilatura",
    "justext",
):
    try:
        hiddenimports.extend(collect_submodules(pkg))
    except Exception:
        pass
    # pythinker_code ships *.md prompts, *.yaml agent specs, SKILL.md,
    # tool descriptions, etc. as package data. Without explicit
    # collect_data_files() PyInstaller misses them and the frozen binary
    # crashes the first time it tries to load init.md / coder.yaml / etc.
    try:
        datas.extend(collect_data_files(pkg, include_py_files=False))
    except Exception:
        pass

# Pygments loads a style module dynamically when config.tui.code_theme names a
# stock style (e.g. monokai); collect_submodules("rich") does not pull these in,
# so without this the frozen binary raises ClassNotFound on opted-in code themes.
try:
    hiddenimports.extend(collect_submodules("pygments.styles"))
except Exception:
    pass

# fastmcp calls importlib.metadata.version("fastmcp") at module import time.
# collect_data_files() only collects files inside the package directory; the
# dist-info lives alongside it in site-packages. copy_metadata() is the
# PyInstaller-standard hook for making importlib.metadata work in frozen apps.
# Do NOT suppress errors here: a missing dist-info produces a broken binary,
# so let PackageNotFoundError surface and fail the build loudly.
for pkg in ("fastmcp", "mcp"):
    datas += copy_metadata(pkg)

a = Analysis(
    ["entrypoint.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pythinker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="pythinker",
)
