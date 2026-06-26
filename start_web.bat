@echo off
REM Launch Pixel Assistant web UI at http://localhost:8000
.venv\Scripts\uvicorn src.api.app:app --reload --port 8000
