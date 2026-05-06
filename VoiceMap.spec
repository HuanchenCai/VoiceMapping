# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for VoiceMap.

Build:
    pyinstaller --noconfirm --clean VoiceMap.spec

Output:
    dist/VoiceMap/VoiceMap.exe   (one-folder layout, faster startup
                                  than --onefile and easier to debug
                                  missing-binary issues)

Why one-folder instead of --onefile?
    --onefile bootstraps by extracting the bundle to %TEMP% on every
    launch; a 200 MB build means a 1-2 s pause + extra disk churn.
    one-folder ships dist/VoiceMap/ as a regular Windows app dir; the
    Inno Setup installer wraps that as a single .exe for the user.

Hidden imports / data-collect notes:
    - sv_ttk: ships a TCL theme file; --collect-data needed
    - matplotlib: defers a lot via importlib; collect-all keeps PyInstaller
      from missing backend pieces
    - tkinterdnd2: ships .tcl files alongside .py; collect-all
    - soundfile: bundles libsndfile via cffi; collect-all
    - numba: aggressive runtime JIT; hidden imports for numba.core.types
"""

block_cipher = None


a = Analysis(
    ['voicemap/cli.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle the i18n module's STRINGS as part of the package
        ('voicemap', 'voicemap'),
    ],
    hiddenimports=[
        'numba.core.types',
        'numba.core.cgutils',
        'voicemap.gui.modern_menu',
        'voicemap.gui.app',
        'voicemap.gui.dialogs',
        'voicemap.gui.widgets',
        'voicemap.gui.theme',
        'voicemap.csv_writer',
        'voicemap.metrics',
        'voicemap.metrics_registry',
        'voicemap.plotter',
        'voicemap.plot_overlay',
        'voicemap.excel_export',
        'voicemap.report',
        'voicemap.i18n',
        'voicemap.config',
        'voicemap.logger',
        'voicemap.analyzer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Drop dev-only deps to slim the bundle
        'pytest',
        'parselmouth',         # only used by tests/validate_params.py
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Pull in matplotlib / soundfile / sv_ttk / tkinterdnd2 data files.
# PyInstaller's collect_all handles the awkward bits (TCL theme files,
# libsndfile DLL, matplotlib mpl-data dir, etc.) without us hardcoding
# paths.
from PyInstaller.utils.hooks import collect_all
for pkg in ('matplotlib', 'sv_ttk', 'tkinterdnd2', 'soundfile'):
    try:
        datas, binaries, hiddenimports = collect_all(pkg)
        a.datas      += datas
        a.binaries   += binaries
        a.hiddenimports += hiddenimports
    except Exception as e:
        print(f"WARNING: collect_all({pkg!r}) failed: {e}")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceMap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX often flags AV; not worth the size win
    console=False,         # GUI app; suppress black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/voicemap.ico',   # add an icon when we have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VoiceMap',
)
