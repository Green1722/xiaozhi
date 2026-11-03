# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

font_paths = [
    os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'seguisym.ttf'),
    os.path.join(os.environ.get('SYSTEMROOT', 'C:\\Windows'), 'Fonts', 'seguisym.ttf'),
]

datas = []
for fp in font_paths:
    if os.path.exists(fp):
        datas.append((fp, '.'))
        break

a = Analysis(
    ['chat_recorder.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'serial',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        'PIL._tkinter_finder',
    ],
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
    [],
    exclude_binaries=True,
    name='小智AI对话面板',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='小智AI对话面板',
)
