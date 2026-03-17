@echo off
REM Build FonaDyn.exe for Windows
REM Uses the miniconda Python at %USERPROFILE%\miniconda3
REM Builds in an isolated venv to keep the exe small.

set PYTHON=%USERPROFILE%\miniconda3\python.exe
set CONDA=%USERPROFILE%\miniconda3

REM Tcl/Tk lives in the miniconda Library — tell PyInstaller where to find it
set TCL_LIBRARY=%CONDA%\Library\lib\tcl8.6
set TK_LIBRARY=%CONDA%\Library\lib\tk8.6

echo [1/3] Creating clean build environment...
"%PYTHON%" -m venv .venv_build
if errorlevel 1 goto :error

echo [2/3] Installing dependencies...
.venv_build\Scripts\pip.exe install --quiet numpy scipy pandas soundfile pyinstaller
if errorlevel 1 goto :error

echo [3/3] Building FonaDyn.exe...
.venv_build\Scripts\pyinstaller.exe FonaDyn.spec --clean --noconfirm
if errorlevel 1 goto :error

echo.
if exist dist\FonaDyn.exe (
    echo [OK] dist\FonaDyn.exe is ready.
) else (
    echo [FAILED] Build did not produce dist\FonaDyn.exe
)
pause
exit /b 0

:error
echo.
echo [ERROR] Build failed. See output above.
pause
exit /b 1
