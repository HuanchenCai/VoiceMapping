@echo off
REM Voice Mapping launcher - double-click to open the GUI.
REM File contents are pure ASCII so the cmd parser (GBK on Chinese Windows)
REM can read this without any encoding issues. The filename itself can be
REM Chinese because Explorer uses Unicode.

cd /d "%~dp0"

REM Force Python to use UTF-8 for stdout/stderr so any log messages with
REM Chinese characters render cleanly in the console window if it appears.
set PYTHONUTF8=1

REM Find a usable Python (same probe order as build_exe.bat):
REM   1. VOICEMAP_PYTHON env var (override)
REM   2. user's known conda env (developer machine default)
REM   3. anything called "python" on PATH
set PY=
if defined VOICEMAP_PYTHON if exist "%VOICEMAP_PYTHON%" set PY=%VOICEMAP_PYTHON%
if not defined PY if exist "%USERPROFILE%\miniconda3\envs\fonadyn\python.exe" set PY=%USERPROFILE%\miniconda3\envs\fonadyn\python.exe
if not defined PY if exist "%USERPROFILE%\anaconda3\envs\fonadyn\python.exe" set PY=%USERPROFILE%\anaconda3\envs\fonadyn\python.exe
if not defined PY for %%P in (python.exe) do if not defined PY set PY=%%~$PATH:P

if not defined PY (
    echo [ERROR] No Python found.
    echo Set VOICEMAP_PYTHON to your interpreter, install conda env "fonadyn",
    echo or put python on PATH.
    pause
    exit /b 1
)

start "" "%PY%" main.py --gui

REM Optional: if you want to see logs in a console window, replace the
REM `start "" ...` line above with:
REM     "%PY%" main.py --gui
REM     if errorlevel 1 pause
