#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting macOS DMG build"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

APP_NAME="Schugaa"
VOL_NAME="Schugaa Installer"

# ----------------------------
# Version (tag or dev)
# ----------------------------
if [[ -n "${BUILD_VERSION:-}" ]]; then
  VERSION="$BUILD_VERSION"
elif git describe --tags --dirty --always >/dev/null 2>&1; then
  VERSION="$(git describe --tags --dirty --always)"
else
  VERSION="dev"
fi

DMG_NAME="${APP_NAME}-${VERSION}.dmg"

echo "📦 Version: $VERSION"
echo "📁 Root: $ROOT_DIR"

# ----------------------------
# Clean previous artifacts
# ----------------------------
echo "🧹 Cleaning old artifacts"
rm -rf "$BUILD_DIR" "$DIST_DIR"
rm -f "$ROOT_DIR/${APP_NAME}.dmg" "$ROOT_DIR/${APP_NAME}-"*.dmg
rm -f "$ROOT_DIR/debug.py"

# ----------------------------
# Python environment
# ----------------------------
if [[ -d "$ROOT_DIR/venv" ]]; then
  echo "🐍 Activating virtualenv"
  source "$ROOT_DIR/venv/bin/activate"
else
  echo "ℹ️ No venv found – using system Python"
fi

python --version
pip --version

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "📥 Installing PyInstaller"
  pip install pyinstaller
fi

# ----------------------------
# Build app
# ----------------------------
echo "🔨 Running PyInstaller"
pyinstaller --clean --noconfirm "$ROOT_DIR/Schugaa.spec"

# ----------------------------
# Locate .app bundle (CI-safe)
# ----------------------------
echo "🔍 Locating app bundle"
APP_PATH="$(find "$DIST_DIR" -type d -name "${APP_NAME}.app" | head -n 1)"

if [[ -z "$APP_PATH" ]]; then
  echo "❌ ERROR: ${APP_NAME}.app not found"
  find "$DIST_DIR" -maxdepth 4
  exit 1
fi

echo "✅ Found app: $APP_PATH"

# ----------------------------
# Ad-hoc sign app (NO Apple ID required)
# ----------------------------
echo "🔐 Ad-hoc signing app bundle"
codesign --deep --force --sign - "$APP_PATH"

echo "🔎 Verifying signature"
codesign --verify --deep --strict "$APP_PATH"

# ----------------------------
# Create DMG with Applications shortcut
# ----------------------------
echo "💿 Creating DMG: $DMG_NAME"

# Create a temporary folder for the DMG contents
DMG_TEMP="$BUILD_DIR/dmg-temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Copy app to temp folder
cp -R "$APP_PATH" "$DMG_TEMP/"

# Create symlink to Applications folder for drag-and-drop install
ln -s /Applications "$DMG_TEMP/Applications"

hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$DMG_TEMP" \
  -ov \
  -format UDZO \
  "$ROOT_DIR/$DMG_NAME"

# Clean up temp folder
rm -rf "$DMG_TEMP"

# ----------------------------
# Final verification
# ----------------------------
echo "📦 DMG created successfully"
ls -lh "$ROOT_DIR/$DMG_NAME"

echo "✅ Build completed"