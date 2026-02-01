#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv-build"
SPEC="$ROOT/packaging/stagepro.spec"

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip wheel setuptools

# Install runtime + build deps
pip install -r requirements.txt
pip install -r requirements-build.txt

# Clean old build outputs to avoid mixing onefile/onedir artifacts
rm -rf "$ROOT/build" "$ROOT/dist"

# --- Ensure the spec is not configured for onefile ---
# PyInstaller spec uses EXE(..., exclude_binaries=..., ...) and COLLECT(...) for onedir.
# Onefile specs typically have EXE(..., exclude_binaries=False, ...) and no COLLECT.
if grep -qE '^\s*COLLECT\s*\(' "$SPEC"; then
  echo "OK: Spec contains COLLECT() (onedir packaging expected)."
else
  echo "ERROR: $SPEC does not contain COLLECT()."
  echo "This usually means the spec is configured for onefile, which breaks AppImage packaging."
  echo "Fix stagepro.spec to use onedir (COLLECT) or regenerate the spec with --onedir."
  exit 1
fi

# Build using the spec (should produce dist/stagepro/ as a directory)
pyinstaller --clean --noconfirm "$SPEC"

# --- Validate output is onedir ---
OUT="$ROOT/dist/stagepro"
if [ ! -d "$OUT" ]; then
  echo "ERROR: Expected onedir output directory not found: $OUT"
  echo "Contents of $ROOT/dist:"
  ls -la "$ROOT/dist" || true
  exit 1
fi

if [ ! -f "$OUT/stagepro" ]; then
  echo "ERROR: Expected executable not found: $OUT/stagepro"
  echo "Contents of $OUT:"
  ls -la "$OUT" || true
  exit 1
fi

echo
echo "Built PyInstaller onedir bundle to: $OUT"
echo "  - executable: $OUT/stagepro"
