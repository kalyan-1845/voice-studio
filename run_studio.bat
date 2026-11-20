@echo off
title AI Voice Studio
echo Starting AI Voice Studio...
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate
)

echo.
echo ========================================================
echo   AI Voice Studio is running at: http://localhost:7860
echo ========================================================
echo.

start http://localhost:7860
python -m uvicorn backend.app:app --host 127.0.0.1 --port 7860 --reload
pause
