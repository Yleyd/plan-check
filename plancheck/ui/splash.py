"""启动动画：原图铺满 + 底部柔和压暗 + 页脚进度条。

要点（踩过的坑，别改）：
1. 整屏只有**一个** Canvas，底图、进度条、文字全部画在它上面。
   以前进度条是独立的 tk.Canvas / tk.Label，它们的 bg 是硬编码纯色，
   压在渐变上会露出一条色块接缝（用户看到的那条横线），所以全部改成
   Canvas item，画在同一张底图上，物理上不可能有接缝。
2. 底部不再渐变到纯色（那样人物下半身被吃掉，看起来"图片不完整"），
   改成半透明柔和压暗，图片始终完整可见。
"""
import time
import tkinter as tk

from .. import theme
from . import art

W, H = 960, 552


class Splash(tk.Toplevel):
    def __init__(self, root, tkmod, on_done, art_key="gen_ring"):
        tk.Toplevel.__init__(self, root)
        self.root = root
        self.on_done = on_done
        self.art_key = art_key
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=theme.BG)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.geometry("%dx%d+%d+%d" % (W, H, (sw - W) // 2, (sh - H) // 2 - 30))
        self.attributes("-topmost", True)

        self.steps = ["载入插画", "校验数据目录", "生成底图", "准备页面"]
        self.progress = 0.0
        self.target = 0.0
        self.done_work = False
        self._photo = None
        self._closing = False
        # 必须在这里记开始时间：_tick 16ms 后就跑，等 _start_work 赋值会
        # 把 elapsed 算成 "time.time() - 0" 这个巨大值，兜底逻辑立刻推到 100%。
        self._start = time.time()

        self.cv = tk.Canvas(self, width=W, height=H, bg=theme.BG,
                            highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self._build_bg()
        self._build_overlay()

        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.update()
        self._start_work()
        self._tick_id = self.after(16, self._tick)

    # ---------------------------------------------------------- 底图
    def _build_bg(self):
        Image, ImageDraw, ImageFilter = art.pil()[0], art.pil()[1], art.pil()[2]
        im = art.cover_fit(art.load_art(self.art_key), W, H, fx=0.5, fy=0.46)

        # 顶部压暗：只为标题可读，强度随距离衰减
        top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(top)
        limit = int(H * 0.34)
        for y in range(limit):
            a = int(120 * (1.0 - y / float(limit)) ** 1.5)
            td.line([(0, y), (W, y)], fill=(0, 0, 0, a))
        im = im.convert("RGBA")
        im.alpha_composite(top)

        # 底部：不再整条压暗（整条压暗看起来像"图片被切断"），
        # 只在进度条与文字所在的中下方加一个柔和椭圆压暗，左右两侧的图完整可见。
        bot = Image.new("L", (W, H), 0)
        bd = ImageDraw.Draw(bot)
        bd.ellipse([-W * 0.10, H * 0.66, W * 1.10, H * 1.34], fill=205)
        bot = bot.filter(ImageFilter.GaussianBlur(max(28, H / 16.0)))
        shade = Image.new("RGBA", (W, H), (2, 4, 10, 255))
        shade.putalpha(bot)
        im.alpha_composite(shade)

        # 最底部再压一点，让窗口下沿有收口，但保留图（最多 55%）
        bot2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd2 = ImageDraw.Draw(bot2)
        tail = int(H * 0.86)
        for y in range(tail, H):
            t = (y - tail) / float(H - tail)
            bd2.line([(0, y), (W, y)], fill=(0, 0, 0, int(120 * (t ** 1.6))))
        im.alpha_composite(bot2)

        # 极轻的暗角，让中心更亮
        vig = Image.new("L", (W, H), 0)
        vd = ImageDraw.Draw(vig)
        vd.ellipse([-W * 0.18, -H * 0.26, W * 1.18, H * 1.26], fill=255)
        vig = vig.filter(ImageFilter.GaussianBlur(max(50, W / 12.0)))
        dark = Image.new("RGBA", (W, H), (4, 7, 14, 255))
        im = Image.composite(im, Image.alpha_composite(im, dark), vig)

        # 边框：只用极暗的一圈收口。原来 1px 亮色 (120,160,230) 在深色图上
        # 就是一条贯穿全宽的亮线（用户看到的"下面出现横线"），改为暗色。
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, 0, W - 1, H - 1], outline=(30, 44, 72, 255))
        # 顶部一条 1px 高光，替代原来的整圈亮边
        draw.line([(1, 1), (W - 2, 1)], fill=(70, 96, 150, 255))

        rgb = im.convert("RGB")

        # ---- 文字（PIL 画，字重和阴影可控）----
        from PIL import ImageFont

        def font(size, bold=False):
            for name in (("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "msyhbd.ttc")):
                try:
                    return ImageFont.truetype(name, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        # 字色自适应：只看标题实际覆盖的区域
        lum = art.luma(rgb, (52, 60, 700, 200))
        if lum < 128:
            title_fg, sub_fg, kick_fg = (255, 255, 255), (214, 226, 244), (127, 231, 255)
            shadow = (0, 0, 0, 165)
        else:
            title_fg, sub_fg, kick_fg = (10, 16, 30), (34, 46, 66), (8, 62, 120)
            shadow = (255, 255, 255, 180)

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((52, 58), "P L A N   C H E C K", font=font(13, True), fill=kick_fg + (255,))
        ld.text((52, 82), "Plan check", font=font(40, True), fill=title_fg + (255,))
        ld.text((54, 144), "计划 · 打卡 · 进度，一个软件管完", font=font(15),
                fill=sub_fg + (255,))
        ld.text((W - 22, H - 14), "v1.0", font=font(11), fill=sub_fg + (190,), anchor="rs")

        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        for off in (1, 2):
            sd.text((52 + off, 58 + off), "P L A N   C H E C K", font=font(13, True),
                    fill=shadow)
            sd.text((52 + off, 82 + off), "Plan check", font=font(40, True), fill=shadow)
            sd.text((54 + off, 144 + off), "计划 · 打卡 · 进度，一个软件管完",
                    font=font(15), fill=shadow)

        base = rgb.convert("RGBA")
        base.alpha_composite(sh)
        base.alpha_composite(layer)
        self._photo = art.photo(base.convert("RGB"))
        self._img_id = self.cv.create_image(0, 0, anchor="nw", image=self._photo)

    # ---------------------------------------------------------- 进度条
    def _build_overlay(self):
        """进度条与说明文字，全部是 Canvas item（没有控件，就没有接缝）。"""
        from .widgets import round_points

        self._bw, self._bh = 520, 10
        bx = (W - self._bw) // 2
        by = H - 62
        self._bx, self._by = bx, by
        r = self._bh / 2.0

        self._track_id = self.cv.create_polygon(
            round_points(bx, by, bx + self._bw, by + self._bh, r),
            smooth=True, fill="#1B2438", outline="")

        self._fill_id = self.cv.create_polygon(
            round_points(bx, by, bx + self._bh, by + self._bh, r),
            smooth=True, fill=theme.ACCENT, outline="", state="hidden")
        self._tip_id = self.cv.create_oval(bx, by, bx + self._bh, by + self._bh,
                                           fill=theme.CYAN, outline="", state="hidden")

        self._msg_id = self.cv.create_text(
            bx, by + 26, anchor="w", text=self.steps[0],
            fill=theme.SUB, font=(theme.FONT, 9))
        self._pct_id = self.cv.create_text(
            bx + self._bw, by + 26, anchor="e", text="0%",
            fill=theme.CYAN, font=(theme.FONT, 9, "bold"))

    def _draw_bar(self):
        from .widgets import round_points

        bx, by = self._bx, self._by
        bw, bh = self._bw, self._bh
        r = bh / 2.0
        p = max(0.0, min(1.0, self.progress))
        if p <= 0.001:
            self.cv.itemconfigure(self._fill_id, state="hidden")
            self.cv.itemconfigure(self._tip_id, state="hidden")
            return
        fw = max(bh, int(bw * p))
        self.cv.coords(self._fill_id, *round_points(bx, by, bx + fw, by + bh, r))
        self.cv.itemconfigure(self._fill_id, state="normal")
        self.cv.coords(self._tip_id, bx + fw - bh, by, bx + fw, by + bh)
        self.cv.itemconfigure(self._tip_id, state="normal")

    # ---------------------------------------------------------- 进度
    def _start_work(self):
        import threading

        def work():
            try:
                art.load_art(self.art_key)
                self.target = 0.34
                art.page_art(self.art_key, 320, 180, dark=0.46)
                self.target = 0.62
                from .. import paths
                paths.ensure_dirs()
                self.target = 0.86
                self.target = 1.0
            except Exception:
                self.target = 1.0
            self.done_work = True

        threading.Thread(target=work, daemon=True).start()

    def _tick(self):
        if self._closing:
            return
        self.progress += (self.target - self.progress) * 0.18
        if self.progress > 0.995:
            self.progress = 1.0
        self._draw_bar()
        pct = int(round(self.progress * 100))
        self.cv.itemconfigure(self._pct_id, text="%d%%" % pct)
        idx = min(len(self.steps) - 1, int(self.progress * len(self.steps)))
        self.cv.itemconfigure(self._msg_id, text=self.steps[idx])

        elapsed = time.time() - self._start
        if self.done_work and self.progress >= 0.999 and elapsed >= 1.25:
            self._finish()
            return
        # 兜底：exe 冷启动解包慢时，超过 3.2 秒直接放行，绝不卡在 99%
        if elapsed > 3.2:
            self.progress = 1.0
            self._draw_bar()
            self.cv.itemconfigure(self._pct_id, text="100%")
            self.cv.itemconfigure(self._msg_id, text=self.steps[-1])
            self._finish()
            return
        self._tick_id = self.after(16, self._tick)

    def _finish(self):
        self._closing = True
        self._cancel_after()
        self._fade()

    def _cancel_after(self):
        for attr in ("_tick_id", "_fade_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)

    def destroy(self):
        # 关键：窗口销毁前必须撤掉还没跑的 after 回调，
        # 否则 Tcl 会在已销毁的解释器上执行 "...._tick" 报 invalid command name。
        self._cancel_after()
        try:
            tk.Toplevel.destroy(self)
        except Exception:
            pass

    def _fade(self, step=10):
        if step <= 0:
            try:
                self.destroy()
            except Exception:
                pass
            if self.on_done:
                self.on_done()
            return
        try:
            self.attributes("-alpha", step / 10.0)
        except Exception:
            pass
        try:
            self._fade_id = self.after(16, lambda: self._fade(step - 1))
        except Exception:
            # 排不上后续帧就立即结束，绝不能把主窗永远留在不显示状态
            try:
                self.destroy()
            except Exception:
                pass
            if self.on_done:
                self.on_done()
