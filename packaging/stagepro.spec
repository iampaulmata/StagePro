cat > packaging/stagepro.spec <<'EOF'
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("PySide6")

datas = []
# Include your project-shipped data files (adjust paths if your themes live elsewhere)
# If your themes directory is inside stagepro/ or assets/, add it here.
# Example: datas += [("stagepro/themes", "stagepro/themes")]
datas += [("stagepro_config.example.json", ".")]
datas += [("README.md", ".")]
datas += [("LICENSE", ".")]
datas += [("CONTRIBUTORS", ".")]

a = Analysis(
    ["stagepro.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
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
    console=False,   # no console window
)

EOF
