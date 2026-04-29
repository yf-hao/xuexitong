# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
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
    upx=True,
    console=False,
    icon='assets/icon.png',  # Linux 图标 (也可以用 .png)
)
