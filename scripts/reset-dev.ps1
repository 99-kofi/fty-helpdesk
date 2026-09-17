# FTY HelpDesk - fresh dev reset (Windows PowerShell, run from repo root).
# Backs up backend\fty.db with a timestamp, then wipes all local dev/test data
# (customers, conversations, messages, tickets, users, teams, history).
# Code, backend\.env credentials, and the isolated logo are never touched.
# Afterward: restart the backend, log in (admin auto-seeds on login).
$ErrorActionPreference = "Stop"

$db = "backend\fty.db"
if (Test-Path $db) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  Copy-Item $db "backend\fty.db.bak-$stamp"
  Write-Host "Backup saved: backend\fty.db.bak-$stamp"
  try {
    Remove-Item $db -Force -ErrorAction Stop
  } catch {
    Write-Host "STOP THE BACKEND FIRST (Ctrl+C in its window), then re-run this script."
    Write-Host "The database file is locked by the running server."
    exit 1
  }
  foreach ($ext in @("-journal", "-wal", "-shm")) {
    if (Test-Path "$db$ext") { Remove-Item "$db$ext" -Force }
  }
  Write-Host "Cleared: $db (+ journals)"
} else {
  Write-Host "No dev database found - already fresh."
}

Get-ChildItem -Recurse -Directory -Filter "__pycache__" backend | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force backend\.pytest_cache -ErrorAction SilentlyContinue
Write-Host "Caches cleared. Restart the backend for a fresh system."
