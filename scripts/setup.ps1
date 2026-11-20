# One-time setup. Everything is installed into the project's .venv — never the global Python.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment in .venv ..."
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "Installing dependencies into .venv ..."
& $py -m pip install --upgrade pip -q
& $py -m pip install -r requirements-dev.txt -q

Write-Host "Creating database and loading synthetic demo data ..."
& $py -m backend.app.seed.generate --reset --skip-assess

Write-Host "Training and registering the risk model ..."
& $py -m backend.app.ml.train

Write-Host "Running initial risk assessment ..."
& $py -c "from backend.app.database import SessionLocal; from backend.app.services.risk_engine import assess_students; db=SessionLocal(); print(len(assess_students(db)), 'students assessed'); db.close()"

Write-Host "`nDone. Start the app with:  .\scripts\run.ps1"
