#requires -Version 5.1
<#
  Local + CI orchestrator for the Pythinker Code Windows native installer.

  Steps:
    1. Validate version, generate versioninfo.generated.txt.
    2. Run PyInstaller using pythinker.spec -> dist/pythinker/
    3. Sign dist/pythinker/pythinker.exe (no-op if cert env unset).
    4. Compile installer.iss with iscc -> dist/PythinkerSetup-<Version>.exe
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
