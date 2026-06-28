@echo off
REM Activate virtualenv if present, then start the FastAPI backend
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
pause
