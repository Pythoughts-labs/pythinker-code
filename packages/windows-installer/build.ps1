#requires -Version 5.1
<#
  Local + CI orchestrator for the Pythinker Code Windows native installer.

  Steps:
    1. Validate version, generate versioninfo.generated.txt.
    2. Run PyInstaller using pythinker.spec -> dist/pythinker/
    3. Sign bundled PE files (.exe/.dll/.pyd) when cert env is configured.
    4. Compile installer.iss with iscc -> dist/PythinkerSetup-<Version>.exe.
       When signing is configured, Inno signs Setup, Uninstall, and temp copies.
    5. Write SHA256 next to the installer.
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

$signScript = Join-Path $here 'sign\sign.ps1'
$signingConfigured = `
    -not [string]::IsNullOrWhiteSpace($env:WINDOWS_CERT_PFX_BASE64) -and `
    -not [string]::IsNullOrWhiteSpace($env:WINDOWS_CERT_PASSWORD)

if (-not $signingConfigured) {
    Write-Warning "build.ps1: WINDOWS_CERT_PFX_BASE64 / WINDOWS_CERT_PASSWORD not set; Windows artifacts will be unsigned"
}

function Invoke-PythinkerSign {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if ($signingConfigured) {
        & $signScript $Path
    }
}

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

# --- 3. sign bundled PE files ---------------------------------------------
if ($signingConfigured) {
    $bundleRoot = Join-Path $dist 'pythinker'
    $peFiles = Get-ChildItem $bundleRoot -Recurse -File |
        Where-Object { $_.Extension -in @('.exe', '.dll', '.pyd') }
    foreach ($file in $peFiles) {
        Invoke-PythinkerSign $file.FullName
    }
}

# --- 4. Inno Setup compile -------------------------------------------------
if (-not $SkipInstaller) {
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $iscc = Get-Command 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' -ErrorAction SilentlyContinue
    }
    if (-not $iscc) {
        throw "build.ps1: iscc.exe not found. Install Inno Setup 6."
    }
    $isccArgs = @("/DAppVersion=$Version")
    if ($signingConfigured) {
        $signCommand = "powershell.exe -NoProfile -NonInteractive -File `"$signScript`" `$f"
        $isccArgs += "/SPythinkerSign=$signCommand"
        $isccArgs += "/DUseInnoSignTool=1"
    }
    $isccArgs += (Join-Path $here 'installer.iss')

    & $iscc.Source @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed ($LASTEXITCODE)" }
}

$installer = Join-Path $dist "PythinkerSetup-$Version.exe"
if (-not (Test-Path $installer)) {
    throw "build.ps1: installer not produced at $installer"
}

# --- 5. sign installer when compilation was skipped ------------------------
if ($SkipInstaller) {
    Invoke-PythinkerSign $installer
} elseif ($signingConfigured) {
    Write-Host "build.ps1: installer, uninstaller, and setup temp copies signed by Inno Setup"
}

# --- 6. SHA-256 -----------------------------------------------------------
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
$shaFile = "$installer.sha256"
Set-Content -Path $shaFile -Value "$hash  $(Split-Path -Leaf $installer)" -Encoding ASCII

Write-Host ""
Write-Host "  installer : $installer"
Write-Host "  sha256    : $hash"
Write-Host "  sha file  : $shaFile"
