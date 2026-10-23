"""Plan check 入口。

用法：
    python -m plancheck           正常启动
    python -m plancheck --nosplash  跳过启动动画
    python -m plancheck --selftest  无窗口自检
    python -m plancheck --smoke     开窗 6 秒后自动退出
"""
import os
import sys
import traceback


def _log(message):
    try:
        from . import paths
        paths.ensure_dirs()
        with open(os.path.join(paths.LOG_DIR, "app.log"), "a", encoding="utf-8") as fh:
            import datetime as dt
            fh.write("[%s] %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _enable_dpi():
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def build(root, app_cls):
    from .core import model
    from .core.settings import Settings
    from .ui import art
    from .ui.dialogs import auto_backup

    settings = Settings()
    library = model.Library()
    auto_backup(library)

    win = settings.win()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(int(win.get("w") or 1280), sw - 60)
    h = min(int(win.get("h") or 840), sh - 80)
    w = max(1100, w)
    h = max(700, h)
    x = win.get("x", -1)
    y = win.get("y", -1)
    if not isinstance(x, int) or x < 0 or x + w > sw:
        x = (sw - w) // 2
    if not isinstance(y, int) or y < 0 or y + h > sh:
        y = max(0, (sh - h) // 2 - 20)
    root.geometry("%dx%d+%d+%d" % (w, h, x, y))
    root.minsize(1100, 700)
    root.title("Plan check")
    root.configure(bg="#070B18")

    app = app_cls(root, settings=settings, library=library, log=_log)
    app.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: _on_close(root, app))
    return app


def _on_close(root, app):
    try:
        app.close()
    except Exception:
        pass
    # 取消所有待执行的 after 回调，否则 destroy 后回调仍触发
    # 会报 AttributeError: 'NoneType' object has no attribute 'remove'
    try:
        for aid in root.tk.call("after", "info"):
            try:
                root.after_cancel(aid)
            except Exception:
                pass
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass


def _set_icon(root, tk):
    """窗口与任务栏图标：先试 ico，再用 png 兜底。"""
    from . import paths
    ico = getattr(paths, "ICON_ICO", "")
    if ico and os.path.exists(ico):
        for kwargs in ({"default": ico}, {}):
            try:
                root.iconbitmap(**kwargs)
                break
            except Exception:
                continue
    png = getattr(paths, "ICON_PNG", "")
    if png and os.path.exists(png):
        try:
            image = tk.PhotoImage(file=png)
            root.iconphoto(True, image)
            root._pc_icon = image  # 必须留引用，否则图片被回收后图标变白
        except Exception:
            pass


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    _enable_dpi()

    from . import paths
    paths.ensure_dirs()

    if "--selftest" in argv:
        from .selftest import run
        return run()

    # 单实例：双击多次不要起多个 38MB 进程互相抢（之前 InstanceLock 写好了却没被调用）。
    lock = None
    if "--allow-multi" not in argv:
        try:
            lock = paths.InstanceLock()
            if not lock.acquire():
                _log("已有实例在运行，本次启动退出")
                return 0
        except Exception:
            lock = None

    import tkinter as tk
    root = tk.Tk()

    # 关闭窗口时 Tk 会先销毁解释器再跑残留的 after 回调，
    # 于是 tkinter 自己在 deletecommand 里抛 AttributeError（_tclCommands 已是 None）。
    # 这个异常纯粹是退出期噪声，不该弹给用户，这里静默掉；其它异常照常写日志。
    def _report(exc, value, tb):
        text = str(value)
        if isinstance(value, AttributeError) and "_tclCommands" in text:
            return
        if isinstance(value, tk.TclError) and "invalid command name" in text:
            return
        _log("回调异常：\n" + "".join(
            __import__("traceback").format_exception(exc, value, tb)))

    root.report_callback_exception = _report
    root.withdraw()
    _set_icon(root, tk)

    from .ui.app import App

    try:
        app = build(root, App)
    except Exception:
        _log("启动失败：\n" + traceback.format_exc())
        raise

    def show_main():
        # 关键：绝不能用「先 alpha=0 再靠 after 链拉回来」的写法。
        # 那条链一旦没跑起来（无控制台的 pythonw / exe 上实测会稳定不跑），
        # 窗口就永久停在 alpha=0：任务栏有图标、能点，但整个窗口全透明。
        # 所以只降到 0.88（肉眼几乎无差别），且一定有兜底把它拉回 1.0。
        try:
            root.attributes("-alpha", 0.88)
        except Exception:
            pass
        try:
            root.deiconify()
            root.lift()
        except Exception:
            pass
        try:
            root.update_idletasks()
            root.after(10, lambda: _fade_in(root, 5))
        except Exception:
            pass
        # 硬兜底：不管上面发生什么，0.8 秒后一定把窗口拉成完全不透明
        try:
            root.after(800, lambda: _force_visible(root))
        except Exception:
            pass

    from .core.settings import Settings
    if "--nosplash" in argv or not Settings().get("show_splash", True):
        root.deiconify()
        _force_visible(root)
    else:
        from .ui.splash import Splash
        art_key = Settings().get("start_art", "gen_ring")
        Splash(root, tk, show_main, art_key=art_key)

    # 硬兜底：无论启动画面走没走完，1.5 秒后主窗必须是可见且不透明的
    try:
        root.after(1500, lambda: _force_visible(root))
    except Exception:
        pass

    if "--smoke" in argv:
        root.after(6000, lambda: _on_close(root, app))
    try:
        root.mainloop()
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass
    return 0


def _force_visible(root):
    """把主窗强制设为完全不透明且可见。任何异常都吞掉，绝不往外抛。"""
    try:
        root.attributes("-alpha", 1.0)
    except Exception:
        pass
    try:
        if root.state() == "withdrawn":
            root.deiconify()
    except Exception:
        pass


def _fade_in(root, step=5):
    """从 0.88 轻微淡入到 1.0。

    每一步失败都必须先把 alpha 设回 1.0 再退出 —— 之前的写法是 except: return，
    链一断窗口就永远停在半透明/全透明，这是"只有任务栏图标"的直接原因。
    """
    if step <= 0:
        _force_visible(root)
        return
    try:
        root.attributes("-alpha", 1.0 - step * 0.024)
    except Exception:
        _force_visible(root)
        return
    try:
        root.after(16, lambda: _fade_in(root, step - 1))
    except Exception:
        _force_visible(root)


if __name__ == "__main__":
    sys.exit(main())
