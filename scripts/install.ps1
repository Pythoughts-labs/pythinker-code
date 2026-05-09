$ErrorActionPreference = "Stop"

# Colors — match src/pythinker_code/ui/shell/__init__.py logo palette.
$useColor = $Host.UI.RawUI -ne $null -and -not $env:NO_COLOR
if ($useColor) {
  $NAVY  = "$([char]27)[38;5;24m"
  $FACE  = "$([char]27)[38;5;255m"
  $CORAL = "$([char]27)[38;5;216m"
  $IRIS  = "$([char]27)[38;5;152m"
  $DIM   = "$([char]27)[2m"
  $BOLD  = "$([char]27)[1m"
  $RESET = "$([char]27)[0m"
} else {
  $NAVY = $FACE = $CORAL = $IRIS = $DIM = $BOLD = $RESET = ""
}

function Print-Logo {
  Write-Host ""
  Write-Host "      $CORAL●$RESET"
  Write-Host "      $NAVY│$RESET"
  Write-Host "  $NAVY▛$RESET$FACE▀▀▀▀▀▀▀$RESET$NAVY▜$RESET"
  Write-Host " $CORAL◖$RESET$NAVY█$RESET $IRIS◉$RESET   $IRIS◉$RESET $NAVY█$RESET$CORAL◗$RESET"
  Write-Host "  $NAVY▙▄▄▄$RESET$FACE≡$RESET$NAVY▄▄▄▟$RESET"
  Write-Host ""
  Write-Host "  $BOLD$FACE`pythinker code$RESET $DIM`· your next CLI agent$RESET"
  Write-Host ""
}

function Step($msg) { Write-Host "  $IRIS⠿$RESET $msg" }
function OK($msg)   { Write-Host "  $IRIS✓$RESET $msg" }
function Fail($msg) { Write-Host "  $CORAL✗$RESET $msg" -ForegroundColor Red; exit 1 }

function Spin-Run($label, [scriptblock]$action) {
  Step $label
  $log = New-TemporaryFile
  try {
    & $action *>&1 | Out-File -FilePath $log -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
      Get-Content $log | Write-Host
      Fail $label
    }
  } finally {
    Remove-Item $log -ErrorAction SilentlyContinue
  }
}

function Refresh-Path {
  $MachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  if (-not $MachinePath) { $MachinePath = '' }
  $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not $UserPath) { $UserPath = '' }

  $ExtraPaths = @(
    Join-Path $env:USERPROFILE ".local\bin"
    Join-Path $env:USERPROFILE ".cargo\bin"
  )

  $env:PATH = (@(
    $MachinePath.TrimEnd(';'),
    $UserPath.TrimEnd(';')
  ) + $ExtraPaths).Where({ $_ }) -join ';'
}

function Install-Uv {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Step "Installing uv with winget"
    $wingetLog = New-TemporaryFile
    try {
      & winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements --silent *>&1 | Out-File -FilePath $wingetLog -Encoding utf8
      Refresh-Path
      if (Get-Command uv -ErrorAction SilentlyContinue) {
        OK "Installing uv with winget"
        return
      }
    } finally {
      Remove-Item $wingetLog -ErrorAction SilentlyContinue
    }
  }

  Step "Fetching uv (Python package installer)"
  $uvInstaller = Join-Path ([System.IO.Path]::GetTempPath()) "uv-install.ps1"
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/install.ps1" -OutFile $uvInstaller
    # Run in the current process (so $env:PATH / registry updates land here) but
    # inside an anonymous scope so Astral's variables and $ErrorActionPreference
    # don't leak into the rest of our script.
    & { . $uvInstaller }
  } finally {
    Remove-Item $uvInstaller -ErrorAction SilentlyContinue
  }
  OK "Fetching uv (Python package installer)"

  Refresh-Path
}

Print-Logo

if (Get-Command uv -ErrorAction SilentlyContinue) {
  $uvVersion = (& uv --version) -replace '^uv\s+', ''
  OK "uv already installed ($uvVersion)"
} else {
  Install-Uv
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Fail "uv not found after installation. Open a new shell and re-run."
}

Spin-Run "Installing pythinker-code" {
  & uv tool install --quiet --python 3.13 pythinker-code
}

# uv tool install drops shims in $USERPROFILE\.local\bin. Make sure the current
# session can find them even if uv didn't refresh the parent PATH.
Refresh-Path

Write-Host ""
Write-Host "  $BOLD$FACE`pythinker$RESET is ready."
if (Get-Command pythinker -ErrorAction SilentlyContinue) {
  Write-Host "  $DIM`Run$RESET $BOLD$IRIS`pythinker$RESET $DIM`to start.$RESET"
} else {
  $toolBin = Join-Path $env:USERPROFILE ".local\bin"
  Write-Host "  $DIM`pythinker is installed at$RESET $toolBin\pythinker.exe"
  Write-Host "  $DIM`Open a new PowerShell window and run$RESET $BOLD$IRIS`pythinker$RESET$DIM`, or run it by full path now.$RESET"
}
Write-Host ""
