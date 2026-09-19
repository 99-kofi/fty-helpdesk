# Share your local FTY HelpDesk publicly (no deploy needed).
# Run from repo root: .\scripts\share.ps1
# Requires: backend on :8000 and frontend on :5173 (.\scripts\start-dev.ps1)
# Uses npx localtunnel — no account needed. Keep this window open while sharing.

$ErrorActionPreference = "Stop"

$frontPort = 5173
$backPort  = 8000

function Test-Port($port) {
  try { (Invoke-WebRequest -Uri "http://localhost:$port/" -TimeoutSec 3 -UseBasicParsing).StatusCode -ge 200 } catch { $false }
}

if (-not (Test-Port $frontPort)) { Write-Host "Frontend not running on :$frontPort — run .\scripts\start-dev.ps1 first." -ForegroundColor Yellow; exit 1 }
if (-not (Test-Port $backPort))  { Write-Host "Backend not running on :$backPort — run .\scripts\start-dev.ps1 first." -ForegroundColor Yellow; exit 1 }

Write-Host "Starting public tunnels (localtunnel, no account)..."
Write-Host "  Frontend : http://localhost:$frontPort  -> public URL below"
Write-Host "  Backend  : http://localhost:$backPort   -> public URL below"
Write-Host ""
Write-Host "Keep this window open. Press Ctrl+C to stop sharing." -ForegroundColor Cyan
Write-Host ""

# Run both tunnels. Each prints: your url is: https://xxxx.loca.lt
# We launch them as parallel jobs so both URLs appear.

$jobs = @()
$jobs += Start-Job -ScriptBlock { param($p) npx --yes localtunnel --port $p } -ArgumentList $frontPort
$jobs += Start-Job -ScriptBlock { param($p) npx --yes localtunnel --port $p } -ArgumentList $backPort

# Stream output as it arrives
while ($true) {
  foreach ($j in $jobs) {
    $out = Receive-Job $j 2>&1
    if ($out) { $out | ForEach-Object { Write-Host $_ } }
  }
  Start-Sleep -Seconds 1
}
