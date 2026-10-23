# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件窗口程序，带图标与内置素材。"""
import os

block_cipher = None

APP_DIR = os.path.abspath(os.getcwd())
ASSETS = os.path.join(APP_DIR, "assets", "default")

datas = []
if os.path.isdir(ASSETS):
    for name in os.listdir(ASSETS):
        datas.append((os.path.join(ASSETS, name), os.path.join("assets", "default")))

# 运行时窗口图标（PhotoImage 需要真实文件；iconbitmap 用 ico 更清晰）
for _name in ("icon.png", "icon.ico"):
    _p = os.path.join(APP_DIR, "assets", _name)
    if os.path.exists(_p):
        datas.append((_p, "assets"))

hiddenimports = [
    "PIL._tkinter_finder",
    "openpyxl.cell._writer",
    "docx",
    "pdfplumber",
    "pdfminer",
]

a = Analysis(
    ["run.py"],
    pathex=[APP_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "IPython", "notebook",
        "jupyter", "pytest", "setuptools", "pip", "wheel",
        "pygame", "pkg_resources", "jaraco", "tkinter.test", "test",
        "unittest", "pydoc_data", "lib2to3", "sqlite3",
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
    name="PlanCheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(APP_DIR, "assets", "icon.ico"),
)
