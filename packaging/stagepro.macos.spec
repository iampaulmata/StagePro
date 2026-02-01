# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

datas = [
    ("themes", "themes"),
    ("assets", "assets"),
    ("stagepro_config.example.json", "."),
    ("README.md", "."),
    ("LICENSE.md", "."),
    ("CONTRIBUTORS.md", "."),
]

a = Analysis(
    ["stagepro.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # keep the same trims as Linux where applicable
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
    console=False,   # windowed app
)

app = BUNDLE(
    exe,
    name="StagePro.app",
    icon=None,       # add .icns later
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
