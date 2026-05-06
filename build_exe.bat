@echo off
REM Build VoiceMap.exe via PyInstaller using VoiceMap.spec.
REM Run from project root: build_exe.bat
REM Output: dist\VoiceMap\VoiceMap.exe

cd /d "%~dp0"

set PY=C:\Users\huanc\miniconda3\envs\fonadyn\python.exe
if not exist "%PY%" (
    echo [ERROR] Python not found at: %PY%
    pause
    exit /b 1
)

REM Ensure pyinstaller is available
"%PY%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing pyinstaller...
    "%PY%" -m pip install pyinstaller
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
