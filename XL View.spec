# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import PySide6

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('lcxl/palette.json','lcxl'), ('lcxl/assets/xl-view.ico','lcxl/assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt on this Windows build imports the OS ICU API (unversioned exports).
# PATH can contain Poppler's incompatible ICU with version-suffixed exports;
# never redistribute that unrelated library as an OS dependency.
a.binaries = [item for item in a.binaries
              if Path(item[0]).name.lower() not in ('icuuc.dll', 'icuin.dll', 'icudt78.dll')]
# Python 3.11.0 ships an older MSVC runtime than Qt 6.11. Use Qt's matching,
# backwards-compatible redistributables at the process DLL search root too.
qt_dir = Path(PySide6.__file__).parent
a.binaries = [(dest, str(qt_dir / Path(dest).name), kind)
              if Path(dest).name.lower() in ('vcruntime140.dll', 'vcruntime140_1.dll')
              else (dest, source, kind)
              for dest, source, kind in a.binaries]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XL View',
    icon='lcxl/assets/xl-view.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XL View',
)
