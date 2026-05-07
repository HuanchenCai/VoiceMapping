# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for VoiceMap.

Build:
    pyinstaller --noconfirm --clean VoiceMap.spec

Output:
    dist/VoiceMap/VoiceMap.exe   (one-folder layout, faster startup
                                  than --onefile and easier to debug
                                  missing-binary issues)
"""

from PyInstaller.utils.hooks import collect_all
import os, sys, glob

# ── Collect data + binaries + hidden imports from packages that ship
# their own resource files / DLLs that PyInstaller can't auto-detect.
# Modern PyInstaller (>= 6.0) returns 2-tuples (src, dst_dir); we
# merge them into the lists handed to Analysis() at construction time
# rather than mutating a.datas / a.binaries afterwards (the post-init
# format is the 3-tuple TOC and direct concatenation breaks).
extra_datas = []
extra_binaries = []
extra_hidden = []
for pkg in ('matplotlib', 'sv_ttk', 'tkinterdnd2', 'soundfile'):
    try:
        datas, binaries, hiddenimports = collect_all(pkg)
        extra_datas.extend(datas)
        extra_binaries.extend(binaries)
        extra_hidden.extend(hiddenimports)
    except Exception as e:
        print(f"WARNING: collect_all({pkg!r}) failed: {e}")

# ── Conda-specific runtime DLLs not on the standard search path
# Conda places libffi (ffi-7.dll / ffi-8.dll) under
# <env>/Library/bin/ — Python's _ctypes module imports it indirectly,
# but PyInstaller's auto-detect doesn't crawl Library/bin (that's a
# conda layout convention, not a stdlib one). Same applies to OpenSSL,
# zlib, sqlite3 if they're conda-installed. We pull every .dll in
# Library/bin into the bundle root.
def _conda_runtime_dlls():
    out = []
    # sys.prefix in a conda env is .../envs/<name>; sibling Library/bin
    # holds the runtime DLLs.
    for cand in (
        os.path.join(sys.prefix, "Library", "bin"),
        os.path.join(os.path.dirname(sys.executable), "Library", "bin"),
    ):
        if os.path.isdir(cand):
            for dll in glob.glob(os.path.join(cand, "*.dll")):
                # Place at bundle root next to python310.dll so
                # LoadLibrary finds them via the EXE's own dir.
                out.append((dll, "."))
            break
    return out

extra_binaries.extend(_conda_runtime_dlls())


block_cipher = None


a = Analysis(
    ['voicemap/cli.py'],
    pathex=['.'],
    binaries=extra_binaries,
    datas=[
        # Bundle the i18n module's STRINGS as part of the package
        ('voicemap', 'voicemap'),
        *extra_datas,
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
        *extra_hidden,
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
    console=False,         # GUI app — no console window for end users
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
