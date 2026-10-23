"""磨砂页面容器：整页烘焙底图 + 玻璃卡片。

要点（踩过的坑，别改）：
1. 卡片容器必须是 tk.Frame —— tk.Label 作容器时里面的 Canvas/Entry/Text 不重绘。
2. 布局用签名短路，避免 winfo_reqheight 回环导致的整页重烘（闪烁）。
3. 不在 <Configure> 里嵌套 update_idletasks（会重入 Tk 事件循环直接崩）。
"""
import tkinter as tk

from .. import theme
from . import art


class Page(tk.Frame):
    def __init__(self, master, app, key, art_key, padx=28, pady=18, gap=14,
                 column=None):
        tk.Frame.__init__(self, master, bg=theme.BG, bd=0, highlightthickness=0)
        self.app = app
        self.key = key
        self.art_key = art_key
        self.padx = padx
        self.pady = pady
        self.gap = gap
        self.column = column          # 右侧插画栏宽度，None=自动
        self.cards = []
        self._photo = None
        self._art_item = None
        self._skin = None
        self._laying = False
        self._last_sig = None
        self._schedule_id = None

        self.cv = tk.Canvas(self, bg=theme.BG, highlightthickness=0, bd=0)
        self.cv.pack(side="left", fill="both", expand=True)
        self.sb = tk.Scrollbar(self, orient="vertical", command=self.cv.yview,
                               width=10, bg=theme.BG, troughcolor=theme.BG,
                               activebackground=theme.LINE, bd=0,
                               highlightthickness=0, relief="flat", elementborderwidth=0)
        self.cv.configure(yscrollcommand=self._on_scroll)
        self.cv.bind("<Configure>", self._on_conf)
        self.cv.bind("<Enter>", self._bind_wheel)
        self.cv.bind("<Leave>", self._unbind_wheel)

    # ---------------------------------------------------------- 卡片
    def clear(self):
        for rec in self.cards:
            # 先删 Canvas 上的 window item，再销毁控件。
            # 只 destroy 控件会留下指向已销毁控件的 item（残影 + 计数错乱）。
            if rec.get("item") is not None:
                try:
                    self.cv.delete(rec["item"])
                except Exception:
                    pass
                rec["item"] = None
            try:
                rec["card"].destroy()
            except Exception:
                pass
        self.cards = []
        self._last_sig = None

    def add_card(self, padx=None, pady=None, fill=False, radius=18,
                 alpha=0.60, tint=None, gap=None):
        padx = self.padx if padx is None else padx
        pady = self.pady if pady is None else pady
        card = tk.Frame(self.cv, bd=0, highlightthickness=0, bg=theme.GLASS)
        body = tk.Frame(card, bd=0, highlightthickness=0, bg=theme.GLASS)
        body.pack(fill="both", expand=True, padx=padx, pady=pady)
        rec = {
            "card": card, "body": body, "padx": padx, "pady": pady,
            "fill": fill, "radius": radius, "alpha": alpha, "tint": tint,
            "gap": self.gap if gap is None else gap, "rect": None,
            "item": None,
        }
        self.cards.append(rec)
        return rec

    # ---------------------------------------------------------- 布局
    def schedule(self, delay=70):
        if self._schedule_id is not None:
            try:
                self.after_cancel(self._schedule_id)
            except Exception:
                pass
        self._schedule_id = self.after(delay, self.layout)

    def _on_conf(self, event):
        self.schedule(90)

    def _col_width(self, W):
        if self.column is not None:
            return self.column
        if W >= 1240:
            return 320
        if W >= 1080:
            return 240
        return 0

    def layout(self):
        self._schedule_id = None
        if self._laying:
            return
        self._laying = True
        try:
            self._layout_inner()
        except Exception as exc:
            self.app.log("layout %s 失败: %s" % (self.key, exc))
            self.schedule(300)
        finally:
            self._laying = False

    def _layout_inner(self):
        cv = self.cv
        W = cv.winfo_width()
        H = cv.winfo_height()
        if W < 120 or H < 120:
            return
        # 量高之前必须先把 idle 任务处理完，否则刚 pack 进去的子控件
        # 还停在 1x1，量出来的 reqheight 是错的（任务行会整片不显示）。
        # layout() 由 after 调度、且有 _laying 重入锁，这里不会嵌套进 <Configure>。
        try:
            self.update_idletasks()
        except Exception:
            pass
        col = self._col_width(W)

        def measure(inner_w):
            """量每张卡需要的高度。宽度会影响换行，所以必须按实际宽度量。"""
            out = []
            for rec in self.cards:
                try:
                    need = rec["body"].winfo_reqheight()
                except Exception:
                    need = 60
                out.append(max(48, need + 2 * rec["pady"]))
            return out

        inner = W - 2 * self.padx - col
        if inner < 240:
            col = 0
            inner = max(240, W - 2 * self.padx)

        heights = measure(inner)
        n_fill = sum(1 for rec in self.cards if rec["fill"])
        gaps = sum(rec["gap"] for rec in self.cards[:-1]) if self.cards else 0
        top = 10
        fixed = sum(h for rec, h in zip(self.cards, heights) if not rec["fill"])
        need_sb = (fixed + gaps + top + 14) > H and n_fill == 0
        if need_sb:
            # 滚动条浮在右侧，不占布局宽度，这里只是留一点右边距
            inner = max(240, inner - 8)
            heights = measure(inner)

        rem = max(0, H - (fixed + gaps + top + 14))
        fill_h = max(150, int(rem / n_fill)) if n_fill else 0

        plan = []
        y = top
        for rec, hh in zip(self.cards, heights):
            if rec["fill"]:
                hh = fill_h
            plan.append((rec, y, hh))
            y += hh + rec["gap"]

        total = max(H, y - self.gap + 12) if self.cards else H
        self._content_h = total
        sig = (W, H, inner, col, tuple((p[1], p[2]) for p in plan), len(self.cards))
        if self._last_sig == sig:
            self._sync_scrollbar()
            return
        self._last_sig = sig

        # 1) 底图
        skin = art.page_art(self.art_key, W, H, dark=0.46)
        if col:
            skin = art.art_column(skin, self.art_key, W, H, col,
                                  dark=0.10, blur=1.0, fade=120)

        # 2) 投影 + 玻璃
        rects = [(self.padx, yy, self.padx + inner, yy + hh) for _, yy, hh in plan]
        if rects:
            skin = art.add_shadow(skin, rects, blur=16, alpha=110, dy=8, radius=18)
        for (rec, yy, hh) in plan:
            box = (self.padx, yy, self.padx + inner, yy + hh)
            skin = art.glass_panel(skin, box, radius=rec["radius"],
                                   alpha=rec["alpha"], tint=rec["tint"],
                                   border="#2A3A56")
            rec["rect"] = box

        # 3) 贴图
        try:
            self._photo = art.photo(skin)
        except Exception:
            return
        if self._art_item is None:
            self._art_item = cv.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            cv.itemconfigure(self._art_item, image=self._photo)
        cv.tag_lower(self._art_item)

        # 4) 摆卡片
        for (rec, yy, hh) in plan:
            if rec["item"] is None:
                rec["item"] = cv.create_window(self.padx, yy, anchor="nw",
                                               window=rec["card"], width=inner,
                                               height=hh)
            else:
                cv.coords(rec["item"], self.padx, yy)
                cv.itemconfigure(rec["item"], width=inner, height=hh)
        cv.configure(scrollregion=(0, 0, W, total))

        # 5) 取色 + 滚动条
        self._blend(skin)
        self._sync_scrollbar()

    def _sync_scrollbar(self):
        """内容超过视口才显示滚动条（浮在右侧，不占布局宽度）。"""
        try:
            need = self._content_h > self.cv.winfo_height() + 1
        except Exception:
            return
        if need:
            if not self.sb.winfo_ismapped():
                self.sb.place(relx=1.0, x=-10, y=8, anchor="ne",
                              relheight=1.0, height=-16)
        else:
            if self.sb.winfo_ismapped():
                self.sb.place_forget()
            try:
                self.cv.yview_moveto(0)
            except Exception:
                pass

    def _need_scroll(self):
        try:
            return self._content_h > self.cv.winfo_height()
        except Exception:
            return False

    _content_h = 0

    def _blend(self, skin):
        for rec in self.cards:
            box = rec["rect"]
            if not box:
                continue
            base = art.avg_of(skin, box)
            col = art.mix(base, theme.GLASS, 0.58)
            hexcol = "#%02X%02X%02X" % col
            try:
                if rec["card"].cget("bg") != hexcol:
                    rec["card"].configure(bg=hexcol)
            except Exception:
                pass
            self._walk(rec["card"], hexcol, rec["card"])

    def _walk(self, widget, color, root):
        for child in widget.winfo_children():
            if getattr(child, "_fixed", False):
                continue
            if getattr(child, "_keep_bg", False):
                continue
            try:
                child.configure(bg=color)
            except Exception:
                pass
            self._walk(child, color, root)

    # ---------------------------------------------------------- 滚动
    def _on_scroll(self, first, last):
        self.sb.set(first, last)

    def _bind_wheel(self, _e=None):
        self.cv.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _e=None):
        self.cv.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        if self.sb.winfo_ismapped():
            self.cv.yview_scroll(int(-event.delta / 120), "units")

    def show(self, value=True):
        for rec in self.cards:
            if rec["item"] is not None:
                self.cv.itemconfigure(rec["item"], state="normal" if value else "hidden")
        if self._art_item is not None:
            self.cv.itemconfigure(self._art_item, state="normal" if value else "hidden")
