#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="${VENV:-$ROOT/.venv-build}"
SPEC="${SPEC:-$ROOT/packaging/stagepro.linux.spec}"

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip wheel setuptools

pip install -r requirements.txt
pip install -r requirements-build.txt

rm -rf "$ROOT/build" "$ROOT/dist"

if grep -qE '\bCOLLECT\s*\(' "$SPEC"; then
  echo "OK: Spec contains COLLECT() (onedir packaging expected)."
else
  echo "ERROR: $SPEC does not contain COLLECT()."
  echo "NOTE: Spec must include COLLECT(...) for onedir AppImage packaging."
  exit 1
fi


pyinstaller --clean --noconfirm "$SPEC"

OUT="$ROOT/dist/stagepro"
if [ ! -d "$OUT" ]; then
  echo "ERROR: Expected onedir output directory not found: $OUT"
  ls -la "$ROOT/dist" || true
  exit 1
fi

if [ ! -f "$OUT/stagepro" ]; then
  echo "ERROR: Expected executable not found: $OUT/stagepro"
  ls -la "$OUT" || true
  exit 1
fi

echo "Built PyInstaller onedir bundle to: $OUT"
