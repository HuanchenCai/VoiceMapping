#!/bin/bash
# Build FonaDyn.app for macOS
# Requirements: pip install pyinstaller

set -e

echo "Installing / updating dependencies..."
pip install pyinstaller numpy scipy pandas soundfile numba

echo ""
echo "Building FonaDyn.app..."
pyinstaller FonaDyn.spec --clean --noconfirm

echo ""
echo "Done! App bundle is at:  dist/FonaDyn.app"
echo ""
echo "To create a DMG for distribution:"
echo "  hdiutil create -volname FonaDyn -srcfolder dist/FonaDyn.app -ov -format UDZO dist/FonaDyn.dmg"
