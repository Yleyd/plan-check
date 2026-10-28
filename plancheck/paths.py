"""路径与运行环境：便携模式 / 用户目录回退、缓存、单实例锁。"""
import os
import sys
import tempfile

APP_NAME = "PlanCheck"
APP_TITLE = "Plan check"
VERSION = "1.1.0"


def _app_dir():
    """exe（或源码根目录）所在位置。打包后 __file__ 指向临时解包目录，不能用。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _bundle_dir():
    """PyInstaller 单文件 exe 的临时解包目录；源码运行时就是源码根。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


APP_DIR = _app_dir()
# 内置素材在打包后位于 _MEIPASS/assets/default，不是 exe 旁边
DEFAULT_ASSETS = os.path.join(_bundle_dir(), "assets", "default")
# 用户自己放的素材（exe 同级 assets/user），换图时可以放这里
SIDE_ASSETS = os.path.join(APP_DIR, "assets")

# 程序图标：打包后在 _MEIPASS/assets 里，源码运行时在项目 assets 里
ICON_PNG = os.path.join(_bundle_dir(), "assets", "icon.png")
ICON_ICO = os.path.join(_bundle_dir(), "assets", "icon.ico")


def _writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


PORTABLE_DIR = os.path.join(APP_DIR, "data")
ROAMING_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)

if _writable(PORTABLE_DIR):
    DATA_DIR = PORTABLE_DIR
    PORTABLE = True
else:
    try:
        os.makedirs(ROAMING_DIR, exist_ok=True)
        _writable(ROAMING_DIR)
    except Exception:
        pass
    DATA_DIR = ROAMING_DIR
    PORTABLE = False

PLANS_DIR = os.path.join(DATA_DIR, "plans")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
USER_ASSETS = os.path.join(DATA_DIR, "assets", "user")
LOG_DIR = os.path.join(DATA_DIR, "logs")

CACHE_DIR = os.path.join(tempfile.gettempdir(), APP_NAME, "cache")
LOCK_PATH = os.path.join(DATA_DIR, ".lock")


def ensure_dirs():
    for path in (DATA_DIR, PLANS_DIR, BACKUP_DIR, USER_ASSETS, LOG_DIR, CACHE_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass


def data_location_note():
    """给设置页显示的一句话。"""
    if PORTABLE:
        return "便携模式：数据保存在程序目录（可随文件夹一起拷走）"
    return "程序目录不可写，数据已保存到用户目录（换到可写文件夹会自动回到便携模式）"


class InstanceLock(object):
    """同目录只允许一个实例。用独占创建的锁文件实现，进程退出自动失效。"""

    def __init__(self, path=LOCK_PATH):
        self.path = path
        self.fh = None

    def acquire(self):
        ensure_dirs()
        try:
            self.fh = open(self.path, "r+")
        except FileNotFoundError:
            try:
                self.fh = open(self.path, "w")
            except Exception:
                return True
        except Exception:
            return True
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except Exception:
            return False

    def release(self):
        if self.fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            self.fh.close()
        except Exception:
            pass
        self.fh = None
