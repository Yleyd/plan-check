"""设置页：整屏插画 + 居中玻璃卡。

要点（踩过的坑，别改）：
1. **按钮的悬停不能用 item 级 tag_bind**。旧实现在 `<Enter>` 回调里
   `cv.delete()` 再重建同一批 item，鼠标指针还在原处 → 新 item 又触发
   `<Enter>` → 无限重入，界面直接卡死。现在改成 widget 级 `<Enter>/<Leave>`
   （重画 item 不会改变控件几何，也就不会再次触发）。
2. 卡片容器必须是 tk.Frame（tk.Label 作容器时里面的 Canvas 不重绘）。
3. 玻璃卡是烘进底图的，Frame 的 bg 取该区域平均色，所以看起来是"透"的。
"""
import os
import tkinter as tk

from .. import paths, theme
from ..core.settings import PAGES
from . import art, widgets

CARD_W = 660


class HeroPage(tk.Frame):
    def __init__(self, master, app, art_key):
        tk.Frame.__init__(self, master, bg=theme.BG, bd=0, highlightthickness=0)
        self.app = app
        self.art_key = art_key
        self.cv = tk.Canvas(self, bg=theme.BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self._photo = None
        self._art_item = None
        self._box_item = None
        self._laying = False
        self._last_sig = None
        self._sched = None
        self._btns = []

        self.box = tk.Frame(self.cv, bd=0, highlightthickness=0, bg=theme.GLASS)
        self._build_content()

        self.cv.bind("<Configure>", self._on_conf)

    # ------------------------------------------------------------ 内容
    def _build_content(self):
        b = self.box
        s = self.app.scale
        widgets.label(b, "设置", 26, theme.TEXT, theme.GLASS, bold=True).pack(
            anchor="w", pady=(0, 4))
        widgets.label(b, "数据、背景与字体都在这里调整", 10, theme.MUTED, theme.GLASS).pack(
            anchor="w", pady=(0, 20))

        grid = tk.Frame(b, bg=theme.GLASS)
        grid.pack(anchor="w")
        items = [
            ("导入计划文件", self.app.do_import, "primary"),
            ("下载计划模板", self.app.do_template, "ghost"),
            ("换背景图", self._pick_art, "ghost"),
            ("字号与选项", self._pick_font, "ghost"),
        ]
        for i, (text, cmd, kind) in enumerate(items):
            btn = ScalePill(grid, text, cmd, kind=kind,
                            width=int(184 * s), height=int(46 * s),
                            bg=theme.GLASS, app=self.app)
            btn.grid(row=i // 2, column=i % 2, padx=(0, int(12 * s)),
                     pady=(0, int(12 * s)), sticky="w")
            self._btns.append(btn)

        tk.Frame(b, bg=theme.LINE_SOFT, height=1).pack(fill="x", pady=(10, 16))

        links = tk.Frame(b, bg=theme.GLASS)
        links.pack(anchor="w")
        for i, (text, cmd) in enumerate([
                ("导出进度报告", self.app.do_export),
                ("立即备份", self.app.do_backup),
                ("打开数据目录", self._open_dir),
                ("恢复默认背景", self._reset_art)]):
            btn = ScalePill(links, text, cmd, kind="link",
                            width=int(118 * s), height=int(34 * s),
                            bg=theme.GLASS, app=self.app, ratio=0.03)
            btn.grid(row=0, column=i, padx=(0, int(6 * s)), sticky="w")
            self._btns.append(btn)

        tk.Frame(b, bg=theme.GLASS, height=int(14 * s)).pack()
        widgets.label(b, "数据目录", 9, theme.MUTED, theme.GLASS).pack(anchor="w")
        widgets.label(b, paths.DATA_DIR, 10, theme.CYAN, theme.GLASS, bold=True).pack(
            anchor="w", pady=(2, 0))
        widgets.label(b, paths.data_location_note(), 9, theme.DIM, theme.GLASS).pack(
            anchor="w", pady=(2, 0))

    # ------------------------------------------------------------ 布局
    def _on_conf(self, _e=None):
        self.schedule(90)

    def schedule(self, delay=60):
        if self._sched is not None:
            try:
                self.after_cancel(self._sched)
            except Exception:
                pass
        self._sched = self.after(delay, self.layout)

    def build(self):
        self.schedule(20)

    def clear(self):
        """与 Page 接口保持一致。

        reload_plan() 会对所有已创建的页面调 clear()，而设置页是 HeroPage
        不是 Page，没有这个方法就会 AttributeError，导致导入计划后
        reload_plan 中途抛异常 —— 表现为「点了导入没反应，关掉重开才有」。
        设置页的内容是 _paint() 每次重画的，这里只需让布局失效、下次重排。
        """
        self._last_sig = None

    def layout(self):
        self._sched = None
        if self._laying:
            return
        self._laying = True
        try:
            self._layout_inner()
        except Exception as exc:
            self.app.log("settings 布局失败: %s" % exc)
        finally:
            self._laying = False

    def _layout_inner(self):
        cv = self.cv
        W, H = cv.winfo_width(), cv.winfo_height()
        if W < 200 or H < 160:
            return

        try:
            self.box.update_idletasks()
        except Exception:
            pass
        pad = int(34 * self.app.scale)
        ch = self.box.winfo_reqheight() + pad * 2
        cw = min(CARD_W + int(60 * (self.app.scale - 1.0)), W - 60)
        cw = max(420, cw)
        bx = (W - cw) // 2
        by = max(24, (H - ch) // 2)

        sig = (W, H, cw, ch, bx, by, self.app.scale)
        if self._last_sig == sig:
            return
        self._last_sig = sig

        skin = art.hero_image(self.art_key, W, H)
        skin = art.add_shadow(skin, [(bx, by, bx + cw, by + ch)],
                              blur=22, alpha=150, dy=10, radius=24)
        skin = art.glass_panel(skin, (bx, by, bx + cw, by + ch),
                               radius=24, alpha=0.52, tint=theme.GLASS,
                               border="#2A3A56")
        try:
            self._photo = art.photo(skin)
        except Exception:
            return

        if self._art_item is None:
            self._art_item = cv.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            cv.itemconfigure(self._art_item, image=self._photo)
        cv.tag_lower(self._art_item)

        if self._box_item is None:
            self._box_item = cv.create_window(bx + pad, by + pad, anchor="nw",
                                              window=self.box, width=cw - pad * 2)
        else:
            cv.coords(self._box_item, bx + pad, by + pad)
            cv.itemconfigure(self._box_item, width=cw - pad * 2)

        # 取卡片平均色，让 Frame 看起来是玻璃的一部分
        col = art.mix(art.avg_of(skin, (bx, by, bx + cw, by + ch)), theme.GLASS, 0.55)
        self._tint(self.box, "#%02X%02X%02X" % col)

    def _tint(self, widget, color):
        try:
            if widget.cget("bg") != color:
                widget.configure(bg=color)
        except Exception:
            pass
        for child in widget.winfo_children():
            if getattr(child, "_fixed", False):
                continue
            self._tint(child, color)

    # ------------------------------------------------------------ 动作
    def _pick_art(self):
        from .dialogs import ArtDialog
        ArtDialog(self.app)

    def _pick_font(self):
        from .dialogs import OptionsDialog
        OptionsDialog(self.app)

    def _reset_art(self):
        for page in PAGES:
            self.app.settings.set_art(page, {"today": "gen_night", "prog": "gen_ring",
                                             "cal": "gen_hat", "set": "gen_clash"}[page])
        self.app.settings.set("start_art", "gen_ring")
        self.app.apply_art_change()
        self.app.toast("背景已恢复默认")

    def _open_dir(self):
        paths.ensure_dirs()
        try:
            os.startfile(paths.DATA_DIR)
        except Exception:
            self.app.toast("打开失败：" + paths.DATA_DIR)


class ScalePill(tk.Canvas):
    """胶囊按钮：鼠标移上去整体轻微放大（画布尺寸预留，不影响布局）。"""

    def __init__(self, master, text, command=None, kind="ghost",
                 width=180, height=46, bg=theme.GLASS, app=None, ratio=0.045,
                 **kw):
        self._base_w, self._base_h = int(width), int(height)
        self._ratio = float(ratio)
        max_f = 1.0 + self._ratio
        cw = int(self._base_w * max_f) + 2
        chh = int(self._base_h * max_f) + 2
        tk.Canvas.__init__(self, master, width=cw, height=chh, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.app = app
        self._text = text
        self._cmd = command
        self._kind = kind
        self._font = (theme.FONT, max(8, int(round(10 * (app.scale if app else 1.0)))),
                      "normal")
        self._hover = False
        self._cw, self._ch = cw, chh
        self._fixed = True
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", self._conf)
        self.draw()

    def _conf(self, event):
        if event.width > 1 and event.height > 1:
            self._cw, self._ch = event.width, event.height
            self.draw()

    def _colors(self):
        if self._kind == "primary":
            fill = theme.ACCENT if self._hover else theme.mix_primary()
            return fill, "#FFFFFF", theme.CYAN
        if self._kind == "danger":
            return ("#4A222B" if self._hover else "#3A1B22"), theme.DANGER, theme.DANGER
        if self._kind == "link":
            return (("#16233A" if self._hover else "#0E1727"),
                    theme.TEXT if self._hover else theme.SUB, theme.LINE_SOFT)
        return ("#16233A" if self._hover else "#0E1727", theme.TEXT, theme.LINE)

    def draw(self):
        self.delete("all")
        fill, fg, outline = self._colors()
        f = 1.0 + (self._ratio if self._hover else 0.0)
        w = self._base_w * f
        h = self._base_h * f
        x0 = (self._cw - w) / 2.0
        y0 = (self._ch - h) / 2.0
        widgets.round_rect(self, x0 + 1, y0 + 1, x0 + w - 1, y0 + h - 1,
                           h / 2.0, fill=fill, outline=outline, width=1)
        self.create_text(self._cw / 2.0, self._ch / 2.0, text=self._text,
                         fill=fg, font=self._font)

    def _enter(self, _e=None):
        # 只改状态 + 重画 item；控件本身没有移动，不会再次触发 <Enter>，
        # 因此不存在旧实现那种 delete→create→<Enter> 的自激死循环。
        if not self._hover:
            self._hover = True
            self.draw()

    def _leave(self, _e=None):
        if self._hover:
            self._hover = False
            self.draw()

    def _click(self, _e=None):
        if self._cmd:
            self._cmd()
