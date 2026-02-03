#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting macOS DMG build..."

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

APP_NAME="Schugaa"
VOL_NAME="Schugaa Installer"

# ----------------------------
# Version handling
# ----------------------------
if git describe --tags --dirty --always >/dev/null 2>&1; then
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
echo "🧹 Cleaning old artifacts..."
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
  echo "⚠️ No venv found – using system Python"
fi

python --version
pip --version

# Ensure pyinstaller exists (important for GitHub Actions)
if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "📥 Installing pyinstaller"
  pip install pyinstaller
fi

# ----------------------------
# Build app
# ----------------------------
echo "🔨 Running PyInstaller..."
pyinstaller --clean --noconfirm "$ROOT_DIR/Schugaa.spec"

APP_PATH="$DIST_DIR/${APP_NAME}.app"

if [[ ! -d "$APP_PATH" ]]; then
  echo "❌ Build failed: ${APP_NAME}.app not found"
  exit 1
fi

# ----------------------------
# Create DMG
# ----------------------------
echo "💿 Creating DMG: $DMG_NAME"

hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$APP_PATH" \
  -ov \
  -format UDZO \
  "$ROOT_DIR/$DMG_NAME"

echo "✅ DMG created successfully:"
ls -lh "$ROOT_DIR/$DMG_NAME"