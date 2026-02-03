# packaging/stagepro.windows.spec
# Build with: pyinstaller packaging/stagepro.windows.spec --clean

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Resolve paths robustly:
# PyInstaller sets SPECPATH to the directory containing this spec file.
SPEC_DIR = Path(globals().get("SPECPATH", os.getcwd())).resolve()
PROJECT_ROOT = SPEC_DIR.parent  # packaging/ -> repo root

# Let PyInstaller's PySide6 hooks do the heavy lifting.
# We just make sure plugins/dlls and our app data are present.
pyside6_bins = collect_dynamic_libs("PySide6")
pyside6_data = collect_data_files("PySide6")

a = Analysis(
    [str(PROJECT_ROOT / "stagepro.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=pyside6_bins,
    datas=(
        pyside6_data
        + [
            (str(PROJECT_ROOT / "themes"), "themes"),
            (str(PROJECT_ROOT / "assets"), "assets"),
            (str(PROJECT_ROOT / "stagepro_config.example.json"), "."),
        ]
    ),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StagePro",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(PROJECT_ROOT / "assets" / "stagepro.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,  # include this so anything PyInstaller marks as zipfiles is collected too
    a.datas,
    strip=False,
    upx=False,
    name="StagePro",
)
