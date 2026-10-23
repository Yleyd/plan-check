"""自绘控件：圆角进度条、发光勾选、胶囊按钮、卡片。"""
import tkinter as tk

from .. import theme


def round_points(x0, y0, x1, y1, r):
    r = max(0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    return [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]


def round_rect(cv, x0, y0, x1, y1, r, **kw):
    return cv.create_polygon(round_points(x0, y0, x1, y1, r), smooth=True, **kw)


class Bar(tk.Canvas):
    """圆角进度条，支持渐变两端发光。"""

    def __init__(self, master, width=220, height=10, bg=theme.GLASS,
                 fg=theme.ACCENT, track=None, radius=None, **kw):
        tk.Canvas.__init__(self, master, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, **kw)
        self._cw = width
        self._ch = height
        self._fg = fg
        self._track = track or theme.mix_track()
        self._radius = radius if radius is not None else height / 2.0
        self._pct = 0.0
        self._fixed = True
        self.bind("<Configure>", self._on_conf)

    def _on_conf(self, event):
        if event.width > 1 and event.height > 1:
            self._cw, self._ch = event.width, event.height
            self.draw()

    def set(self, pct, fg=None):
        pct = max(0.0, min(1.0, float(pct or 0)))
        if fg:
            self._fg = fg
        if abs(pct - self._pct) < 1e-4 and fg is None:
            return
        self._pct = pct
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self._cw, self._ch
        if w < 4 or h < 2:
            return
        round_rect(self, 0, 0, w - 1, h - 1, self._radius,
                   fill=self._track, outline="")
        if self._pct <= 0:
            return
        fw = max(h, int((w - 1) * self._pct))
        round_rect(self, 0, 0, fw, h - 1, self._radius,
                   fill=self._fg, outline="")
        if fw > 6:
            # 末端高光
            self.create_oval(fw - h, 1, fw - 1, h - 2,
                             fill=theme.CYAN if self._fg != theme.CYAN else "#FFFFFF",
                             outline="")


class Check(tk.Canvas):
    """发光圆环勾选。"""

    def __init__(self, master, size=26, bg=theme.GLASS, on=False, **kw):
        tk.Canvas.__init__(self, master, width=size, height=size, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2", **kw)
        self._size = size
        self._on = bool(on)
        self._fixed = True
        self.draw()

    def set(self, on):
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.draw()

    def draw(self):
        self.delete("all")
        s = self._size
        pad = 3
        if self._on:
            # 外发光
            for i, alpha_col in ((2, "#1B3A5C"), (1, "#2C6EA8")):
                self.create_oval(pad - i, pad - i, s - pad + i, s - pad + i,
                                 outline=alpha_col, width=1)
            self.create_oval(pad, pad, s - pad, s - pad,
                             fill=theme.ACCENT, outline=theme.CYAN, width=1)
            m = s * 0.30
            self.create_line(m, s * 0.52, s * 0.45, s * 0.68, s - m,
                             s * 0.34, fill="#FFFFFF", width=max(2, int(s / 11)),
                             capstyle="round", joinstyle="round")
        else:
            self.create_oval(pad, pad, s - pad, s - pad,
                             fill=theme.GLASS_SOFT, outline=theme.LINE, width=1)


class Pill(tk.Canvas):
    """胶囊按钮（自绘，支持主/次/危险三种）。"""

    def __init__(self, master, text, command=None, width=120, height=34,
                 kind="ghost", bg=theme.GLASS, font=None, **kw):
        tk.Canvas.__init__(self, master, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2", **kw)
        self._text = text
        self._cmd = command
        self._cw = width
        self._ch = height
        self._kind = kind
        self._font = font or (theme.FONT, 10)
        self._hover = False
        self._fixed = True
        self._enabled = True
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
        if not self._enabled:
            return theme.LINE_SOFT, theme.DIM, theme.LINE_SOFT
        if self._kind == "primary":
            return (theme.ACCENT if self._hover else theme.mix_primary(),
                    "#FFFFFF", theme.CYAN)
        if self._kind == "danger":
            return ("#3A1B22" if not self._hover else "#4A222B",
                    theme.DANGER, theme.DANGER)
        return (theme.GLASS_SOFT if not self._hover else "#16233A",
                theme.TEXT, theme.LINE)

    def draw(self):
        self.delete("all")
        fill, fg, outline = self._colors()
        round_rect(self, 1, 1, self._cw - 2, self._ch - 2, self._ch / 2.0,
                   fill=fill, outline=outline, width=1)
        self.create_text(self._cw / 2.0, self._ch / 2.0, text=self._text,
                         fill=fg, font=self._font)

    def set_enabled(self, value):
        self._enabled = bool(value)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self.draw()

    def set_text(self, text):
        self._text = text
        self.draw()

    def _enter(self, _e):
        self._hover = True
        self.draw()

    def _leave(self, _e):
        self._hover = False
        self.draw()

    def _click(self, _e):
        if self._enabled and self._cmd:
            self._cmd()


def chip(master, text, color, bg=theme.GLASS, size=9, height=22):
    """科目小标签（圆角 + 半透明底）。"""
    import tkinter.font as tkfont
    font = tkfont.Font(family=theme.FONT, size=size)
    width = font.measure(text) + 20
    cv = tk.Canvas(master, width=width, height=height, bg=bg,
                   highlightthickness=0, bd=0)
    cv._fixed = True
    round_rect(cv, 0, 0, width - 1, height - 1, height / 2.0,
               fill=theme.mix_soft(color), outline="")
    cv.create_text(width / 2.0, height / 2.0, text=text, fill=color, font=font)
    return cv


def label(master, text="", size=10, fg=theme.TEXT, bg=theme.GLASS,
          bold=False, anchor="w", **kw):
    try:
        size = max(6, int(round(float(size))))
    except Exception:
        size = 10
    return tk.Label(master, text=text, bg=bg, fg=fg,
                    font=(theme.FONT, size, "bold" if bold else "normal"),
                    anchor=anchor, **kw)


def sep(master, bg=theme.GLASS, color=None):
    return tk.Frame(master, bg=color or theme.LINE_SOFT, height=1)
