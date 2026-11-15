@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Install dependencies first: uv sync --locked
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m app
