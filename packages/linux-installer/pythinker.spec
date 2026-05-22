# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Pythinker Code Linux native packages (.deb / .rpm
# / tarball). Mode: --onedir — fpm wraps the directory into the package and
# install-native.sh tar-gzips it for the curl-bash flow.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = []
for pkg in (
    "pythinker_code",
    "pythinker_core",
    "fastmcp",
    "mcp",
    "typer",
    "aiohttp",
    "anyio",
    "rich",
):
    try:
        hiddenimports.extend(collect_submodules(pkg))
    except Exception:
        pass

a = Analysis(
    ["entrypoint.py"],
    pathex=[],
    binaries=[],
    # No PyInstaller datas: the runtime probe for the native build looks
    # next to the executable. Packagers drop sentinel + LICENSE separately.
    datas=[],
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
