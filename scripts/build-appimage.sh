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
rsync -a --copy-links \
    --exclude='share/applications/*.desktop' \
    --exclude='share/icons/hicolor/scalable/apps/*.svg' \
    result/ "$APPDIR/usr/"

echo "🔓 Fixing permissions (Nix store is read-only)..."
chmod -R u+w "$APPDIR"

echo "📁 Ensuring AppDir structure..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "🖼️ Creating desktop file + icon..."
DESKTOP_FILE="$APPDIR/usr/share/applications/${APP_ID}.desktop"
cat > "$DESKTOP_FILE" <<EOL
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

echo "⬇️ Downloading linuxdeploy (if needed)..."
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

echo "🔍 Locating qmake from Nix store..."
# The Nix build result has Qt in its closure — find qmake from there
QMAKE_PATH=$(find /nix/store -name "qmake" -type f 2>/dev/null | grep qt6 | head -n 1)

if [ -z "$QMAKE_PATH" ]; then
    # Fallback: try to get it via nix shell
    QMAKE_PATH=$(nix shell nixpkgs#qt6.qtbase -c which qmake 2>/dev/null || true)
fi

if [ -z "$QMAKE_PATH" ]; then
    echo "❌ qmake not found in Nix store. Trying nix build approach..."
    nix build nixpkgs#qt6.qtbase --out-link /tmp/qt6base
    QMAKE_PATH=$(find /tmp/qt6base -name "qmake" -type f | head -n 1)
fi

if [ -z "$QMAKE_PATH" ]; then
    echo "❌ Could not locate qmake. Aborting."
    exit 1
fi

echo "✅ Found qmake at: $QMAKE_PATH"
export QMAKE="$QMAKE_PATH"

# Also add Qt bin dir to PATH so linuxdeploy-plugin-qt can find other Qt tools
QT_BIN_DIR="$(dirname $QMAKE_PATH)"
export PATH="$QT_BIN_DIR:$PATH"

echo "⚙️ Building AppImage..."
./$LINUXDEPLOY \
    --appdir "$APPDIR" \
    --desktop-file "$DESKTOP_FILE" \
    --icon-file "$APPDIR/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg" \
    --plugin qt \
    --output appimage

echo "🏷️ Renaming output..."
APPIMAGE=$(ls *.AppImage | grep -v linuxdeploy | head -n 1)

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