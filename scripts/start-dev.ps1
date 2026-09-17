# FTY HelpDesk - run backend + frontend natively (no Docker).
# Run from repo root: .\scripts\start-dev.ps1
$ErrorActionPreference = "Stop"

# Backend: uvicorn with reload (http://localhost:8000/docs)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..\\backend'; ..\\.venv\\Scripts\\Activate.ps1; uvicorn app.main:app --reload --port 8000"

# Frontend: vite dev server (http://localhost:5173)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..\\frontend'; npm run dev"

Write-Host "Backend  -> http://localhost:8000/docs"
Write-Host "Frontend -> http://localhost:5173"
Write-Host "Login: POST /api/v1/auth/seed-admin then login as admin@fty.local / admin123"
