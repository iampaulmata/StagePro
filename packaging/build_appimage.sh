#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---------- config ----------
export VERSION="${VERSION:-0.1.0-beta.1}"
TOOLS_DIR="$ROOT/packaging/tools"

LINUXDEPLOY="$TOOLS_DIR/linuxdeploy-x86_64.AppImage"
QTPLUGIN="$TOOLS_DIR/linuxdeploy-plugin-qt-x86_64.AppImage"
APPIMAGETOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"

APPDIR="$ROOT/AppDir"
DIST_ONEDIR="$ROOT/dist/stagepro"

# ---------- build PyInstaller bundle ----------
./packaging/build_pyinstaller.sh

# ---------- require onedir output ----------
if [ ! -d "$DIST_ONEDIR" ]; then
  echo "ERROR: Expected PyInstaller onedir output at: $DIST_ONEDIR"
  echo "AppImage packaging should use PyInstaller --onedir so linuxdeploy can see dependencies."
  exit 1
fi

# ---------- validate tools ----------
if [ ! -d "$TOOLS_DIR" ]; then
  echo "ERROR: tools directory not found: $TOOLS_DIR"
  exit 1
fi

for f in "$LINUXDEPLOY" "$QTPLUGIN" "$APPIMAGETOOL"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: missing tool: $f"
    exit 1
  fi
  chmod +x "$f"
done

# Make appimagetool discoverable for linuxdeploy (some setups need this)
export PATH="$TOOLS_DIR:$PATH"
export APPIMAGETOOL="$APPIMAGETOOL"

# ---------- locate qmake for linuxdeploy-plugin-qt ----------
if command -v qmake6 >/dev/null 2>&1; then
  export QMAKE="$(command -v qmake6)"
else
  echo "ERROR: qmake6 not found. Install Qt tools:"
  echo "  sudo apt update && sudo apt install -y qmake6 qt6-base-dev-tools"
  exit 1
fi

# ---------- create AppDir ----------
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/plugins"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller onedir payload into AppDir/usr/bin
cp -a "$DIST_ONEDIR/"* "$APPDIR/usr/bin/"

# ---------- prune unwanted Qt modules/plugins anywhere in AppDir ----------
prune_patterns=(
  "*TextToSpeech*"
  "*texttospeech*"
  "*Location*"
  "*Positioning*"
  "*3D*"
  "*WebEngine*"
  "*Pdf*"
  "*SerialBus*"
  "*SerialPort*"
)

for pat in "${prune_patterns[@]}"; do
  find "$APPDIR" -type f -name "$pat" -print -delete 2>/dev/null || true
  find "$APPDIR" -type d -name "$pat" -print -exec rm -rf {} + 2>/dev/null || true
done

echo "Checking for unwanted Qt modules after prune (should be empty):"
BAD=$(find "$APPDIR" -iname '*texttospeech*' -o -iname '*TextToSpeech*' | head -n 5 || true)
if [ -n "$BAD" ]; then
  echo "ERROR: QtTextToSpeech still present after prune:"
  echo "$BAD"
  exit 1
fi

echo "Unexpected Qt modules still present in AppDir (should be empty):"
(ls "$APPDIR/usr/lib" | egrep -i 'TextToSpeech|Location|Positioning|3D|WebEngine|Serial' || true)
(find "$APPDIR/usr/plugins" -maxdepth 1 -type d | egrep -i 'texttospeech|geoservices|geometryloaders|webengine|serial' || true)

# Desktop + icon (linuxdeploy expects .desktop under usr/share/applications)
mkdir -p "$APPDIR/usr/share/applications"
cp packaging/appimage/stagepro.desktop "$APPDIR/usr/share/applications/stagepro.desktop"

mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp assets/stagepro.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/stagepro.png"


# Ensure the expected executable exists and is executable
if [ ! -f "$APPDIR/usr/bin/stagepro" ]; then
  echo "ERROR: expected $APPDIR/usr/bin/stagepro not found."
  echo "Contents of $APPDIR/usr/bin:"
  ls -la "$APPDIR/usr/bin" || true
  exit 1
fi
chmod +x "$APPDIR/usr/bin/stagepro"

# ---------- PySide6 Qt runtime whitelist ----------
# We copy only the Qt libraries and plugin dirs StagePro likely needs.
# This prevents linuxdeploy-plugin-qt from trying to deploy Qt3D/Location/WebEngine, etc.
PY_PYSIDE_DIR="$(python3 -c 'import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).resolve().parent)')"
QT_LIB_DIR="$PY_PYSIDE_DIR/Qt/lib"
QT_PLUGINS_DIR="$PY_PYSIDE_DIR/Qt/plugins"

if [ ! -d "$QT_LIB_DIR" ] || [ ! -d "$QT_PLUGINS_DIR" ]; then
  echo "ERROR: Could not find PySide6 Qt runtime directories."
  echo "Expected:"
  echo "  $QT_LIB_DIR"
  echo "  $QT_PLUGINS_DIR"
  exit 1
fi

echo "PySide6 dir: $PY_PYSIDE_DIR"
echo "Qt lib dir:  $QT_LIB_DIR"
echo "Qt plugins:  $QT_PLUGINS_DIR"

# ---- Qt libs whitelist (adjust if you later add features) ----
QT_LIBS=(
  "libQt6Core.so"
  "libQt6Gui.so"
  "libQt6Widgets.so"
  "libQt6Network.so"
  "libQt6DBus.so"
  "libQt6Svg.so"
  "libQt6XcbQpa.so"
)

for lib in "${QT_LIBS[@]}"; do
  # copy all versioned symlinks/so files matching the base name
  if compgen -G "$QT_LIB_DIR/$lib*" > /dev/null; then
    cp -av "$QT_LIB_DIR/$lib"* "$APPDIR/usr/lib/"
  else
    # Some are optional (e.g., Svg, DBus). Don’t fail hard unless it’s core.
    case "$lib" in
      libQt6Core.so|libQt6Gui.so|libQt6Widgets.so)
        echo "ERROR: required Qt library not found: $QT_LIB_DIR/$lib*"
        exit 1
        ;;
      *)
        echo "WARN: optional Qt library not found: $QT_LIB_DIR/$lib*"
        ;;
    esac
  fi
done

# ---- Qt plugin dirs whitelist ----
QT_PLUGIN_DIRS=(
  "platforms"
  "imageformats"
  "styles"
  "xcbglintegrations"
)

for d in "${QT_PLUGIN_DIRS[@]}"; do
  if [ -d "$QT_PLUGINS_DIR/$d" ]; then
    mkdir -p "$APPDIR/usr/plugins/$d"
    cp -av "$QT_PLUGINS_DIR/$d/"* "$APPDIR/usr/plugins/$d/"
  else
    # platforms is required for any GUI app
    if [ "$d" = "platforms" ]; then
      echo "ERROR: required Qt plugins dir not found: $QT_PLUGINS_DIR/$d"
      exit 1
    fi
    echo "WARN: optional Qt plugins dir not found: $QT_PLUGINS_DIR/$d"
  fi
done

# Sanity: confirm we did not accidentally include large optional plugin families
rm -rf "$APPDIR/usr/plugins/geoservices" "$APPDIR/usr/plugins/geometryloaders" "$APPDIR/usr/plugins/webengine"* 2>/dev/null || true
rm -f  "$APPDIR/usr/lib/libQt63D"* "$APPDIR/usr/lib/libQt6Location"* "$APPDIR/usr/lib/libQt6Positioning"* "$APPDIR/usr/lib/libQt6WebEngine"* "$APPDIR/usr/lib/libQt6Pdf"* 2>/dev/null || true

echo
echo "Qt libs in AppDir (sample):"
ls "$APPDIR/usr/lib" | grep -E '^libQt6' | head -n 30 || true
echo
echo "Qt plugins in AppDir:"
find "$APPDIR/usr/plugins" -maxdepth 2 -type d -print

# ---------- build AppImage ----------
# Run with a sanitized environment so host Qt tools don't accidentally load AppDir Qt libs.
export DEBUG=1
env -u LD_LIBRARY_PATH -u QT_PLUGIN_PATH -u QML2_IMPORT_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH \
  QMAKE="$QMAKE" DEBUG="$DEBUG" \
  "$LINUXDEPLOY" --appdir "$APPDIR" --plugin qt --output appimage

echo
echo "Done."
echo "Look for the AppImage in: $ROOT"
echo "  ls -lh *.AppImage"
