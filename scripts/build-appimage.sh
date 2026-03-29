#!/usr/bin/env bash
set -euo pipefail

APP_NAME="QuillAI"
APP_ID="quillai"

BUILD_DIR="build"
APPDIR="$BUILD_DIR/AppDir"

echo "🧹 Cleaning previous build..."
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/usr"

echo "🔨 Building Nix package..."
nix build .#default

echo "📦 Copying Nix result into AppDir (dereferencing symlinks)..."
cp -rL result/* "$APPDIR/usr/"

echo "📁 Ensuring AppDir structure..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "🖼️ Creating desktop file + icon..."

# Create a fresh, writable desktop file
DESKTOP_DST="$APPDIR/usr/share/applications/${APP_ID}.desktop"
cat > "$DESKTOP_DST" <<EOL
[Desktop Entry]
Name=$APP_NAME
Exec=$APP_ID
Icon=$APP_ID
Type=Application
Categories=Development;IDE;TextEditor;
EOL

# Copy icon
if [ -f "images/quillai_logo_min.svg" ]; then
  cp images/quillai_logo_min.svg \
     "$APPDIR/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
fi

echo "⬇️ Downloading linuxdeploy + Qt plugin (if missing)..."

LINUXDEPLOY="linuxdeploy-x86_64.AppImage"
QT_PLUGIN="linuxdeploy-plugin-qt-x86_64.AppImage"

if [ ! -f "$LINUXDEPLOY" ]; then
  wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/$LINUXDEPLOY
  chmod +x $LINUXDEPLOY
fi

if [ ! -f "$QT_PLUGIN" ]; then
  wget -q https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/$QT_PLUGIN
  chmod +x $QT_PLUGIN
fi

echo "🔍 Locating qmake..."
if ! command -v qmake &> /dev/null; then
  echo "❌ qmake not found. Make sure qt6.qtbase is in your environment."
  exit 1
fi

export QMAKE="$(which qmake)"

echo "⚙️ Building AppImage..."
./$LINUXDEPLOY \
  --appdir "$APPDIR" \
  --desktop-file "$DESKTOP_DST" \
  --icon-file "$APPDIR/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg" \
  --plugin qt \
  --output appimage

echo "🏷️ Renaming output..."

APPIMAGE=$(ls *.AppImage | head -n 1)

if [ -n "${GITHUB_REF_NAME:-}" ]; then
  VERSION="$GITHUB_REF_NAME"
else
  VERSION="local"
fi

FINAL_NAME="${APP_NAME}-${VERSION}-x86_64.AppImage"
mv "$APPIMAGE" "$FINAL_NAME"

echo ""
echo "✅ Done!"
echo "📦 Output: $FINAL_NAME"
echo ""