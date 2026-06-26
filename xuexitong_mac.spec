# -*- mode: python ; coding: utf-8 -*-

import os
from PyQt6.QtCore import QLibraryInfo

block_cipher = None

qt_plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        (os.path.join(qt_plugins, 'platforms'), 'platforms'),
        (os.path.join(qt_plugins, 'imageformats'), 'imageformats'),
        ('assets/katex', 'assets/katex'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtNetwork',
        'PyQt6.QtSvg',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebChannel',
        'requests',
        'bs4',
        'lxml',
        'openpyxl',
        'xlrd',
        'certifi',
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'cv2',
        'core.excel_parser',
        'qrcode',
        'qrcode.image.pil',
        'qrcode.image.svg', 'websocket',
        'core.rendering.katex_snapshot',
    ],
    excludes=[
        'tkinter',
        'pandas',
        'scipy',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='XHelper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=os.environ.get('ARCH', 'x86_64'),
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='XHelper.app',
    icon='assets/icon.icns',
    bundle_identifier='com.xuexitong.xhelper',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '0.12.4',
        'CFBundleDisplayName': 'XHelper',
        'CFBundleName': 'XHelper',
    },
)
