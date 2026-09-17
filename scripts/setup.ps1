# FTY HelpDesk - first-time setup (Windows PowerShell, no Docker).
# Run from repo root: .\scripts\setup.ps1
$ErrorActionPreference = "Stop"

# 1. Backend venv + deps
if (-not (Test-Path "backend\.venv")) {
  python -m venv backend\.venv
}
& "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt

# 2. Backend .env (SQLite + local queue by default - no Postgres/Redis needed)
if (-not (Test-Path "backend\.env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" "backend\.env"
  Write-Host "Copied .env.example -> backend\.env (defaults work with zero external services)"
}

# 3. Frontend deps
Push-Location frontend
npm install
Pop-Location

Write-Host "`nDone. Start everything with: .\scripts\start-dev.ps1"
