# stagepro.windows.spec
# Build with: pyinstaller stagepro.windows.spec --clean

from PyInstaller.utils.hooks import collect_qt_plugins

qt_platform_plugins = collect_qt_plugins("PySide6", "platforms")
qt_image_plugins    = collect_qt_plugins("PySide6", "imageformats")

a = Analysis(
    ["stagepro.py"],
    pathex=["."],
    binaries=qt_platform_plugins + qt_image_plugins,
    datas=[
        ("themes", "themes"),
        ("assets", "assets"),
        ("stagepro_config.example.json", "."),
    ],
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
    upx=False,          # keep false in CI for fewer surprises
    console=False,
    icon="assets/stagepro.ico",   # we’ll generate this in CI
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StagePro",
)
