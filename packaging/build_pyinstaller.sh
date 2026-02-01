#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv-build
source .venv-build/bin/activate
pip install -U pip

# Install runtime + build deps
pip install -r requirements.txt
pip install -r requirements-build.txt

pyinstaller --clean --noconfirm packaging/stagepro.spec

echo
echo "Built to: $ROOT/dist/stagepro"