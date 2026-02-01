# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

# IMPORTANT: run pyinstaller from the repo root so Path.cwd() is StagePro root
ROOT = Path.cwd().resolve()

entry_script = str(ROOT / "stagepro.py")

datas = [
    (str(ROOT / "themes"), "themes"),
    (str(ROOT / "stagepro_config.example.json"), "."),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "LICENSE.md"), "."),
    (str(ROOT / "CONTRIBUTORS.md"), "."),
]

a = Analysis(
    [entry_script],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.scripts.deploy_lib",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="stagepro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
