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

# 体积优化（1.0.4）：实测确认可去掉的大块头
#
# pypdfium2 / pypdfium2_raw：pdfium.dll 7.04 MB。只被 pdfplumber 的
#   display.py（页面渲染预览）引用，extract_text / extract_tables 都不用它。
#   屏蔽后实测文本提取正常、extract_tables 返回 []、无异常。
# _avif：Pillow 的 AVIF 解码器 7.53 MB。我们只读写 JPEG/PNG。
#   Pillow 是运行时按需 import 扩展的，不打包就不存在，JPEG/PNG 不受影响。
EXCLUDES = [
    "numpy", "pandas", "matplotlib", "scipy", "IPython", "notebook",
    "jupyter", "pytest", "setuptools", "pip", "wheel",
    "pygame", "pkg_resources", "jaraco", "tkinter.test", "test",
    "unittest", "pydoc_data", "lib2to3", "sqlite3",
    # ---- 体积优化 ----
    "pypdfium2", "pypdfium2_raw",
    "PIL._avif",
    "PIL.ImageQt", "PIL.ImageShow", "PIL.ImageTiff",
    "PIL._imagingcms", "PIL._imagingmath", "PIL._imagingmorph",
    "PIL.ImageGrab", "PIL.ImageEnhance",
    "xmlrpc", "http.server", "ftplib", "smtplib", "telnetlib",
    "multiprocessing", "concurrent", "asyncio",
    "pydoc", "doctest", "difflib", "optparse", "gettext",
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
    excludes=EXCLUDES,
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
