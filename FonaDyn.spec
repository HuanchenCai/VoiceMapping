# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FonaDyn GUI
# Build:  pyinstaller FonaDyn.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['gui.py'],
    pathex=[str(Path('src').resolve())],
    binaries=[],
    datas=[
        ('src', 'src'),
    ],
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
