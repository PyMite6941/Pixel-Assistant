@echo off
echo === Pixel Assistant — First-time setup ===
echo.

REM Create virtual environment if it doesn't exist
if not exist ".venv\" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create .venv — make sure Python 3.10+ is installed.
        pause
        exit /b 1
    )
    echo Done.
) else (
    echo Virtual environment already exists.
)

echo.
echo Installing dependencies...
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Check requirements.txt and your internet connection.
    pause
    exit /b 1
)

echo.
echo === Setup complete ===
echo Run  start.bat      to launch the CLI
echo Run  start_web.bat  to launch the web UI
echo.
pause
