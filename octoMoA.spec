# -*- mode: python ; coding: utf-8 -*-

import os
_python_root = r'C:\Users\Jie\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none'
_ssl_dlls = [
    (os.path.join(_python_root, 'DLLs', 'libssl-3-x64.dll'), '.'),
    (os.path.join(_python_root, 'DLLs', 'libcrypto-3-x64.dll'), '.'),
]

a = Analysis(
    ['app\\desktop.py'],
    pathex=[os.path.dirname(os.path.abspath('app\\desktop.py'))],
    binaries=_ssl_dlls,
    datas=[('config.yaml', '.'), ('app/static', 'app/static')],
    hiddenimports=[
        'app', 'app.main', 'app.config', 'app.engine', 'app.routes',
        'app.db', 'app.db_config', 'app.admin_api', 'app.desktop_ui',
        'fastapi', 'uvicorn', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
        'httpx', 'yaml', 'aiosqlite',
        'pystray', 'PIL.Image', 'PIL.ImageDraw',
        'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui',
        'starlette',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook', 'ipykernel',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='octoMoA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='app\\icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='octoMoA',
)
