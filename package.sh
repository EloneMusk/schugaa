#!/bin/bash
# Remove previous build artifacts to ensure clean build
rm -rf build dist
rm -f debug.py
if [ -d "venv" ]; then
    source venv/bin/activate
fi
pyinstaller --clean --noconfirm Schugaa.spec
# Note: Schugaa.spec does NOT include config.json in 'datas', ensuring it is not bundled.
rm -f Schugaa.dmg
hdiutil create -volname "Schugaa Installer" -srcfolder "dist/Schugaa.app" -ov -format UDZO "Schugaa.dmg"
