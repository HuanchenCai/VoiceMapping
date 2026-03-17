#!/bin/bash
# Build FonaDyn.app for macOS
# Builds in an isolated venv to keep the app small.
# Run from the project root: bash build_mac.sh

set -e

echo "[1/3] Creating clean build environment..."
python3 -m venv .venv_build

echo "[2/3] Installing dependencies..."
.venv_build/bin/pip install --quiet numpy scipy pandas soundfile pyinstaller

echo "[3/3] Building FonaDyn.app..."
.venv_build/bin/pyinstaller FonaDyn.spec --clean --noconfirm

echo ""
if [ -d "dist/FonaDyn.app" ]; then
    echo "[OK] dist/FonaDyn.app is ready."
    echo ""
    echo "Optional: create a DMG for distribution:"
    echo "  hdiutil create -volname FonaDyn -srcfolder dist/FonaDyn.app -ov -format UDZO dist/FonaDyn.dmg"
else
    echo "[FAILED] Build did not produce dist/FonaDyn.app"
    exit 1
fi
