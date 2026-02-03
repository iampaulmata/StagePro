#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---------- config ----------
export VERSION="${VERSION:-0.1.0-dev}"
TOOLS_DIR="$ROOT/packaging/tools"

LINUXDEPLOY="$TOOLS_DIR/linuxdeploy-x86_64.AppImage"
QTPLUGIN="$TOOLS_DIR/linuxdeploy-plugin-qt-x86_64.AppImage"
APPIMAGETOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"

APPDIR="$ROOT/AppDir"
DIST_ONEDIR="$ROOT/dist/stagepro"

echo "PWD before pyinstaller: $(pwd)"

# ---------- build PyInstaller bundle ----------
./packaging/build_pyinstaller.sh

# ---------- require onedir output ----------
if [ ! -d "$DIST_ONEDIR" ]; then
  echo "ERROR: Expected PyInstaller onedir output at: $DIST_ONEDIR"
  exit 1
fi

# ---------- validate tools ----------
for f in "$LINUXDEPLOY" "$QTPLUGIN" "$APPIMAGETOOL"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: missing tool: $f"
    exit 1
  fi
  chmod +x "$f"
done

export PATH="$TOOLS_DIR:$PATH"
export APPIMAGETOOL="$APPIMAGETOOL"

# ---------- locate qmake for linuxdeploy-plugin-qt ----------
if command -v qmake6 >/dev/null 2>&1; then
  export QMAKE="$(command -v qmake6)"
else
  echo "ERROR: qmake6 not found. Install:"
  echo "  sudo apt update && sudo apt install -y qmake6 qt6-base-dev-tools"
  exit 1
fi

# ---------- create AppDir ----------
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$APPDIR/usr/plugins"
mkdir -p "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$DIST_ONEDIR/"* "$APPDIR/usr/bin/"

# Desktop + icon
cp packaging/stagepro.desktop "$APPDIR/usr/share/applications/stagepro.desktop"
cp assets/stagepro.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/stagepro.png"

# Ensure expected executable exists
if [ ! -f "$APPDIR/usr/bin/stagepro" ]; then
  echo "ERROR: expected $APPDIR/usr/bin/stagepro not found."
  ls -la "$APPDIR/usr/bin" || true
  exit 1
fi
chmod +x "$APPDIR/usr/bin/stagepro"

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

# ---------- whitelist PySide6 Qt runtime ----------
PYTHON="$ROOT/.venv-build/bin/python"
PY_PYSIDE_DIR="$("$PYTHON" -c 'import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).resolve().parent)')"
QT_LIB_DIR="$PY_PYSIDE_DIR/Qt/lib"
QT_PLUGINS_DIR="$PY_PYSIDE_DIR/Qt/plugins"

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
  if compgen -G "$QT_LIB_DIR/$lib*" > /dev/null; then
    cp -av "$QT_LIB_DIR/$lib"* "$APPDIR/usr/lib/"
  else
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

# ICU libs (avoid system ICU version mismatch like libicui18n.so.73)
for icu in libicui18n.so libicuuc.so libicudata.so; do
  if compgen -G "$QT_LIB_DIR/$icu*" > /dev/null; then
    cp -av "$QT_LIB_DIR/$icu"* "$APPDIR/usr/lib/"
  else
    echo "WARN: ICU lib not found in wheel: $QT_LIB_DIR/$icu*"
  fi
done


QT_PLUGIN_DIRS=( "platforms" "imageformats" "styles" "xcbglintegrations" )
for d in "${QT_PLUGIN_DIRS[@]}"; do
  if [ -d "$QT_PLUGINS_DIR/$d" ]; then
    mkdir -p "$APPDIR/usr/plugins/$d"
    cp -av "$QT_PLUGINS_DIR/$d/"* "$APPDIR/usr/plugins/$d/"
  else
    if [ "$d" = "platforms" ]; then
      echo "ERROR: required Qt plugins dir not found: $QT_PLUGINS_DIR/$d"
      exit 1
    fi
    echo "WARN: optional Qt plugins dir not found: $QT_PLUGINS_DIR/$d"
  fi
done

rm -rf "$APPDIR/usr/plugins/geoservices" "$APPDIR/usr/plugins/geometryloaders" "$APPDIR/usr/plugins/webengine"* 2>/dev/null || true
rm -f  "$APPDIR/usr/lib/libQt63D"* "$APPDIR/usr/lib/libQt6Location"* "$APPDIR/usr/lib/libQt6Positioning"* "$APPDIR/usr/lib/libQt6WebEngine"* "$APPDIR/usr/lib/libQt6Pdf"* 2>/dev/null || true

# ---------- build AppImage ----------
export DEBUG=1
env -u LD_LIBRARY_PATH -u QT_PLUGIN_PATH -u QML2_IMPORT_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH \
  QMAKE="$QMAKE" DEBUG="$DEBUG" \
  "$LINUXDEPLOY" --appdir "$APPDIR" --plugin qt --output appimage

# ---------- normalize output name ----------
OUT="$(ls -1 ./*.AppImage | head -n 1)"
FINAL="StagePro-${VERSION}-x86_64.AppImage"
mv -f "$OUT" "$FINAL"
sha256sum "$FINAL" > "${FINAL}.sha256"

echo "Done: $FINAL"
