"""打包入口（PyInstaller 用）。

直接双击运行时也能启动，方便调试。
"""
import os
import sys

if getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(sys.executable))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plancheck.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
