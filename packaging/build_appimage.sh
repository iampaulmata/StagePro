#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 1) Build PyInstaller bundle
./packaging/build_pyinstaller.sh

# 2) Clean AppDir
rm -rf AppDir
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps

# 3) Copy onedir output into AppDir/usr/bin
cp -a dist/stagepro/* AppDir/usr/bin/

# 4) Desktop + icon
cp packaging/appimage/stagepro.desktop AppDir/
cp assets/stagepro.png AppDir/usr/share/icons/hicolor/256x256/apps/stagepro.png

# linuxdeploy expects the executable name referenced by Exec=stagepro
# Ensure it's executable
chmod +x AppDir/usr/bin/stagepro

# 5) Build AppImage (Qt plugin handles bundling Qt libs/plugins)
export VERSION="${VERSION:-0.1.0-beta.1}"

LINUXDEPLOY="$(ls packaging/tools/linuxdeploy*-x86_64.AppImage | head -n 1)"
QTPLUGIN="$(ls packaging/tools/linuxdeploy-plugin-qt*-x86_64.AppImage | head -n 1)"
APPIMAGETOOL="$(ls packaging/tools/appimagetool*-x86_64.AppImage | head -n 1)"

"$LINUXDEPLOY" --appdir AppDir \
  --plugin qt \
  --output appimage

echo
echo "Done. AppImage should be in: $ROOT (or current dir) and named like StagePro-*.AppImage"