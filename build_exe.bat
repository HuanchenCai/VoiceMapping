@echo off
REM Build VoiceMap.exe via PyInstaller using VoiceMap.spec.
REM Run from project root: build_exe.bat
REM Output: dist\VoiceMap\VoiceMap.exe

cd /d "%~dp0"

REM 1. Find a usable Python:
REM    a. VOICEMAP_PYTHON env var (override)
REM    b. user's known conda env (developer machine default)
REM    c. anything called "python" on PATH
set PY=
if defined VOICEMAP_PYTHON if exist "%VOICEMAP_PYTHON%" set PY=%VOICEMAP_PYTHON%
if not defined PY if exist "%USERPROFILE%\miniconda3\envs\fonadyn\python.exe" set PY=%USERPROFILE%\miniconda3\envs\fonadyn\python.exe
if not defined PY if exist "%USERPROFILE%\anaconda3\envs\fonadyn\python.exe" set PY=%USERPROFILE%\anaconda3\envs\fonadyn\python.exe
if not defined PY for %%P in (python.exe) do if not defined PY set PY=%%~$PATH:P

if not defined PY (
    echo [ERROR] No Python found. Set VOICEMAP_PYTHON to your interpreter, or
    echo         install conda env "fonadyn", or put python on PATH.
    pause
    exit /b 1
)
echo Using Python: %PY%

REM 2. Ensure pyinstaller is available
"%PY%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing pyinstaller...
    "%PY%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] pyinstaller install failed.
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo  Building VoiceMap.exe
echo ========================================
echo.

"%PY%" -m PyInstaller --noconfirm --clean VoiceMap.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build complete.
echo  Output: dist\VoiceMap\VoiceMap.exe
echo ========================================
echo.
pause
