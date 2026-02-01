# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

# IMPORTANT: run pyinstaller from the repo root so Path.cwd() is StagePro root
ROOT = Path.cwd().resolve()
entry_script = str(ROOT / "stagepro.py")

datas = [
    ("themes", "themes"),
    ("assets", "assets"),
    ("stagepro_config.example.json", "."),
    ("README.md", "."),
    ("LICENSE.md", "."),
    ("CONTRIBUTORS.md", "."),
]

a = Analysis(
    [entry_script],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
    "PySide6.scripts.deploy_lib",
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

# Build the executable (no datas bundled here for onedir)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # IMPORTANT for onedir
    name="stagepro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

# Collect everything into dist/stagepro/
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="stagepro",
)
