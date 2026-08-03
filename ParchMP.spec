# -*- mode: python ; coding: utf-8 -*-
import glob
import os

from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets')]
binaries = [(path, '.') for path in glob.glob(os.path.join('lib', '*'))
            if path.endswith(('.so', '.pyd', '.dll'))]
hiddenimports = [
    'scipy.signal', 'scipy.fft', 'scipy.signal.windows', 'numpy',
    'mutagen', 'mutagen.mp3', 'mutagen.flac', 'mutagen.id3', 'mutagen.mp4',
    'mutagen.oggvorbis', 'mutagen.oggopus', 'mutagen.oggflac', 'mutagen.wave',
    'mutagen.aiff', 'mutagen.asf', 'mutagen.aac', 'mutagen.monkeysaudio',
    'mutagen.musepack', 'mutagen.wavpack', 'mutagen.trueaudio', 'mutagen.dsf',
    'sqlite3', 'zipfile',
    'app.native', 'app.library', 'app.analysis', 'app.features',
    'app.filterquery', 'app.lyrics', 'app.ui.icons',
]
tmp_ret = collect_all('scipy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PySide2', 'PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ParchMP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
