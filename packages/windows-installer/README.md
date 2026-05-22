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
