# Windows Native Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a code-signable, downloadable Windows installer (`PythinkerSetup-x.y.z.exe`) that drops a self-contained, PyInstaller-frozen `pythinker.exe` onto a user's machine — no Python, no Node, no uv prerequisite — with in-app updates that re-run the installer silently.

**Architecture:** Inno Setup wizard wrapping a PyInstaller `--onedir` build. Per-user install to `%LOCALAPPDATA%\Programs\Pythinker`, HKCU PATH, no UAC. Build pipeline runs on `windows-latest` in GitHub Actions, triggered by `pythinker-code-v*` tags. Code-signing is wired in via a GitHub Secret and is a no-op until that secret is populated. The runtime detects the native build through a sentinel file (`.pythinker-native`) and routes `pythinker update` to download + silently re-run the latest setup.

**Tech Stack:** Python 3.13, PyInstaller, Inno Setup 6, PowerShell, GitHub Actions, signtool / Authenticode, Typer (existing CLI), aiohttp (existing HTTP client).

**Spec:** `docs/superpowers/specs/2026-05-22-windows-native-installer-design.md`

---

## Files to create / modify

| Path | Responsibility |
|---|---|
| `packages/windows-installer/README.md` | Build instructions, prerequisites |
| `packages/windows-installer/build.ps1` | Local + CI orchestrator (freeze → sign → compile → sign) |
| `packages/windows-installer/pythinker.spec` | PyInstaller spec (onedir, hidden imports, version metadata) |
| `packages/windows-installer/installer.iss` | Inno Setup script |
| `packages/windows-installer/versioninfo.txt` | PyInstaller `--version-file` metadata |
| `packages/windows-installer/.pythinker-native` | Empty sentinel file dropped by installer; runtime probes for it |
| `packages/windows-installer/assets/pythinker.ico` | Generated app icon |
| `packages/windows-installer/assets/LICENSE.rtf` | Apache-2.0 in RTF format for the EULA page |
| `packages/windows-installer/sign/sign.ps1` | signtool wrapper (no-op when cert secret unset) |
| `src/pythinker_code/native.py` | `is_native_build()`, `native_installer_release_url()` |
| `src/pythinker_code/ui/shell/update.py` | Extend `_detect_upgrade_command()` / update flow to handle native builds |
| `tests/unit/test_native.py` | Unit tests for `native.py` |
| `tests/unit/ui/shell/test_update_native.py` | Unit tests for the native-build update branch |
| `.github/workflows/windows-installer.yml` | Tag-triggered build + sign + Release upload |
| `README.md` | New *Windows (native)* install section |

---

## Task 1: Scaffold `packages/windows-installer/` directory

**Files:**
- Create: `packages/windows-installer/README.md`
- Create: `packages/windows-installer/.pythinker-native`

- [ ] **Step 1: Create the directory and a README**

Create `packages/windows-installer/README.md` with:

```markdown
# Pythinker Windows Native Installer

Builds `PythinkerSetup-x.y.z.exe`, a downloadable Inno Setup wizard that drops a
PyInstaller-frozen `pythinker.exe` on a Windows machine with no Python / Node /
uv prerequisite.

## Prerequisites (local builds)

- Windows 10/11 x64
- Python 3.13 (matching the wheel index used by `pyproject.toml`)
- [Inno Setup 6](https://jrsoftware.org/isdl.php) on PATH (`iscc.exe`)
- `uv` for resolving `pythinker-code`'s dependencies
- Optional: a Windows Authenticode certificate as PFX for signing. If you don't
  set `WINDOWS_CERT_PFX_BASE64` + `WINDOWS_CERT_PASSWORD`, the build still
  succeeds but produces an unsigned installer.

## Build

```powershell
pwsh packages/windows-installer/build.ps1 -Version 0.11.0
```

Outputs `dist/PythinkerSetup-0.11.0.exe`.

## CI

The `windows-installer.yml` workflow runs this build on every
`pythinker-code-v*` tag push and uploads the installer to the corresponding
GitHub Release.

See `docs/superpowers/specs/2026-05-22-windows-native-installer-design.md` for
the full design.
```

- [ ] **Step 2: Create the runtime sentinel file**

Create `packages/windows-installer/.pythinker-native` containing exactly one line:

```
pythinker-native-build
```

This file is bundled by `installer.iss` and dropped next to `pythinker.exe`.
The runtime probes for it in Task 7 to decide whether to use the native update
path.

- [ ] **Step 3: Commit**

```bash
git add packages/windows-installer/README.md packages/windows-installer/.pythinker-native
git commit -m "feat(installer): scaffold windows installer package"
```

---

## Task 2: PyInstaller spec + version metadata

**Files:**
- Create: `packages/windows-installer/versioninfo.txt`
- Create: `packages/windows-installer/pythinker.spec`

- [ ] **Step 1: Write the version-info template**

Create `packages/windows-installer/versioninfo.txt`:

```
# Template consumed by PyInstaller via --version-file.
# build.ps1 substitutes ${VERSION} with the tag (e.g. 0.11.0).
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(${VERSION_TUPLE}),
    prodvers=(${VERSION_TUPLE}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Pythinker'),
         StringStruct(u'FileDescription', u'Pythinker Code CLI'),
         StringStruct(u'FileVersion', u'${VERSION}'),
         StringStruct(u'InternalName', u'pythinker'),
         StringStruct(u'LegalCopyright', u'Copyright (c) Pythinker contributors'),
         StringStruct(u'OriginalFilename', u'pythinker.exe'),
         StringStruct(u'ProductName', u'Pythinker Code'),
         StringStruct(u'ProductVersion', u'${VERSION}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
```

`${VERSION}` and `${VERSION_TUPLE}` are substituted by `build.ps1` (Task 6).

- [ ] **Step 2: Write the PyInstaller spec**

Create `packages/windows-installer/pythinker.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Pythinker Code Windows native build.
# Mode: --onedir (faster startup, fewer AV false-positives than --onefile).

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
    datas=[
        ("../.pythinker-native", "."),
    ],
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
    icon="assets/pythinker.ico",
    version="versioninfo.generated.txt",
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
```

- [ ] **Step 3: Write the entrypoint shim**

Create `packages/windows-installer/entrypoint.py`:

```python
"""PyInstaller entry shim for pythinker.exe.

We re-export the existing Typer app so PyInstaller can freeze a single
exe that behaves identically to `python -m pythinker_code`.
"""
from __future__ import annotations

import sys


def main() -> int:
    from pythinker_code.cli import app  # Typer instance

    app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Commit**

```bash
git add packages/windows-installer/versioninfo.txt \
        packages/windows-installer/pythinker.spec \
        packages/windows-installer/entrypoint.py
git commit -m "feat(installer): pyinstaller spec + version metadata"
```

---

## Task 3: Inno Setup script

**Files:**
- Create: `packages/windows-installer/installer.iss`

- [ ] **Step 1: Write the Inno Setup script**

Create `packages/windows-installer/installer.iss`:

```pascal
; Pythinker Code — Windows native installer
; Inno Setup 6 syntax. Per-user install, no UAC by default.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{4F4F2EAE-9D55-4E8E-92BC-7C1FA38B6F02}
AppName=Pythinker Code
AppVersion={#AppVersion}
AppPublisher=Pythinker
AppPublisherURL=https://pythinker.com
AppSupportURL=https://github.com/TechMatrix-labs/pythinker-code/issues
AppUpdatesURL=https://github.com/TechMatrix-labs/pythinker-code/releases
DefaultDirName={localappdata}\Programs\Pythinker
DefaultGroupName=Pythinker
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\..\dist
OutputBaseFilename=PythinkerSetup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\pythinker.ico
UninstallDisplayIcon={app}\pythinker.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=assets\LICENSE.rtf
ChangesEnvironment=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "modifypath"; Description: "Add Pythinker to your PATH"; \
  GroupDescription: "Shell integration:"; Check: not IsAdminInstallMode

Name: "modifypathmachine"; Description: "Add Pythinker to the system PATH"; \
  GroupDescription: "Shell integration:"; Check: IsAdminInstallMode

[Files]
Source: "..\..\dist\pythinker\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pythinker"; Filename: "{app}\pythinker.exe"
Name: "{group}\Uninstall Pythinker"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\pythinker.exe"; Description: "Launch Pythinker"; \
  Flags: nowait postinstall skipifsilent unchecked

[Code]
function NeedsAddPath(Param, RootHive: string): Boolean;
var
  OrigPath: string;
  Root: Integer;
  Subkey, ValueName: string;
begin
  if RootHive = 'HKCU' then begin
    Root := HKEY_CURRENT_USER;
    Subkey := 'Environment';
  end else begin
    Root := HKEY_LOCAL_MACHINE;
    Subkey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end;
  ValueName := 'Path';
  if not RegQueryStringValue(Root, Subkey, ValueName, OrigPath) then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + UpperCase(Param) + ';',
                ';' + UpperCase(OrigPath) + ';') = 0;
end;

procedure AddToPath(Param, RootHive: string);
var
  OrigPath, NewPath: string;
  Root: Integer;
  Subkey: string;
begin
  if RootHive = 'HKCU' then begin
    Root := HKEY_CURRENT_USER;
    Subkey := 'Environment';
  end else begin
    Root := HKEY_LOCAL_MACHINE;
    Subkey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end;
  if not RegQueryStringValue(Root, Subkey, 'Path', OrigPath) then
    OrigPath := '';
  if OrigPath = '' then
    NewPath := Param
  else
    NewPath := OrigPath + ';' + Param;
  RegWriteExpandStringValue(Root, Subkey, 'Path', NewPath);
end;

procedure RemoveFromPath(Param, RootHive: string);
var
  OrigPath: string;
  Root: Integer;
  Subkey: string;
begin
  if RootHive = 'HKCU' then begin
    Root := HKEY_CURRENT_USER;
    Subkey := 'Environment';
  end else begin
    Root := HKEY_LOCAL_MACHINE;
    Subkey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end;
  if not RegQueryStringValue(Root, Subkey, 'Path', OrigPath) then exit;
  StringChangeEx(OrigPath, ';' + Param, '', True);
  StringChangeEx(OrigPath, Param + ';', '', True);
  StringChangeEx(OrigPath, Param, '', True);
  RegWriteExpandStringValue(Root, Subkey, 'Path', OrigPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir: string;
begin
  if CurStep = ssPostInstall then begin
    AppDir := ExpandConstant('{app}');
    if WizardIsTaskSelected('modifypath')
       and NeedsAddPath(AppDir, 'HKCU') then
      AddToPath(AppDir, 'HKCU');
    if WizardIsTaskSelected('modifypathmachine')
       and NeedsAddPath(AppDir, 'HKLM') then
      AddToPath(AppDir, 'HKLM');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
begin
  if CurUninstallStep = usUninstall then begin
    AppDir := ExpandConstant('{app}');
    RemoveFromPath(AppDir, 'HKCU');
    if IsAdminInstallMode then
      RemoveFromPath(AppDir, 'HKLM');
  end;
end;

function InitializeSetup(): Boolean;
var
  OtherScopeKey: string;
  Found: Boolean;
begin
  // Refuse to install per-user over an existing per-machine install (or vice
  // versa) without first uninstalling the other one.
  if IsAdminInstallMode then
    OtherScopeKey :=
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{4F4F2EAE-9D55-4E8E-92BC-7C1FA38B6F02}_is1'
  else
    OtherScopeKey :=
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{4F4F2EAE-9D55-4E8E-92BC-7C1FA38B6F02}_is1';

  if IsAdminInstallMode then
    Found := RegKeyExists(HKEY_CURRENT_USER, OtherScopeKey)
  else
    Found := RegKeyExists(HKEY_LOCAL_MACHINE, OtherScopeKey);

  if Found then begin
    MsgBox('An existing Pythinker install was found at a different scope. '
           + 'Please uninstall it from Apps & Features before continuing.',
           mbError, MB_OK);
    Result := False;
  end else
    Result := True;
end;
```

- [ ] **Step 2: Commit**

```bash
git add packages/windows-installer/installer.iss
git commit -m "feat(installer): inno setup script with HKCU/HKLM path handling"
```

---

## Task 4: Sign-tool wrapper

**Files:**
- Create: `packages/windows-installer/sign/sign.ps1`

- [ ] **Step 1: Write the signing wrapper**

Create `packages/windows-installer/sign/sign.ps1`:

```powershell
#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Target
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Target)) {
    Write-Error "sign.ps1: target not found: $Target"
    exit 1
}

$pfxB64 = $env:WINDOWS_CERT_PFX_BASE64
$pfxPwd = $env:WINDOWS_CERT_PASSWORD

if (-not $pfxB64 -or -not $pfxPwd) {
    Write-Warning "sign.ps1: WINDOWS_CERT_PFX_BASE64 / WINDOWS_CERT_PASSWORD not set; skipping signing of $Target"
    exit 0
}

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) {
    $candidates = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool.exe$' } |
        Sort-Object FullName -Descending
    if ($candidates) { $signtool = $candidates[0] }
}
if (-not $signtool) {
    Write-Error "sign.ps1: signtool.exe not found on PATH and no fallback under Windows Kits"
    exit 1
}

$tmpPfx = [System.IO.Path]::GetTempFileName()
$tmpPfx = [System.IO.Path]::ChangeExtension($tmpPfx, '.pfx')
try {
    [IO.File]::WriteAllBytes($tmpPfx, [Convert]::FromBase64String($pfxB64))

    $args = @(
        'sign',
        '/f', $tmpPfx,
        '/p', $pfxPwd,
        '/tr', 'http://timestamp.digicert.com',
        '/td', 'sha256',
        '/fd', 'sha256',
        $Target
    )
    & $signtool.Source @args
    if ($LASTEXITCODE -ne 0) {
        Write-Error "sign.ps1: signtool exited with $LASTEXITCODE"
        exit $LASTEXITCODE
    }
    Write-Host "sign.ps1: signed $Target"
} finally {
    if (Test-Path $tmpPfx) {
        Remove-Item $tmpPfx -Force -ErrorAction SilentlyContinue
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/windows-installer/sign/sign.ps1
git commit -m "feat(installer): signtool wrapper, no-op when cert env unset"
```

---

## Task 5: Build orchestrator

**Files:**
- Create: `packages/windows-installer/build.ps1`

- [ ] **Step 1: Write the orchestrator**

Create `packages/windows-installer/build.ps1`:

```powershell
#requires -Version 5.1
<#
  Local + CI orchestrator for the Pythinker Code Windows native installer.

  Steps:
    1. Validate version, generate versioninfo.generated.txt.
    2. Run PyInstaller using pythinker.spec → dist/pythinker/
    3. Sign dist/pythinker/pythinker.exe (no-op if cert env unset).
    4. Compile installer.iss with iscc → dist/PythinkerSetup-<Version>.exe
    5. Sign the resulting setup .exe.
    6. Write SHA256 next to the installer.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [string] $Python = 'python',
    [switch] $SkipFreeze,
    [switch] $SkipInstaller
)

$ErrorActionPreference = 'Stop'

$here   = Split-Path -Parent $PSCommandPath
$repo   = Resolve-Path (Join-Path $here '..\..')
$dist   = Join-Path $repo 'dist'

if (-not (Test-Path $dist)) { New-Item -ItemType Directory -Path $dist | Out-Null }

# --- 1. version metadata ---------------------------------------------------
$parts  = $Version.Split('.')
while ($parts.Count -lt 4) { $parts += '0' }
$tuple  = ($parts[0..3] -join ', ')

$verTemplate = Get-Content (Join-Path $here 'versioninfo.txt') -Raw
$verTemplate = $verTemplate `
    -replace '\$\{VERSION\}',       $Version `
    -replace '\$\{VERSION_TUPLE\}', $tuple
$verOut = Join-Path $here 'versioninfo.generated.txt'
Set-Content -Path $verOut -Value $verTemplate -Encoding UTF8

Write-Host "build.ps1: building Pythinker $Version"

# --- 2. PyInstaller --------------------------------------------------------
if (-not $SkipFreeze) {
    Push-Location $here
    try {
        & $Python -m PyInstaller --noconfirm --distpath (Join-Path $repo 'dist') --workpath (Join-Path $repo 'build\windows-installer') pythinker.spec
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
}

$frozenExe = Join-Path $dist 'pythinker\pythinker.exe'
if (-not (Test-Path $frozenExe)) {
    throw "build.ps1: frozen binary not found at $frozenExe"
}

# --- 3. sign inner exe -----------------------------------------------------
& (Join-Path $here 'sign\sign.ps1') $frozenExe

# --- 4. Inno Setup compile -------------------------------------------------
if (-not $SkipInstaller) {
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $iscc = Get-Command 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' -ErrorAction SilentlyContinue
    }
    if (-not $iscc) {
        throw "build.ps1: iscc.exe not found. Install Inno Setup 6."
    }
    & $iscc.Source "/DAppVersion=$Version" (Join-Path $here 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed ($LASTEXITCODE)" }
}

$installer = Join-Path $dist "PythinkerSetup-$Version.exe"
if (-not (Test-Path $installer)) {
    throw "build.ps1: installer not produced at $installer"
}

# --- 5. sign installer -----------------------------------------------------
& (Join-Path $here 'sign\sign.ps1') $installer

# --- 6. SHA-256 -----------------------------------------------------------
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
$shaFile = "$installer.sha256"
Set-Content -Path $shaFile -Value "$hash  $(Split-Path -Leaf $installer)" -Encoding ASCII

Write-Host ""
Write-Host "  installer : $installer"
Write-Host "  sha256    : $hash"
Write-Host "  sha file  : $shaFile"
```

- [ ] **Step 2: Commit**

```bash
git add packages/windows-installer/build.ps1
git commit -m "feat(installer): build orchestrator (freeze, sign, compile, hash)"
```

---

## Task 6: License RTF + icon asset placeholders

**Files:**
- Create: `packages/windows-installer/assets/LICENSE.rtf`
- Create: `packages/windows-installer/assets/README.md`

- [ ] **Step 1: Generate a minimal RTF wrapper around the Apache-2.0 text**

Create `packages/windows-installer/assets/LICENSE.rtf`:

```
{\rtf1\ansi\deff0
{\fonttbl{\f0\fnil\fcharset0 Calibri;}}
\fs20\par
\b Apache License 2.0\b0\par\par
Pythinker Code is licensed under the Apache License, Version 2.0 (the
"License"); you may not use this software except in compliance with the
License. You may obtain a copy of the License at\par\par
http://www.apache.org/licenses/LICENSE-2.0\par\par
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations under
the License.\par\par
See the full LICENSE file in the repository for the complete text.\par
}
```

- [ ] **Step 2: Write an asset README documenting what needs to be regenerated**

Create `packages/windows-installer/assets/README.md`:

```markdown
# Installer assets

- `pythinker.ico` — Windows multi-resolution icon (16/32/48/256). Regenerate
  from `docs/media/logo.png` with ImageMagick:
  `magick docs/media/logo.png -define icon:auto-resize=16,32,48,256 packages/windows-installer/assets/pythinker.ico`.
  Committed as a binary blob; do not hand-edit.

- `LICENSE.rtf` — Apache-2.0 wrapper shown on the wizard's EULA page.

- (Optional) `pythinker-banner.bmp` (164×314, 24-bit) — left wizard image.
- (Optional) `pythinker-header.bmp` (150×57, 24-bit) — top-right wizard image.

If the optional banners are absent, Inno Setup falls back to its default
modern-style wizard chrome, which is acceptable for v1.
```

- [ ] **Step 3: Commit**

```bash
git add packages/windows-installer/assets/
git commit -m "feat(installer): license rtf + asset README"
```

Note: the binary `pythinker.ico` is generated by Task 8 (CI) using ImageMagick;
local builds without it will fail at PyInstaller's icon resolution step. That's
fine — local devs follow the instructions in the asset README.

---

## Task 7: Native-build detection helper

**Files:**
- Create: `src/pythinker_code/native.py`
- Create: `tests/unit/test_native.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_native.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from pythinker_code import native


def test_is_native_build_false_when_not_frozen():
    with patch.object(sys, "frozen", False, create=True):
        assert native.is_native_build() is False


def test_is_native_build_false_when_frozen_without_sentinel(tmp_path):
    fake_exe = tmp_path / "pythinker.exe"
    fake_exe.write_bytes(b"")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", str(fake_exe)):
        assert native.is_native_build() is False


def test_is_native_build_true_when_sentinel_present(tmp_path):
    fake_exe = tmp_path / "pythinker.exe"
    fake_exe.write_bytes(b"")
    (tmp_path / ".pythinker-native").write_text("pythinker-native-build")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", str(fake_exe)):
        assert native.is_native_build() is True


def test_native_installer_release_url_latest():
    url = native.native_installer_release_url(channel="latest")
    assert url == (
        "https://api.github.com/repos/TechMatrix-labs/"
        "pythinker-code/releases/latest"
    )


def test_native_installer_release_url_stable():
    url = native.native_installer_release_url(channel="stable")
    assert "/releases/tags/stable" in url


def test_native_installer_asset_name():
    assert native.native_installer_asset_name("0.11.0") == "PythinkerSetup-0.11.0.exe"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_native.py -v
```

Expected: 6 failures with `ModuleNotFoundError: No module named 'pythinker_code.native'`.

- [ ] **Step 3: Implement `native.py`**

Create `src/pythinker_code/native.py`:

```python
"""Native-build detection + GitHub Releases lookup helpers.

The Windows native installer drops a sentinel file ``.pythinker-native`` next
to the PyInstaller-frozen ``pythinker.exe``. The runtime probes for that file
to decide whether ``pythinker update`` should re-run the native installer
instead of shelling out to ``uv tool upgrade``.
"""
from __future__ import annotations

import sys
from pathlib import Path

GITHUB_REPO = "TechMatrix-labs/pythinker-code"
SENTINEL_FILENAME = ".pythinker-native"


def is_native_build() -> bool:
    """True iff this process is a Pythinker native (Inno Setup) install."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        exe_dir = Path(sys.executable).resolve().parent
    except OSError:
        return False
    return (exe_dir / SENTINEL_FILENAME).is_file()


def native_installer_release_url(channel: str = "latest") -> str:
    """Return the GitHub API URL for the requested release channel."""
    if channel == "latest":
        return f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    return f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{channel}"


def native_installer_asset_name(version: str) -> str:
    """Filename of the installer asset attached to a Release."""
    return f"PythinkerSetup-{version}.exe"
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/unit/test_native.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pythinker_code/native.py tests/unit/test_native.py
git commit -m "feat(native): add native-build detection + release URL helpers"
```

---

## Task 8: Wire native-build path into `update.py`

**Files:**
- Modify: `src/pythinker_code/ui/shell/update.py`
- Create: `tests/unit/ui/shell/test_update_native.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/ui/shell/test_update_native.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest

from pythinker_code.ui.shell import update as upd


def test_detect_upgrade_command_returns_native_marker_when_native():
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=True):
        cmd = upd._detect_upgrade_command()
    assert cmd == ["__pythinker_native_installer__"]


def test_detect_upgrade_command_pypi_path_when_not_native():
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=False), \
         patch("sys.executable", "/usr/local/bin/python"):
        cmd = upd._detect_upgrade_command()
    assert "pythinker-code" in cmd
    assert cmd[0] != "__pythinker_native_installer__"


@pytest.mark.asyncio
async def test_native_update_skipped_when_auto_disabled(monkeypatch):
    monkeypatch.setenv("DISABLE_AUTOUPDATER", "1")
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=True), \
         patch("pythinker_code.ui.shell.update._run_native_installer") as run_native:
        result = await upd._maybe_run_native_update(latest_version="9.9.9")
    run_native.assert_not_called()
    assert result is upd.UpdateResult.UPDATE_AVAILABLE
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/ui/shell/test_update_native.py -v
```

Expected: failures — `_is_native_build`, `_run_native_installer`,
`_maybe_run_native_update` not defined.

- [ ] **Step 3: Patch `update.py` — imports + native detection**

Add at the top of `src/pythinker_code/ui/shell/update.py`, after the existing
imports:

```python
import os
from pythinker_code.native import (
    is_native_build as _is_native_build,
    native_installer_release_url,
    native_installer_asset_name,
)
```

- [ ] **Step 4: Patch `_detect_upgrade_command` to branch on native build**

Replace the body of `_detect_upgrade_command` in `src/pythinker_code/ui/shell/update.py`
(lines 56-63):

```python
def _detect_upgrade_command() -> list[str]:
    """Pick the right upgrade argv based on how this interpreter was installed."""
    if _is_native_build():
        return ["__pythinker_native_installer__"]
    exe = sys.executable.replace("\\", "/").lower()
    if "/uv/tools/" in exe:
        return ["uv", "tool", "upgrade", "pythinker-code"]
    if "/pipx/venvs/" in exe:
        return ["pipx", "upgrade", "pythinker-code"]
    return [sys.executable, "-m", "pip", "install", "--upgrade", "pythinker-code"]
```

- [ ] **Step 5: Add the native-installer runner + orchestrator**

Append to `src/pythinker_code/ui/shell/update.py` (above the final `do_update`
function):

```python
NATIVE_INSTALLER_MARKER = "__pythinker_native_installer__"


async def _fetch_native_installer_asset(
    session: "aiohttp.ClientSession", latest_version: str, channel: str
) -> tuple[str, str] | None:
    """Return (download_url, sha256) for the installer asset, or None on failure."""
    url = native_installer_release_url(channel=channel)
    try:
        async with session.get(url, headers={"Accept": "application/vnd.github+json"}) as resp:
            if resp.status != 200:
                logger.warning("GitHub release lookup returned {status}", status=resp.status)
                return None
            payload = await resp.json()
    except Exception:
        logger.exception("Failed to look up native installer release")
        return None

    asset_name = native_installer_asset_name(latest_version)
    download_url: str | None = None
    sha256_url: str | None = None
    for asset in payload.get("assets", []):
        name = asset.get("name", "")
        if name == asset_name:
            download_url = asset.get("browser_download_url")
        elif name == asset_name + ".sha256":
            sha256_url = asset.get("browser_download_url")
    if not download_url or not sha256_url:
        logger.warning("Native installer asset {name} not found on release", name=asset_name)
        return None

    try:
        async with session.get(sha256_url) as resp:
            text = (await resp.text()).strip()
    except Exception:
        logger.exception("Failed to fetch installer sha256")
        return None
    sha = text.split()[0] if text else ""
    if len(sha) != 64:
        logger.warning("Installer sha256 has unexpected length: {n}", n=len(sha))
        return None
    return download_url, sha


def _run_native_installer(installer_path: Path) -> None:
    """Spawn the downloaded installer silently and exit this process."""
    subprocess.Popen(
        [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    sys.exit(0)


async def _maybe_run_native_update(latest_version: str, channel: str = "latest") -> UpdateResult:
    """Native-build update path. Returns UPDATED on success; UPDATE_AVAILABLE if skipped."""
    if os.environ.get("DISABLE_AUTOUPDATER"):
        logger.info("DISABLE_AUTOUPDATER set; skipping native auto-update")
        return UpdateResult.UPDATE_AVAILABLE

    import hashlib
    import tempfile

    timeout = aiohttp.ClientTimeout(total=120, sock_connect=10, sock_read=60)
    async with new_client_session(timeout=timeout) as session:
        fetched = await _fetch_native_installer_asset(session, latest_version, channel)
        if fetched is None:
            return UpdateResult.FAILED
        download_url, expected_sha = fetched

        tmpdir = Path(tempfile.mkdtemp(prefix="pythinker-update-"))
        installer = tmpdir / native_installer_asset_name(latest_version)
        try:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    logger.warning("Installer download returned {status}", status=resp.status)
                    return UpdateResult.FAILED
                with installer.open("wb") as fh:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        fh.write(chunk)
        except Exception:
            logger.exception("Installer download failed")
            return UpdateResult.FAILED

    digest = hashlib.sha256()
    with installer.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            digest.update(chunk)
    actual_sha = digest.hexdigest()
    if actual_sha != expected_sha:
        logger.error(
            "Installer sha mismatch: expected={expected} actual={actual}",
            expected=expected_sha,
            actual=actual_sha,
        )
        return UpdateResult.FAILED

    _run_native_installer(installer)
    return UpdateResult.UPDATED  # unreachable; sys.exit fires
```

- [ ] **Step 6: Branch the install execution on the native marker**

In `_do_update` (around line 338), replace the block that runs
`subprocess.run(upgrade_command)` to dispatch native vs. PyPI:

```python
if upgrade_command == [NATIVE_INSTALLER_MARKER]:
    _print("Downloading native installer for update...")
    native_result = await _maybe_run_native_update(latest_version)
    if native_result is UpdateResult.UPDATE_AVAILABLE:
        _print("[yellow]Auto-update disabled. "
               "Download the new installer manually from "
               "https://github.com/TechMatrix-labs/pythinker-code/releases/latest[/yellow]")
        return UpdateResult.UPDATE_AVAILABLE
    if native_result is UpdateResult.FAILED:
        _print("[red]Native update failed. "
               "Download manually from the releases page.[/red]")
        return UpdateResult.FAILED
    return native_result

try:
    result = subprocess.run(upgrade_command)
except OSError as e:
    logger.exception("Upgrade failed:")
    _print(f"[red]Upgrade failed:[/red] {e}")
    _print(f"Please run manually: {upgrade_command_text}")
    return UpdateResult.FAILED
```

- [ ] **Step 7: Run tests, verify pass**

```bash
pytest tests/unit/ui/shell/test_update_native.py tests/unit/test_native.py -v
```

Expected: 9 passed.

- [ ] **Step 8: Run the full update test module to make sure nothing regressed**

```bash
pytest tests/unit/ui/shell/ -v
```

Expected: all passing. If any pre-existing tests fail, fix them before
proceeding (likely by updating mocks of `_detect_upgrade_command`).

- [ ] **Step 9: Commit**

```bash
git add src/pythinker_code/ui/shell/update.py tests/unit/ui/shell/test_update_native.py
git commit -m "feat(update): route native builds through silent installer re-run"
```

---

## Task 9: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/windows-installer.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/windows-installer.yml`:

```yaml
name: Build Windows native installer

on:
  push:
    tags:
      - "pythinker-code-v*"
  workflow_dispatch:
    inputs:
      version:
        description: "Version to build (e.g. 0.11.0)"
        required: true
        type: string

jobs:
  build:
    runs-on: windows-latest
    permissions:
      contents: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Resolve version
        id: ver
        shell: pwsh
        run: |
          if ($env:GITHUB_REF -match '^refs/tags/pythinker-code-v(.+)$') {
            "version=$($Matches[1])" | Out-File -FilePath $env:GITHUB_OUTPUT -Append
          } elseif ('${{ inputs.version }}') {
            "version=${{ inputs.version }}" | Out-File -FilePath $env:GITHUB_OUTPUT -Append
          } else {
            throw "No version source"
          }

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv
        run: pip install uv

      - name: Sync project dependencies
        run: uv sync --frozen --no-dev

      - name: Install PyInstaller
        run: uv pip install pyinstaller

      - name: Generate icon (from logo.png)
        shell: pwsh
        run: |
          choco install -y imagemagick.tool --no-progress | Out-Null
          $logo = "docs/media/logo.png"
          if (-not (Test-Path $logo)) {
            throw "Expected logo source at $logo; cannot generate installer icon."
          }
          magick $logo -define icon:auto-resize=16,32,48,256 `
            "packages/windows-installer/assets/pythinker.ico"
          if ($LASTEXITCODE -ne 0) { throw "ImageMagick icon generation failed" }

      - name: Install Inno Setup
        run: choco install -y innosetup --no-progress

      - name: Build installer
        shell: pwsh
        env:
          WINDOWS_CERT_PFX_BASE64: ${{ secrets.WINDOWS_CERT_PFX_BASE64 }}
          WINDOWS_CERT_PASSWORD: ${{ secrets.WINDOWS_CERT_PASSWORD }}
        run: |
          $py = (& uv run python -c "import sys; print(sys.executable)").Trim()
          pwsh packages/windows-installer/build.ps1 -Version "${{ steps.ver.outputs.version }}" -Python $py

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: PythinkerSetup-${{ steps.ver.outputs.version }}
          path: |
            dist/PythinkerSetup-*.exe
            dist/PythinkerSetup-*.exe.sha256

      - name: Attach to Release
        if: startsWith(github.ref, 'refs/tags/pythinker-code-v')
        shell: pwsh
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          $tag = "${{ github.ref_name }}"
          gh release upload $tag dist/PythinkerSetup-*.exe dist/PythinkerSetup-*.exe.sha256 --clobber
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/windows-installer.yml
git commit -m "ci: tag-triggered windows native installer build"
```

---

## Task 10: README — add Windows (native) section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate the current install section**

```bash
grep -n "Quick Start\|Install\|pip install pythinker-code\|install.ps1" README.md | head -20
```

Note the line range of the existing install section. (Step 2 below assumes
there is a `## ⚡ Quick Start` heading; if the README structure differs, place
the new content above whatever section currently shows the PyPI install
command.)

- [ ] **Step 2: Insert the Windows-native install block**

Open `README.md` and add the following subsection at the *top* of the install
instructions (above the current PyPI / uv block). If the README uses a
`## ⚡ Quick Start` heading, place this block as the first item under it.

````markdown
### Windows — native installer (recommended)

A signed `PythinkerSetup-x.y.z.exe` is attached to every GitHub Release. It
bundles Pythinker as a self-contained executable; **you do not need Python, Node,
or uv installed**.

1. Download the latest installer from the
   [Releases page](https://github.com/TechMatrix-labs/pythinker-code/releases/latest)
   (`PythinkerSetup-x.y.z.exe`).
2. Run it. The wizard installs to `%LOCALAPPDATA%\Programs\Pythinker` and adds
   `pythinker` to your user PATH — no admin / UAC prompt.
3. Open a new PowerShell window and run `pythinker`.

Updates: `pythinker update` from inside the native build downloads the latest
installer from GitHub Releases, verifies its SHA-256, and re-runs it silently.
Set the env var `DISABLE_AUTOUPDATER=1` to opt out of automatic update prompts.

> If you prefer a one-liner from PowerShell:
>
> ```powershell
> irm https://raw.githubusercontent.com/TechMatrix-labs/pythinker-code/main/scripts/install-native.ps1 | iex
> ```
>
> *(That helper script ships in a follow-up; for now download the `.exe`
> directly.)*
````

- [ ] **Step 3: Run the README link checker if the project has one**

```bash
grep -rn "lychee\|markdownlint" .github/workflows 2>/dev/null
```

If a link checker exists, run it locally; otherwise skip. The new links are
relative to the GitHub repo and require no validation pre-merge.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add windows native installer install section to README"
```

---

## Task 11: Wire native helper into existing release readme-sync feedback

**Files:**
- Modify: `README.md` (the *What's New* block at the top, only on the next
  release that ships the installer — see note below)

> **Important:** This task is **conditional**. The user has a saved
> preference (`feedback_release_readme_sync`) that README "What's New",
> install snippets, and version-bearing badges must update in the same
> change set as the next version bump. This plan **does not** bump the
> version — that happens in a separate release commit. When the next
> release lands, the *What's New* section must mention the native
> installer.
>
> If you are executing this plan as part of a release commit, add the
> following line to the `## 🆕 What's New in <next-version>` section of
> README.md. Otherwise, **skip this task** and leave it for the release
> author.

- [ ] **Step 1 (conditional): Add the changelog entry**

In the appropriate "What's New" bullet list of `README.md`, add:

```markdown
- **Native Windows installer.** A signed `PythinkerSetup-x.y.z.exe` is now
  attached to every GitHub Release — install Pythinker on Windows with one
  download, no Python/Node/uv prerequisite. `pythinker update` re-runs the
  installer silently from inside the native build.
```

- [ ] **Step 2 (conditional): Commit alongside the release commit**

Combine with the existing release commit; do not create a standalone commit.

---

## Task 12: Manual acceptance verification (Windows 11 VM)

These steps cannot be automated from this Linux dev box. Run them on a clean
Windows 11 x64 VM that has neither Python, Node, nor uv installed.

- [ ] **Step 1: Download the installer artifact from the latest CI run**

  From the GitHub Actions UI, download `PythinkerSetup-<version>` artifact.

- [ ] **Step 2: Verify the SHA-256**

  ```powershell
  Get-FileHash .\PythinkerSetup-<version>.exe -Algorithm SHA256
  Get-Content .\PythinkerSetup-<version>.exe.sha256
  ```

  The hash from `Get-FileHash` must match the one in the `.sha256` file.

- [ ] **Step 3: Run the installer**

  Double-click `PythinkerSetup-<version>.exe`. Confirm:
  - **No UAC prompt** appears.
  - Wizard reaches *Finished* without errors.
  - `%LOCALAPPDATA%\Programs\Pythinker\pythinker.exe` exists.
  - `%LOCALAPPDATA%\Programs\Pythinker\.pythinker-native` exists.

- [ ] **Step 4: Verify PATH and CLI work**

  Open a **new** PowerShell window:

  ```powershell
  pythinker --version
  ```

  Expected: exact match for the installed version.

- [ ] **Step 5: Verify native update detection**

  ```powershell
  pythinker update --check
  ```

  Expected: either *Already up to date* or *Update available*; no `uv` /
  `pip` invocation appears in the output.

- [ ] **Step 6: Verify uninstall**

  Apps & Features → Pythinker Code → Uninstall. Confirm:
  - Install directory is removed.
  - A new PowerShell window cannot find `pythinker` on PATH.

- [ ] **Step 7: If signed, verify the Authenticode chain**

  ```powershell
  signtool verify /pa /v PythinkerSetup-<version>.exe
  ```

  Expected: *Successfully verified* + a valid RFC 3161 timestamp.

- [ ] **Step 8: File the verification results**

  Paste the output of steps 2-7 into `docs/superpowers/artifacts/<date>-windows-installer-verification.md`
  and commit it. This serves as evidence the acceptance criteria from section
  7 of the design were met.

---

## Self-review notes

- **Spec coverage:** every numbered design-doc section (architecture,
  components, build pipeline, update plumbing, distribution surfaces, risks)
  maps to a task above. Risk mitigations live inline: PATH conflict notice
  (Task 3 InitializeSetup), pre-cert window (Task 4 no-op signing), AV
  posture (Task 2 `--onedir`), sha verification (Task 8 step 5).
- **Linux dev box limitation:** Tasks 1-8 + 9 + 10 are authored on Linux;
  only Task 12 requires Windows. Task 7 + 8 tests run on Linux because they
  mock `sys.frozen` / `sys.executable`.
- **Frequent commits:** every task ends with a single focused commit; eleven
  commits total before the conditional release commit in Task 11.
- **No version bump in this plan:** the installer infrastructure ships as
  additive scaffolding. The user's
  `feedback_release_readme_sync` rule kicks in only on the release commit
  that bumps `pythinker-code` to the next version; Task 11 documents the
  changelog entry the release author must include.
