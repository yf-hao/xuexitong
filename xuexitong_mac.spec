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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='XuexitongManager',
    debug=False,
    strip=False,
    upx=False,               # mac 必关
    console=False,           # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,    # 改为False以生成单一文件
    target_arch=os.environ.get('ARCH', 'x86_64'),
)

app = BUNDLE(
    exe,
    name='XuexitongManager.app',
    icon='assets/icon.icns',  # macOS 图标
    bundle_identifier='com.hao.xuexitong',
    info_plist={
        'NSHighResolutionCapable': 'True',
        'LSBackgroundOnly': 'False',
        'CFBundleDisplayName': 'XuexitongManager',
        'CFBundleName': 'XuexitongManager',
    },
)
