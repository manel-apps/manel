@echo off
call ".venv\Scripts\activate.bat"

if "%~1"=="" (
    python -m manel.cli gui
) else (
    python -m manel.cli %*
)
