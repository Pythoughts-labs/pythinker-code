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
