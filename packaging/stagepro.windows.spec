# packaging/stagepro.windows.spec
# Build with: pyinstaller packaging/stagepro.windows.spec --clean

import os
from pathlib import Path

SPEC_DIR = Path(globals().get("SPECPATH", os.getcwd())).resolve()
PROJECT_ROOT = SPEC_DIR.parent

a = Analysis(
    [str(PROJECT_ROOT / "stagepro.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],   # <-- do NOT collect all PySide6 binaries
    datas=[
        (str(PROJECT_ROOT / "themes"), "themes"),
        (str(PROJECT_ROOT / "assets"), "assets"),
        (str(PROJECT_ROOT / "stagepro_config.example.json"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Exclude Qt modules you very likely don't use
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
    ],
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
    upx=False,     # set True if you install UPX
    console=False,
    icon=str(PROJECT_ROOT / "assets" / "stagepro.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="StagePro",
)
