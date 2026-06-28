@echo off
REM Start the Streamlit frontend
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
streamlit run frontend/app.py
pause
