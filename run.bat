@echo off
title JobShield - Multi-Agent Scam Screening
cd /d "%~dp0"

echo ============================================================
echo   JobShield: Multi-Agent Scam Risk Screening System
echo ============================================================
echo.

REM 1. Sync repository updates if git is available
where git >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [*] Checking for repository updates...
    git pull --quiet 2>nul
)

REM 2. Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.11 or higher from https://www.python.org/
    pause
    exit /b 1
)

REM 2. Create virtual environment if it does not exist
if not exist ".venv" (
    echo [*] Creating isolated virtual environment in .venv...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM 3. Install/Update requirements automatically
echo [*] Checking and installing dependencies...
call .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Some dependencies had warnings, continuing launch...
)

REM 4. Launch Streamlit app
echo.
echo ============================================================
echo   Launching JobShield Web App on http://localhost:8501
echo ============================================================
echo.
call .venv\Scripts\python.exe -m streamlit run app.py

pause
