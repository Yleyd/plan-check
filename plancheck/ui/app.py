"""主窗口：头部 + 页签 + 四个页面。"""
import datetime as dt
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .. import paths, theme, template
from ..core import model
from ..core.settings import Settings
from . import art, widgets
from .page import Page

PAGE_DEFS = [
    ("today", "今日", "night"),
    ("prog", "进度", "ring"),
    ("cal", "日历", "hat"),
    ("set", "设置", "flame"),
]

WEEK_CN = "一二三四五六日"


class App(tk.Frame):
    def __init__(self, root, settings=None, library=None, log=None):
        tk.Frame.__init__(self, root, bg=theme.BG, bd=0, highlightthickness=0)
        self.root = root
        self.settings = settings or Settings()
        self.library = library or model.Library()
        self._log_fn = log
        self.scale = self.settings.scale()

        self.plan = self.library.load_plan()
        self.records = None
        if self.plan:
            self.records = model.Records.load(self.plan.id)

        self.cur_date = self._initial_date()
        self.pages = {}
        self._cur_page = None
        self._hd_photo = None
        self._hd_busy = False
        self._syncing = False
        self._closing = False

        # 用户自定义背景图要在任何一次 load_art 之前装进 art 模块
        self._sync_art()

        self._style()
        self._header()
        self._tabs()
        self._bind_keys()
        self.after(60, self.show_page, self._first_page())
        self.after(200, self.refresh_header)

    # ------------------------------------------------------------ 基础
    def log(self, message):
        if self._log_fn:
            self._log_fn(message)

    def f(self, size, bold=False):
        px = max(8, int(round(size * self.scale)))
        return (theme.FONT, px, "bold" if bold else "normal")

    def _initial_date(self):
        today = dt.date.today()
        if not self.plan:
            return today
        dates = self.plan.dates()
        if not dates:
            return today
        if dates[0] <= today <= dates[-1]:
            return today
        return dates[0] if today < dates[0] else dates[-1]

    def _first_page(self):
        return "today"

    def _slot_art_map(self):
        """{页面 key: 该页选中的内置图 key}，供 art.art_for_slot 使用。"""
        out = {"splash": self.settings.get("start_art", "gen_ring")}
        for key in ("today", "prog", "cal", "set"):
            out[key] = self.settings.art_of(key)
        return out

    def _sync_art(self):
        """把「用户选的内置图」和「用户自定义图」一起推给 art 模块。
        换图相关的一切都必须走这里，否则两个映射容易不同步。"""
        art.set_slot_art(self._slot_art_map())
        art.set_custom_map(self.settings.get("custom_art") or {})

    # ------------------------------------------------------------ 样式
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TNotebook", background=theme.BG, borderwidth=0,
                     tabmargins=(10, 8, 10, 0))
        st.configure("TNotebook.Tab", background="#0C1424", foreground=theme.MUTED,
                     padding=(24, 9), borderwidth=0,
                     bordercolor="#0C1424", lightcolor="#0C1424",
                     darkcolor="#0C1424")
        st.map("TNotebook.Tab",
               background=[("selected", theme.GLASS)],
               foreground=[("selected", theme.CYAN)],
               lightcolor=[("selected", theme.GLASS)],
               darkcolor=[("selected", theme.GLASS)],
               bordercolor=[("selected", theme.GLASS)])
        st.configure("Vertical.TScrollbar", background=theme.LINE, width=10,
                     troughcolor=theme.BG, bordercolor=theme.BG,
                     arrowcolor=theme.BG, lightcolor=theme.LINE,
                     darkcolor=theme.LINE, relief="flat", arrowsize=0)
        st.configure("Treeview", background=theme.GLASS_SOFT, fieldbackground=theme.GLASS_SOFT,
                     foreground=theme.TEXT, borderwidth=0, rowheight=int(26 * self.scale))
        st.configure("Treeview.Heading", background="#16233A", foreground=theme.SUB,
                     borderwidth=0, relief="flat")
        st.map("Treeview", background=[("selected", "#1E3A5F")],
               foreground=[("selected", theme.TEXT)])

    # ------------------------------------------------------------ 头部
    def _header(self):
        self.hd = tk.Canvas(self, height=int(112 * self.scale), bg=theme.BG,
                            highlightthickness=0, bd=0)
        self.hd.pack(side="top", fill="x")
        self.hd.bind("<Configure>", self._on_header_conf)

    def _on_header_conf(self, _e=None):
        if self._hd_busy:
            return
        self._hd_busy = True
        try:
            self._paint_header()
        except Exception as exc:
            self.log("header 失败: %s" % exc)
        finally:
            self._hd_busy = False

    def _paint_header(self):
        W = max(200, self.hd.winfo_width())
        H = max(60, self.hd.winfo_height())
        img = art.page_art(art.art_for_slot("today"), W, H, dark=0.55)
        img = art.glass_panel(img, (0, 0, W, H), radius=0, alpha=0.52,
                              tint=theme.GLASS, border=None)
        # 底部分隔线
        try:
            Image, ImageDraw = art.pil()[0], art.pil()[1]
            draw = ImageDraw.Draw(img)
            draw.line([(0, H - 1), (W, H - 1)], fill=theme.hex_rgb(theme.LINE), width=1)
        except Exception:
            pass
        try:
            self._hd_photo = art.photo(img)
        except Exception:
            return
        self.hd.delete("all")
        self.hd.create_image(0, 0, anchor="nw", image=self._hd_photo)
        s = self.scale

        # 纵向位置必须按「字体实际渲染高度」排，不能拍脑袋写死。
        # 21pt 在 150% DPI 下行高约 55px，标题放 y=26 就会占 26..81，
        # 副标题放 y=58 直接压上去（用户看到的重叠）。这里改成：
        # 标题 18..70，副标题 72..99，头部高 112，三段互不相交。
        title_y = int(18 * s)
        sub_y = int(72 * s)
        self.hd.create_text(int(30 * s), title_y, anchor="nw", text="Plan check",
                            fill=theme.TEXT, font=(theme.FONT, int(20 * s), "bold"))
        sub = self._header_sub()
        self.hd.create_text(int(31 * s), sub_y, anchor="nw", text=sub,
                            fill=theme.MUTED, font=(theme.FONT, int(10 * s)))

        # 右侧统计：数值 16..66，标签 70..97
        stats = self._header_stats()
        x = W - int(28 * s)
        for label_text, value, color in reversed(stats):
            self.hd.create_text(x, int(16 * s), anchor="ne", text=value,
                                fill=color, font=(theme.FONT, int(17 * s), "bold"))
            self.hd.create_text(x, int(70 * s), anchor="ne", text=label_text,
                                fill=theme.MUTED, font=(theme.FONT, int(9 * s)))
            x -= int(112 * s)

    def _header_sub(self):
        if not self.plan:
            return "还没有计划 · 去「设置」导入或新建"
        start = self.plan.start.strftime("%Y-%m-%d")
        end = self.plan.end.strftime("%Y-%m-%d")
        left = (self.plan.end - dt.date.today()).days
        tail = ("剩 %d 天" % left) if left >= 0 else ("已超期 %d 天" % -left)
        return "%s ｜ %s ~ %s ｜ %d 天 ｜ %s" % (self.plan.name, start, end,
                                                self.plan.total_days, tail)

    def _header_stats(self):
        if not self.plan or not self.records:
            return [("总进度", "—", theme.MUTED),
                    ("已完成", "—", theme.MUTED),
                    ("连续打卡", "—", theme.MUTED)]
        total = self.plan.total_tasks
        done = self.records.tasks_done(self.plan)
        pct = (100.0 * done / total) if total else 0.0
        run, best = self.records.streak(self.plan)
        return [("总进度", "%d%%" % int(round(pct)), theme.CYAN),
                ("已完成", "%d / %d" % (done, total), theme.TEXT),
                ("连续打卡", "%d 天" % run, theme.OK)]

    def refresh_header(self):
        self._on_header_conf()

    # ------------------------------------------------------------ 页签
    def _tabs(self):
        bar = tk.Frame(self, bg=theme.BG, bd=0, highlightthickness=0)
        bar.pack(side="top", fill="x", padx=int(24 * self.scale), pady=(6, 0))
        self.tab_btns = {}
        self._tab_marks = {}
        for key, name, _art_key in PAGE_DEFS:
            cv = tk.Canvas(bar, height=int(38 * self.scale), width=int(96 * self.scale),
                           bg=theme.BG, highlightthickness=0, bd=0, cursor="hand2")
            cv.pack(side="left", padx=(0, 6))
            cv.bind("<Button-1>", lambda _e, k=key: self.show_page(k))
            cv.bind("<Enter>", lambda _e, k=key: self._hover_tab(k, True))
            cv.bind("<Leave>", lambda _e, k=key: self._hover_tab(k, False))
            self.tab_btns[key] = cv
            self._tab_marks[key] = False
        self.body = tk.Frame(self, bg=theme.BG, bd=0, highlightthickness=0)
        self.body.pack(side="top", fill="both", expand=True)
        self._paint_tabs()

    def _hover_tab(self, key, value):
        if key == self._cur_page:
            return
        self._tab_hover = getattr(self, "_tab_hover", {})
        self._tab_hover[key] = value
        self._paint_tab(key)

    def _paint_tabs(self):
        for key in self.tab_btns:
            self._paint_tab(key)

    def _paint_tab(self, key):
        cv = self.tab_btns[key]
        cv.delete("all")
        W = max(60, cv.winfo_width() or int(96 * self.scale))
        H = max(24, cv.winfo_height() or int(38 * self.scale))
        active = (key == self._cur_page)
        hover = getattr(self, "_tab_hover", {}).get(key)
        name = dict((k, n) for k, n, _a in PAGE_DEFS)[key]
        if active:
            widgets.round_rect(cv, 1, 1, W - 2, H - 2, 10,
                               fill=theme.GLASS, outline=theme.LINE, width=1)
            fg = theme.CYAN
        elif hover:
            widgets.round_rect(cv, 1, 1, W - 2, H - 2, 10,
                               fill=theme.GLASS_SOFT, outline="")
            fg = theme.SUB
        else:
            fg = theme.MUTED
        cv.create_text(W / 2.0, H / 2.0, text=name, fill=fg,
                       font=self.f(10.5, bold=active))

    def show_page(self, key):
        if key not in dict((k, 1) for k, _n, _a in PAGE_DEFS):
            return
        if self._cur_page == key:
            return
        if self._cur_page and self._cur_page in self.pages:
            self.pages[self._cur_page].pack_forget()
        self._cur_page = key
        page = self._get_page(key)
        page.pack(fill="both", expand=True)
        page.schedule(20)
        self._paint_tabs()

    def _get_page(self, key):
        if key in self.pages:
            return self.pages[key]
        art_key = art.art_for_slot(key)
        if key == "set":
            from .hero import HeroPage
            page = HeroPage(self.body, self, art_key)
        else:
            page = Page(self.body, self, key, art_key,
                        padx=int(26 * self.scale), pady=int(16 * self.scale),
                        gap=int(12 * self.scale))
        self.pages[key] = page
        if key == "today":
            self.render_today()
        elif key == "prog":
            self.render_progress()
        elif key == "cal":
            self.render_calendar()
        elif key == "set":
            page.build()
        return page

    # ------------------------------------------------------------ 键盘
    def _bind_keys(self):
        self.root.bind("<Control-s>", lambda _e: self._save_note())
        self.root.bind("<Left>", lambda _e: self.shift_day(-1))
        self.root.bind("<Right>", lambda _e: self.shift_day(1))

    # ------------------------------------------------------------ 今日
    def render_today(self):
        page = self.pages.get("today")
        if page is None:
            return
        page.clear()
        if not self.plan:
            self._today_empty(page)
            page.layout()
            return

        # 日期行
        rec = page.add_card(pady=int(14 * self.scale))
        body = rec["body"]
        row = tk.Frame(body, bg=theme.GLASS)
        row.pack(fill="x")
        prev = widgets.Pill(row, "◀", lambda: self.shift_day(-1),
                            width=int(34 * self.scale), height=int(30 * self.scale))
        prev.pack(side="left")
        self.date_lbl = widgets.label(row, "", 17, theme.TEXT, theme.GLASS, bold=True)
        self.date_lbl.pack(side="left", padx=(14, 8))
        self.week_lbl = widgets.label(row, "", 11, theme.MUTED, theme.GLASS)
        self.week_lbl.pack(side="left")
        nxt = widgets.Pill(row, "▶", lambda: self.shift_day(1),
                           width=int(34 * self.scale), height=int(30 * self.scale))
        nxt.pack(side="left", padx=(14, 0))
        self.day_lbl = widgets.label(row, "", 10, theme.PURPLE, theme.GLASS)
        self.day_lbl.pack(side="right")

        self.theme_lbl = widgets.label(body, "", 10, theme.MUTED, theme.GLASS)
        self.theme_lbl.pack(fill="x", pady=(8, 0))

        # 任务卡
        rec2 = page.add_card(pady=int(14 * self.scale))
        body2 = rec2["body"]
        head = tk.Frame(body2, bg=theme.GLASS)
        head.pack(fill="x")
        widgets.label(head, "今日任务", 12, theme.TEXT, theme.GLASS, bold=True).pack(side="left")
        self.check_lbl = widgets.label(head, "", 10, theme.MUTED, theme.GLASS)
        self.check_lbl.pack(side="right")
        self.task_box = tk.Frame(body2, bg=theme.GLASS)
        self.task_box.pack(fill="both", expand=True, pady=(10, 0))

        # 备注卡（撑满）
        rec3 = page.add_card(pady=int(14 * self.scale), fill=True)
        body3 = rec3["body"]
        hb = tk.Frame(body3, bg=theme.GLASS)
        hb.pack(fill="x")
        widgets.label(hb, "当天备注", 11, theme.SUB, theme.GLASS, bold=True).pack(side="left")
        self.note_state = widgets.label(hb, "", 9, theme.OK, theme.GLASS)
        self.note_state.pack(side="right")
        well = tk.Frame(body3, bg=theme.GLASS_SOFT, highlightthickness=1,
                        highlightbackground=theme.LINE)
        well._fixed = True
        well.pack(fill="both", expand=True, pady=(8, 10))
        self.note = tk.Text(well, bg=theme.GLASS_SOFT, fg=theme.TEXT, bd=0,
                            highlightthickness=0, wrap="word", undo=True,
                            insertbackground=theme.CYAN,
                            font=self.f(10), padx=10, pady=8)
        self.note._fixed = True
        self.note.pack(fill="both", expand=True)

        foot = tk.Frame(body3, bg=theme.GLASS)
        foot.pack(fill="x")
        widgets.Pill(foot, "全部完成", self.mark_all, width=int(96 * self.scale),
                     height=int(30 * self.scale), kind="primary").pack(side="left")
        widgets.Pill(foot, "清空勾选", self.clear_all, width=int(96 * self.scale),
                     height=int(30 * self.scale)).pack(side="left", padx=(8, 0))
        widgets.Pill(foot, "保存备注", self._save_note, width=int(96 * self.scale),
                     height=int(30 * self.scale)).pack(side="left", padx=(8, 0))
        widgets.label(foot, "快捷键 ← → 换日期 · Ctrl+S 存备注", 9,
                      theme.DIM, theme.GLASS).pack(side="right")

        self._sync_today()
        page.layout()

    def _today_empty(self, page):
        rec = page.add_card(pady=int(30 * self.scale), fill=True)
        body = rec["body"]
        wrap = tk.Frame(body, bg=theme.GLASS)
        wrap.place(relx=0.5, rely=0.42, anchor="center")
        widgets.label(wrap, "还没有任何计划", 20, theme.TEXT, theme.GLASS,
                      bold=True, anchor="center").pack()
        widgets.label(wrap, "先导入一份计划，或者用内置示例体验一下", 11,
                      theme.MUTED, theme.GLASS, anchor="center").pack(pady=(10, 22))
        row = tk.Frame(wrap, bg=theme.GLASS)
        row.pack()
        widgets.Pill(row, "导入计划文件", self.do_import, width=int(132 * self.scale),
                     height=int(38 * self.scale), kind="primary").pack(side="left")
        widgets.Pill(row, "下载计划模板", self.do_template, width=int(132 * self.scale),
                     height=int(38 * self.scale)).pack(side="left", padx=(10, 0))
        row2 = tk.Frame(wrap, bg=theme.GLASS)
        row2.pack(pady=(10, 0))
        widgets.Pill(row2, "手动新建", self.do_manual, width=int(132 * self.scale),
                     height=int(38 * self.scale)).pack(side="left")
        widgets.Pill(row2, "用示例计划", self.do_sample, width=int(132 * self.scale),
                     height=int(38 * self.scale)).pack(side="left", padx=(10, 0))

    def _sync_today(self):
        if not self.plan or not self.records:
            return
        date_str = self.cur_date.strftime("%Y-%m-%d")
        day = self.plan.day_of(date_str)
        self.date_lbl.configure(text=self.cur_date.strftime("%m 月 %d 日"))
        self.week_lbl.configure(text="周" + WEEK_CN[self.cur_date.weekday()])
        try:
            idx = (self.cur_date - self.plan.start).days + 1
            total = self.plan.total_days
            self.day_lbl.configure(text="第 %d / %d 天" % (max(1, idx), total))
        except Exception:
            self.day_lbl.configure(text="")

        tasks = day.get("tasks") if day else []
        self.theme_lbl.configure(
            text=("" if not tasks else "共 %d 项任务 · 计划 %.1f 小时" % (
                len(tasks), sum(float(t.get("hours") or 0) for t in tasks))))

        for child in self.task_box.winfo_children():
            child.destroy()
        if not tasks:
            widgets.label(self.task_box, "这一天没有安排任务", 11, theme.MUTED,
                          theme.GLASS).pack(pady=18)
        else:
            colors = self._subject_colors()
            for i, task in enumerate(tasks):
                self._task_row(self.task_box, i, task, date_str, colors)

        done = self.records.done_count(date_str)
        self.check_lbl.configure(text="%d / %d 已完成" % (done, len(tasks)),
                                 fg=theme.OK if tasks and done == len(tasks) else theme.MUTED)
        self.note.delete("1.0", "end")
        self.note.insert("1.0", self.records.note_of(date_str))
        self.note_state.configure(text="")

    def _subject_colors(self):
        mapping = {}
        for i, subj in enumerate(self.plan.subject_list() if self.plan else []):
            mapping[subj] = theme.subject_color(i)
        return mapping

    def _task_row(self, parent, index, task, date_str, colors):
        row = tk.Frame(parent, bg=theme.GLASS, cursor="hand2")
        row.pack(fill="x", pady=(0, int(8 * self.scale)))
        subj = task.get("subject") or "未分类"
        color = colors.get(subj, theme.ACCENT)

        bar = tk.Canvas(row, width=4, height=int(34 * self.scale), bg=theme.GLASS,
                        highlightthickness=0, bd=0)
        bar._fixed = True
        bar.create_rectangle(0, 0, 4, int(34 * self.scale), fill=color, outline="")
        bar.pack(side="left", padx=(2, 10))

        done = self.records.is_done(date_str, task.get("id"))
        chk = widgets.Check(row, size=int(24 * self.scale), bg=theme.GLASS, on=done)
        chk.pack(side="left", padx=(0, 12))

        text_wrap = tk.Frame(row, bg=theme.GLASS)
        text_wrap.pack(side="left", fill="x", expand=True)
        title = task.get("text") or ""
        lbl = widgets.label(text_wrap, title, 11,
                            theme.MUTED if done else theme.TEXT, theme.GLASS)
        lbl.pack(anchor="w")
        meta = []
        if task.get("hours") is not None:
            meta.append(theme.hours_text(task.get("hours")))
        if task.get("star"):
            meta.append(theme.star_text(task.get("star")))
        if task.get("note"):
            meta.append(task.get("note"))
        if meta:
            widgets.label(text_wrap, "  ".join([m for m in meta if m]), 9,
                          theme.DIM, theme.GLASS).pack(anchor="w", pady=(2, 0))
        if done:
            try:
                lbl.configure(font=self.f(11))
            except Exception:
                pass

        def on_click(_e=None):
            new = self.records.toggle(date_str, task.get("id"))
            chk.set(new)
            lbl.configure(fg=theme.MUTED if new else theme.TEXT)
            self._after_toggle()

        for widget in (row, bar, chk, text_wrap, lbl):
            widget.bind("<Button-1>", on_click)
        row.bind("<Enter>", lambda _e: row.configure(bg=theme.GLASS_SOFT))
        row.bind("<Leave>", lambda _e: row.configure(bg=theme.GLASS))

    def _after_toggle(self):
        if not self.plan:
            return
        date_str = self.cur_date.strftime("%Y-%m-%d")
        tasks = self.plan.tasks_of(date_str)
        done = self.records.done_count(date_str)
        self.check_lbl.configure(text="%d / %d 已完成" % (done, len(tasks)),
                                 fg=theme.OK if tasks and done == len(tasks) else theme.MUTED)
        self.refresh_header()
        prog = self.pages.get("prog")
        if prog is not None:
            self.render_progress()

    def mark_all(self):
        if not self.plan or not self.records:
            return
        date_str = self.cur_date.strftime("%Y-%m-%d")
        tids = [t.get("id") for t in self.plan.tasks_of(date_str)]
        if not tids:
            return
        self.records.mark_all(date_str, tids, True)
        self._sync_today()
        self._after_toggle()

    def clear_all(self):
        if not self.plan or not self.records:
            return
        date_str = self.cur_date.strftime("%Y-%m-%d")
        self.records.mark_all(date_str, [], False)
        self._sync_today()
        self._after_toggle()

    def _save_note(self):
        if not self.records:
            return
        date_str = self.cur_date.strftime("%Y-%m-%d")
        self.records.set_note(date_str, self.note.get("1.0", "end").rstrip("\n"))
        try:
            self.note_state.configure(text="已保存")
            self.after(1600, lambda: self.note_state.configure(text=""))
        except Exception:
            pass

    def shift_day(self, delta):
        if not self.plan:
            return
        dates = self.plan.dates()
        if not dates:
            return
        new = self.cur_date + dt.timedelta(days=delta)
        if new < dates[0] or new > dates[-1]:
            return
        self.cur_date = new
        self._save_note()
        self._sync_today()
        self.refresh_header()

    # ------------------------------------------------------------ 进度
    def render_progress(self):
        page = self.pages.get("prog")
        if page is None:
            return
        page.clear()
        if not self.plan or not self.records:
            rec = page.add_card(fill=True)
            widgets.label(rec["body"], "还没有计划，导入后这里会显示进度", 12,
                          theme.MUTED, theme.GLASS).pack(pady=40)
            page.layout()
            return

        total = self.plan.total_tasks
        done = self.records.tasks_done(self.plan)
        hours_plan = self.plan.total_hours
        hours_done = self.records.hours_done(self.plan)
        run, best = self.records.streak(self.plan)
        pct = (done / float(total)) if total else 0.0

        # 总览
        rec = page.add_card(pady=int(16 * self.scale))
        b = rec["body"]
        top = tk.Frame(b, bg=theme.GLASS)
        top.pack(fill="x")
        widgets.label(top, "总进度", 12, theme.TEXT, theme.GLASS, bold=True).pack(side="left")
        self._pct_lbl = widgets.label(top, "%d%%" % int(round(pct * 100)), 20,
                                      theme.CYAN, theme.GLASS, bold=True)
        self._pct_lbl.pack(side="right")
        bar = widgets.Bar(b, width=800, height=int(12 * self.scale), bg=theme.GLASS,
                          fg=theme.ACCENT)
        bar.pack(fill="x", pady=(10, 10))
        bar.set(pct)
        info = tk.Frame(b, bg=theme.GLASS)
        info.pack(fill="x")
        for text in ("任务 %d / %d" % (done, total),
                     "时长 %.1f / %.1f h" % (hours_done, hours_plan),
                     "打卡 %d 天" % len([1 for d in self.plan.dates()
                                       if self.records.is_day_complete(
                                           self.plan, d.strftime("%Y-%m-%d"))]),
                     "连续 %d 天 · 最长 %d 天" % (run, best)):
            widgets.label(info, text, 10, theme.SUB, theme.GLASS).pack(side="left", padx=(0, 26))

        # 各科
        rec2 = page.add_card(pady=int(14 * self.scale))
        b2 = rec2["body"]
        widgets.label(b2, "各科目", 12, theme.TEXT, theme.GLASS, bold=True).pack(anchor="w")
        grid = tk.Frame(b2, bg=theme.GLASS)
        grid.pack(fill="x", pady=(8, 0))
        grid.grid_columnconfigure(0, weight=0, minsize=int(96 * self.scale))
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=0, minsize=int(150 * self.scale))
        stats = self.plan.subject_stats()
        colors = self._subject_colors()
        for r, (subj, row_data) in enumerate(stats.items()):
            color = colors.get(subj, theme.ACCENT)
            widgets.label(grid, subj, 10.5, theme.TEXT, theme.GLASS).grid(
                row=r, column=0, sticky="w", pady=2)
            done_h = self.records.hours_done(self.plan, subj)
            done_n = sum(1 for d, t in self.plan.iter_tasks()
                         if (t.get("subject") or "未分类") == subj
                         and self.records.is_done(d, t.get("id")))
            sbar = widgets.Bar(grid, width=300, height=int(9 * self.scale),
                               bg=theme.GLASS, fg=color)
            sbar.grid(row=r, column=1, sticky="ew", padx=12, pady=2)
            sbar.set(done_h / row_data["hours"] if row_data["hours"] else 0)
            widgets.label(grid, "%d/%d 项 · %.1f/%.1f h" % (
                done_n, row_data["tasks"], done_h, row_data["hours"]),
                9, theme.MUTED, theme.GLASS, anchor="e").grid(
                row=r, column=2, sticky="e", pady=2)

        # 每周
        rec3 = page.add_card(pady=int(14 * self.scale))
        b3 = rec3["body"]
        widgets.label(b3, "每周进度", 12, theme.TEXT, theme.GLASS, bold=True).pack(anchor="w")
        wgrid = tk.Frame(b3, bg=theme.GLASS)
        wgrid.pack(fill="x", pady=(8, 0))
        for c in (0, 1):
            wgrid.grid_columnconfigure(c, weight=1, uniform="wk")
        weeks = self.plan.week_stats()
        for i, wk in enumerate(sorted(weeks)):
            cell = tk.Frame(wgrid, bg=theme.GLASS)
            cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 16), pady=1)
            row = weeks[wk]
            done_days = 0
            for d in self.plan.dates():
                if model.week_index(self.plan.start, d) == wk and \
                        self.records.is_day_complete(self.plan, d.strftime("%Y-%m-%d")):
                    done_days += 1
            widgets.label(cell, "第 %d 周" % wk, 9.5, theme.SUB, theme.GLASS,
                          anchor="w").pack(side="left")
            wbar = widgets.Bar(cell, width=100, height=int(8 * self.scale),
                               bg=theme.GLASS, fg=theme.PURPLE)
            wbar.pack(side="left", fill="x", expand=True, padx=8)
            wbar.set(done_days / float(row["days"]) if row["days"] else 0)
            widgets.label(cell, "%d/%d 天" % (done_days, row["days"]), 9,
                          theme.MUTED, theme.GLASS, anchor="e").pack(side="left")
        page.layout()

    # ------------------------------------------------------------ 日历
    def render_calendar(self):
        page = self.pages.get("cal")
        if page is None:
            return
        page.clear()
        if not self.plan:
            rec = page.add_card(fill=True)
            widgets.label(rec["body"], "还没有计划", 12, theme.MUTED,
                          theme.GLASS).pack(pady=40)
            page.layout()
            return

        rec = page.add_card(pady=int(16 * self.scale))
        b = rec["body"]
        head = tk.Frame(b, bg=theme.GLASS)
        head.pack(fill="x", pady=(0, 8))
        widgets.label(head, "打卡日历", 12, theme.TEXT, theme.GLASS, bold=True).pack(side="left")
        widgets.label(head, "点击任意一天可跳转", 9, theme.DIM, theme.GLASS).pack(side="right")

        grid = tk.Frame(b, bg=theme.GLASS)
        grid.pack(fill="both", expand=True)
        for i in range(7):
            grid.grid_columnconfigure(i, weight=1, uniform="cal")
            widgets.label(grid, "周" + WEEK_CN[i], 9.5, theme.MUTED, theme.GLASS,
                          anchor="center").grid(row=0, column=i, pady=(0, 6))
        self.cal_cells = {}
        dates = self.plan.dates()
        first = dates[0]
        offset = first.weekday()
        for idx, date in enumerate(dates):
            pos = offset + idx
            r, c = pos // 7 + 1, pos % 7
            date_str = date.strftime("%Y-%m-%d")
            complete = self.records.is_day_complete(self.plan, date_str)
            done = self.records.done_count(date_str)
            total = len(self.plan.tasks_of(date_str))
            cell = tk.Canvas(grid, height=int(50 * self.scale), bg=theme.GLASS,
                             highlightthickness=0, bd=0, cursor="hand2")
            cell._fixed = True
            cell.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            cell.bind("<Button-1>", lambda _e, d=date: self.jump_to(d))
            self.cal_cells[date_str] = (cell, date, complete, done, total)
        for r in range(1, (offset + len(dates) - 1) // 7 + 2):
            grid.grid_rowconfigure(r, weight=1)

        legend = tk.Frame(b, bg=theme.GLASS)
        legend.pack(fill="x", pady=(8, 0))
        for color, text in ((theme.OK, "全部完成"), (theme.PURPLE, "部分完成"),
                            (theme.LINE_SOFT, "未开始"), (theme.CYAN, "今天")):
            dot = tk.Canvas(legend, width=10, height=10, bg=theme.GLASS,
                            highlightthickness=0, bd=0)
            dot._fixed = True
            dot.create_oval(1, 1, 9, 9, fill=color, outline="")
            dot.pack(side="left", padx=(0, 4))
            widgets.label(legend, text, 9, theme.MUTED, theme.GLASS).pack(
                side="left", padx=(0, 16))
        page.layout()
        self.after(30, self._paint_calendar)

    def _paint_calendar(self):
        today = dt.date.today()
        for date_str, (cell, date, complete, done, total) in getattr(self, "cal_cells", {}).items():
            cell.delete("all")
            W = cell.winfo_width()
            H = cell.winfo_height()
            if W < 10 or H < 10:
                W, H = int(74 * self.scale), int(50 * self.scale)
            if complete:
                fill, fg, outline = theme.mix_soft(theme.OK, 0.26), theme.OK, theme.OK
            elif done:
                fill, fg, outline = theme.mix_soft(theme.PURPLE, 0.24), theme.PURPLE, theme.PURPLE
            else:
                fill, fg, outline = theme.GLASS_SOFT, theme.MUTED, theme.LINE_SOFT
            if date == today:
                outline = theme.CYAN
            widgets.round_rect(cell, 1, 1, W - 2, H - 2, 9, fill=fill,
                               outline=outline, width=2 if date == today else 1)
            cell.create_text(W / 2.0, H * 0.36, text=date.strftime("%m/%d"),
                             fill=fg, font=self.f(9.5, bold=True))
            if total:
                cell.create_text(W / 2.0, H * 0.72, text="%d/%d" % (done, total),
                                 fill=theme.SUB if not complete else theme.OK,
                                 font=self.f(8.5))

    def jump_to(self, date):
        self.cur_date = date
        self.show_page("today")
        self._sync_today()
        self.refresh_header()

    # ------------------------------------------------------------ 计划操作
    def reload_plan(self, plan_id=None):
        if plan_id:
            self.library.set_current(plan_id)
        self.plan = self.library.load_plan()
        self.records = model.Records.load(self.plan.id) if self.plan else None
        self.cur_date = self._initial_date()
        for key in list(self.pages):
            page = self.pages[key]
            page.clear()
        self.render_today()
        self.render_progress()
        self.render_calendar()
        if "set" in self.pages:
            self.pages["set"].build()
        self.refresh_header()

    def install_plan(self, data, overwrite_id=None, merge=False):
        """把导入结果落成计划并切换过去。返回 (ok, message)。"""
        plan = model.Plan(data)
        if overwrite_id:
            old = self.library.load_plan(overwrite_id)
            plan.id = overwrite_id
            plan.data["id"] = overwrite_id
            self.library.save_plan(plan)
            if old:
                recs = model.Records.load(overwrite_id)
                keep, lost = recs.migrate(old, plan)
                recs.save()
                message = "已覆盖计划，保留 %d 条打卡记录" % keep
                if lost:
                    message += "，%d 条因任务变化被移除" % lost
            else:
                message = "已覆盖计划"
        else:
            self.library.add_plan(plan)
            message = "已导入 %d 天、%d 个任务" % (plan.total_days, plan.total_tasks)
        self.reload_plan(plan.id)
        return True, message

    def do_import(self, path=None):
        from .dialogs import ImportDialog
        ImportDialog(self, path=path)

    def do_template(self):
        from .dialogs import TemplateDialog
        TemplateDialog(self)

    def do_manual(self):
        from .dialogs import ManualDialog
        ManualDialog(self)

    def do_sample(self):
        data, problems = template.sample_plan_dict()
        if not data:
            self.toast("示例计划生成失败")
            return
        ok, message = self.install_plan(data)
        self.toast(message)

    def do_export(self):
        from .dialogs import export_current
        export_current(self)

    def do_backup(self):
        from .dialogs import backup_now
        ok, message = backup_now(self.library)
        self.toast(message)

    # ------------------------------------------------------------ 提示
    def toast(self, message, ms=2600):
        try:
            self._toast.destroy()
        except Exception:
            pass
        cv = tk.Canvas(self, bg=theme.GLASS, highlightthickness=1,
                       highlightbackground=theme.LINE, bd=0)
        self._toast = cv
        font = tkfont.Font(family=theme.FONT, size=int(10 * self.scale))
        width = min(720, font.measure(message) + 56)
        cv.configure(width=width, height=int(38 * self.scale))
        cv.create_text(width / 2.0, int(19 * self.scale), text=message,
                       fill=theme.TEXT, font=self.f(10))
        cv.place(relx=0.5, rely=1.0, anchor="s", y=-18)
        # Canvas 覆盖了 lift()（那是 tag_raise），抬窗口层级要用 Misc.lift
        tk.Misc.lift(cv)
        self.after(ms, lambda: cv.destroy() if cv.winfo_exists() else None)

    def apply_art_change(self, page_key=None):
        """换了背景图后重建对应页面。"""
        self._sync_art()
        art.clear_art_cache()
        # 启动画面不在页面列表里，换图后下次启动才生效，不用重建任何页面
        if page_key == "splash":
            self.toast("启动画面已更新，下次启动生效")
            return
        keys = [page_key] if page_key else list(self.pages)
        cur = self._cur_page
        for key in keys:
            page = self.pages.pop(key, None)
            if page is not None:
                try:
                    page.destroy()
                except Exception:
                    pass
        # 头部底图也跟着「今日」页换
        self._hd_photo = None
        self._cur_page = None
        self.show_page(cur if (cur and not page_key) else
                       ("today" if not page_key else page_key))
        self.refresh_header()

    def apply_font_change(self, size_key):
        self.settings.set("font_size", size_key)
        self.toast("字号已改为 %s，重启后完全生效" % {"small": "小", "medium": "中",
                                                "large": "大"}.get(size_key, size_key))

    def close(self):
        if self._closing:
            return
        self._closing = True
        try:
            self._save_note()
        except Exception:
            pass
        try:
            self.root.update_idletasks()
            self.settings.set_win(self.root.winfo_width(), self.root.winfo_height(),
                                  self.root.winfo_x(), self.root.winfo_y())
        except Exception:
            pass
        self.settings.save()
