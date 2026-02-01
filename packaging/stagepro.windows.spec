# packaging/stagepro.windows.spec
# Build with: pyinstaller packaging/stagepro.windows.spec --clean

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Let PyInstaller's PySide6 hooks do the heavy lifting.
# We just make sure plugins/dlls and our app data are present.

pyside6_bins = collect_dynamic_libs("PySide6")
pyside6_data = collect_data_files("PySide6")

a = Analysis(
    ["stagepro.py"],
    pathex=["."],
    binaries=pyside6_bins,
    datas=(
        pyside6_data
        + [
            ("themes", "themes"),
            ("assets", "assets"),
            ("stagepro_config.example.json", "."),
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
    icon="assets/stagepro.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StagePro",
)
