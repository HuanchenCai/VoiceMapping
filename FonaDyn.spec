# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FonaDyn GUI
# Build:  pyinstaller FonaDyn.spec

import sys
import os
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Locate Tcl/Tk DLLs and library dirs (needed on Windows when building in venv)
# ---------------------------------------------------------------------------
def _find_tcltk():
    """Return (binaries, datas) for Tcl/Tk, searching common conda/Python locations."""
    import sysconfig, glob

    candidates = []
    # Walk up from the venv's python to find the base Python prefix
    base = Path(sys.executable)
    for _ in range(4):
        base = base.parent
        candidates.append(base)

    # Also check CONDA_PREFIX or common locations
    conda = os.environ.get('CONDA_PREFIX') or os.path.expanduser('~/miniconda3')
    candidates += [Path(conda), Path(conda) / 'Library']

    binaries, datas = [], []
    for root in candidates:
        lib_bin = root / 'Library' / 'bin'
        for dll in ['tcl86t.dll', 'tk86t.dll', 'tcl86.dll', 'tk86.dll']:
            p = lib_bin / dll
            if p.exists():
                binaries.append((str(p), '.'))

        for name in ['tcl8.6', 'tk8.6']:
            for sub in [root / 'Library' / 'lib' / name,
                        root / 'lib' / name,
                        root / 'tcl' / name]:
                if sub.is_dir():
                    datas.append((str(sub), name))
                    break

        if binaries and len(datas) >= 2:
            break

    return binaries, datas

_tcltk_bins, _tcltk_datas = _find_tcltk()

a = Analysis(
    ['gui.py'],
    pathex=[str(Path('src').resolve())],
    binaries=_tcltk_bins,
    datas=[
        ('src', 'src'),
    ] + _tcltk_datas,
    hiddenimports=[
        'numpy', 'scipy', 'scipy.signal', 'scipy.fft',
        'pandas', 'soundfile',
        'analyzer', 'config', 'metrics', 'logger',
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude heavy/unneeded packages
    excludes=[
        'numba', 'llvmlite',
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'keras',
        'matplotlib', 'librosa',
        'IPython', 'jupyter', 'notebook',
        'sklearn', 'skimage',
        'cv2', 'PIL',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FonaDyn',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows: icon='assets/icon.ico',
    # Mac:     icon='assets/icon.icns',
)

# macOS: also wrap in .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='FonaDyn.app',
        icon=None,
        bundle_identifier='com.fonadyn.analyzer',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '1.0.0',
        },
    )
