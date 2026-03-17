@echo off
REM Build FonaDyn.exe for Windows
REM Requirements: pip install pyinstaller

echo Installing / updating dependencies...
pip install pyinstaller numpy scipy pandas soundfile numba

echo.
echo Building FonaDyn.exe...
pyinstaller FonaDyn.spec --clean --noconfirm

echo.
echo Done! Executable is at:  dist\FonaDyn.exe
pause
