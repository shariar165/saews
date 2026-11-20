# Start the development server using the project venv.
Set-Location (Split-Path $PSScriptRoot -Parent)
& ".\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --reload --port 8000
