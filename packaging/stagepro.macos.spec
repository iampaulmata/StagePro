# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None

# PyInstaller defines SPECPATH as the directory containing the spec file
SPEC_DIR = Path(globals().get("SPECPATH", os.getcwd())).resolve()
PROJECT_ROOT = SPEC_DIR.parent  # packaging/ -> repo root

# (Optional) keep the debug for one run, then remove
print("SPEC DEBUG cwd =", os.getcwd())
print("SPEC DEBUG SPECPATH =", SPEC_DIR)
print("SPEC DEBUG PROJECT_ROOT =", PROJECT_ROOT)

datas = [
    (str(PROJECT_ROOT / "themes"), "themes"),
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "stagepro_config.example.json"), "."),
    (str(PROJECT_ROOT / "README.md"), "."),
    (str(PROJECT_ROOT / "LICENSE.md"), "."),
    (str(PROJECT_ROOT / "CONTRIBUTORS.md"), "."),
]

a = Analysis(
    [str(PROJECT_ROOT / "stagepro.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtTextToSpeech",
        "PySide6.QtLocation",
        "PySide6.QtPositioning",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtSerialPort",
        "PySide6.QtSerialBus",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StagePro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

app = BUNDLE(
    exe,
    name="StagePro.app",
    icon=None,
)

coll = COLLECT(
    app,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="StagePro",
)
