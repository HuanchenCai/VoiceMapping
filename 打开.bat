@echo off
REM Voice Mapping launcher - double-click to open the GUI.
REM File contents are pure ASCII so the cmd parser (GBK on Chinese Windows)
REM can read this without any encoding issues. The filename itself can be
REM Chinese because Explorer uses Unicode.

cd /d "%~dp0"

REM Force Python to use UTF-8 for stdout/stderr so any log messages with
REM Chinese characters render cleanly in the console window if it appears.
set PYTHONUTF8=1

REM Use the conda env python explicitly so the user doesn't need to
REM activate the env first.
set PY=C:\Users\huanc\miniconda3\envs\fonadyn\python.exe

if not exist "%PY%" (
    echo [ERROR] Python not found at: %PY%
    echo Edit this .bat and update the PY=... line to your Python path.
    pause
    exit /b 1
)

start "" "%PY%" main.py --gui

REM Optional: if you want to see logs in a console window, replace the
REM `start "" ...` line above with:
REM     "%PY%" main.py --gui
REM     if errorlevel 1 pause
