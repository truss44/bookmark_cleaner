# run.ps1 — Setup and run the Edge Favorites Cleaner
# Usage: .\run.ps1 [arguments to pass to bookmark_cleaner.py]
# Example: .\run.ps1 favorites_4_18_26.html --threads 10 --timeout 15

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir = Join-Path $ScriptDir ".venv"
$Script = Join-Path $ScriptDir "bookmark_cleaner.py"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Edge Favorites Cleaner & Organizer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python is available ──────────────────────────────────────────────
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Please install Python 3.10+ from https://python.org" -ForegroundColor Red
    exit 1
}

$PythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "Python version: $PythonVersion" -ForegroundColor Green

# ── Check bookmark_cleaner.py exists ──────────────────────────────────────
if (-not (Test-Path $Script)) {
    Write-Host "ERROR: bookmark_cleaner.py not found in $ScriptDir" -ForegroundColor Red
    exit 1
}

# ── Create virtual environment if it doesn't exist ────────────────────────
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
    Write-Host "Virtual environment created at: $VenvDir" -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

# ── Activate virtual environment ──────────────────────────────────────────
$Activate = Join-Path $VenvDir "Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
    Write-Host "ERROR: Could not find venv activation script at $Activate" -ForegroundColor Red
    exit 1
}

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& $Activate

# ── Install/upgrade dependencies ──────────────────────────────────────────
Write-Host "Installing dependencies..." -ForegroundColor Yellow
# Note: pip self-upgrade is skipped — it can fail inside a venv on Python 3.14+
pip install requests openai python-dotenv --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies ready." -ForegroundColor Green

# ── Prompt for input file if not provided ─────────────────────────────────
$ScriptArgs = $args
if ($ScriptArgs.Count -eq 0) {
    Write-Host ""
    $InputFile = Read-Host "Enter the path to your favorites HTML file"
    if ([string]::IsNullOrWhiteSpace($InputFile)) {
        Write-Host "ERROR: No input file provided." -ForegroundColor Red
        exit 1
    }
    $ScriptArgs = @($InputFile)
}

# ── Run the script ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Running bookmark_cleaner.py $ScriptArgs" -ForegroundColor Cyan
Write-Host ""

python $Script @ScriptArgs
$ExitCode = $LASTEXITCODE

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "Done." -ForegroundColor Green
} else {
    Write-Host "Script exited with code $ExitCode." -ForegroundColor Red
}

exit $ExitCode