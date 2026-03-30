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
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/plugins"
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

if [ -f "images/quillai_logo_min.svg" ]; then
    cp images/quillai_logo_min.svg \
        "$APPDIR/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
fi

# ── Copy Qt libraries from Nix closure ───────────────────────────────────────
# linuxdeploy-plugin-qt can't detect Qt in Python wrappers, so we copy
# Qt libs directly from the Nix store closure of our package.
echo "🔗 Copying Qt libraries from Nix closure..."

# Get the full closure — every Nix store path our package depends on
CLOSURE=$(nix-store -qR result 2>/dev/null || nix path-info -r ".#default" 2>/dev/null || true)

if [ -z "$CLOSURE" ]; then
    echo "⚠️  Could not read closure, falling back to store search..."
    CLOSURE=$(find /nix/store -maxdepth 1 -name '*qt6*' -o -name '*pyqt6*' -o -name '*PyQt6*' 2>/dev/null || true)
fi

# Copy Qt shared libraries and plugins
echo "$CLOSURE" | tr ' ' '\n' | grep -iE 'qt6|pyqt' | sort -u | while read qt_path; do
    [ -d "$qt_path" ] || continue

    # Shared libraries
    if [ -d "$qt_path/lib" ]; then
        find "$qt_path/lib" \( -name 'libQt6*.so*' -o -name 'libpython3*.so*' \) 2>/dev/null | \
        while read lib; do
            cp -Pn "$lib" "$APPDIR/usr/lib/" 2>/dev/null || true
        done
    fi

    # Qt plugins (platforms, xcb, wayland, imageformats, etc.)
    for plugin_dir in \
        "$qt_path/plugins" \
        "$qt_path/lib/qt6/plugins" \
        "$qt_path"/*/*/plugins; do
        [ -d "$plugin_dir" ] && \
            rsync -a --copy-links "$plugin_dir/" "$APPDIR/usr/plugins/" 2>/dev/null || true
    done
done

LIB_COUNT=$(ls "$APPDIR/usr/lib/"libQt6*.so* 2>/dev/null | wc -l || echo 0)
echo "   Qt libs bundled: $LIB_COUNT"

# ── AppRun wrapper ────────────────────────────────────────────────────────────
echo "📝 Creating AppRun..."
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"

export QT_PLUGIN_PATH="$HERE/usr/plugins${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$HERE/usr/share/quillai${PYTHONPATH:+:$PYTHONPATH}"

exec "$HERE/usr/bin/quillai" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# ── Download linuxdeploy (base only — no Qt plugin needed) ───────────────────
echo "⬇️ Downloading linuxdeploy (if needed)..."
LINUXDEPLOY="linuxdeploy-x86_64.AppImage"

if [ ! -f "$LINUXDEPLOY" ]; then
    wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/$LINUXDEPLOY
    chmod +x "$LINUXDEPLOY"
fi

# ── Build AppImage ────────────────────────────────────────────────────────────
echo "⚙️ Building AppImage..."
APPIMAGE_EXTRACT_AND_RUN=1 ./"$LINUXDEPLOY" \
    --appdir "$APPDIR" \
    --desktop-file "$DESKTOP_FILE" \
    --icon-file "$APPDIR/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg" \
    --output appimage

# ── Rename output ─────────────────────────────────────────────────────────────
echo "🏷️ Renaming output..."
APPIMAGE=$(ls ./*.AppImage | grep -v linuxdeploy | head -n 1)

VERSION="${GITHUB_REF_NAME:-local}"
FINAL_NAME="${APP_NAME}-${VERSION}-x86_64.AppImage"
mv "$APPIMAGE" "$FINAL_NAME"

echo ""
echo "✅ Done!"
echo "📦 Output: $FINAL_NAME ($(du -h "$FINAL_NAME" | cut -f1))"
echo ""