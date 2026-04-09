# -*- mode: python ; coding: utf-8 -*-

from PyQt6.QtCore import QLibraryInfo
import os

block_cipher = None

qt_plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(qt_plugins, 'platforms'), 'platforms'),
        (os.path.join(qt_plugins, 'imageformats'), 'imageformats'),
        ('assets/katex', 'assets/katex'),
    ],
    hiddenimports=[
        'PyQt6.QtNetwork',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.QtSvg',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebChannel',
        'bs4',
        'requests',
        'lxml',
        'xlrd',
        'openpyxl',
        'certifi',
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
    ],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'tkinter',
    ],
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
    name='XuexitongManager',
    debug=False,
    strip=False,
    upx=False,              # ← 关键
    console=False,
    argv_emulation=True,    # ← 关键
    target_arch='x86_64',   # ← 明确架构
)

app = BUNDLE(
    exe,
    name='XuexitongManager.app',
    bundle_identifier='com.xuexitong.manager',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.0.0',
    },
)
