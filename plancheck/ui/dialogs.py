"""各种对话框：导入预览、模板下载、手动新建、换背景、字号选项、导出、备份。"""
import datetime as dt
import json
import os
import shutil
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from .. import paths, template, theme
from ..core import importer, model
from . import art, widgets


# ---------------------------------------------------------------- 基础窗口
class BaseDialog(tk.Toplevel):
    def __init__(self, app, title, width=980, height=680):
        tk.Toplevel.__init__(self, app.root)
        self.app = app
        self.title(title)
        self.configure(bg=theme.BG)
        self.transient(app.root)
        self.resizable(True, True)
        self.minsize(720, 480)
        self._center(width, height)
        self.result = None
        self.grab_set()
        self.bind("<Escape>", lambda _e: self.cancel())
        # 底部占位条必须最先 pack：pack 是按顺序分配空间的，
        # 若先 pack 内容(body)，内容一超高就会把 footer 压成 1px 并推到窗外
        # （实测 TemplateDialog 三个按钮 y=-545 h=1，用户看到的就是"只有一个界面"）。
        self._foot = tk.Frame(self, bg=theme.BG)
        self._foot.pack(side="bottom", fill="x")

    def _center(self, w, h):
        root = self.app.root
        try:
            root.update_idletasks()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w = min(w, sw - 80)
            h = min(h, sh - 100)
            x = (sw - w) // 2
            y = max(20, (sh - h) // 2 - 20)
            self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        except Exception:
            self.geometry("%dx%d" % (w, h))

    def cancel(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # ---- 通用块 ----
    def header(self, parent, title, subtitle=""):
        box = tk.Frame(parent, bg=theme.BG)
        box.pack(fill="x", padx=26, pady=(20, 12))
        widgets.label(box, title, 16, theme.TEXT, theme.BG, bold=True).pack(anchor="w")
        if subtitle:
            widgets.label(box, subtitle, 10, theme.MUTED, theme.BG).pack(anchor="w", pady=(4, 0))
        return box

    def footer(self, parent, buttons):
        # 统一放进 __init__ 里先占好位的底部条，避免被超高内容挤出窗口
        bar = tk.Frame(self._foot, bg=theme.BG)
        bar.pack(fill="x", padx=26, pady=(8, 18))
        widgets.label(bar, "", 9, theme.DIM, theme.BG).pack(side="left")
        for text, cmd, kind in reversed(buttons):
            widgets.Pill(bar, text, cmd, width=int(112 * self.app.scale),
                         height=int(36 * self.app.scale), kind=kind,
                         bg=theme.BG).pack(side="right", padx=(8, 0))
        return bar


def _tree(parent, columns, widths, height=12):
    wrap = tk.Frame(parent, bg=theme.GLASS_SOFT, highlightthickness=1,
                    highlightbackground=theme.LINE)
    tree = ttk.Treeview(wrap, columns=columns, show="headings", height=height)
    for col, width in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=width, anchor="w", stretch=True)
    sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree.tag_configure("warn", foreground=theme.WARN)
    tree.tag_configure("bad", foreground=theme.DANGER)
    tree.tag_configure("even", background=theme.GLASS_SOFT)
    return wrap, tree


# ---------------------------------------------------------------- 导入预览
class ImportDialog(BaseDialog):
    def __init__(self, app, path=None):
        BaseDialog.__init__(self, app, "导入计划", 1020, 720)
        self.result_rows = []
        self.warnings = []
        self.errors = []
        self.source = ""
        self.need_start = False

        self.header(self, "导入计划",
                    "支持 xlsx / csv / tsv / docx / pdf(文字版) / txt / md，也可以手动粘贴")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=26)

        self.info = widgets.label(body, "正在读取…", 10, theme.SUB, theme.BG)
        self.info.pack(anchor="w", pady=(0, 8))

        self.wrap, self.tree = _tree(body, ("日期", "第几天", "科目", "任务内容", "小时", "星级"),
                                     (110, 70, 110, 520, 70, 60), height=14)
        self.wrap.pack(fill="both", expand=True)

        self.msg = widgets.label(body, "", 9, theme.WARN, theme.BG, anchor="w",
                                 justify="left")
        self.msg.pack(fill="x", pady=(8, 0))

        form = tk.Frame(body, bg=theme.BG)
        form.pack(fill="x", pady=(10, 0))
        widgets.label(form, "计划名称", 10, theme.SUB, theme.BG).grid(
            row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=self.name_var, bg=theme.GLASS_SOFT, fg=theme.TEXT,
                 insertbackground=theme.CYAN, bd=0, highlightthickness=1,
                 highlightbackground=theme.LINE, font=app.f(10)).grid(
            row=0, column=1, sticky="ew", padx=(10, 0), pady=4, ipady=5)

        widgets.label(form, "导入方式", 10, theme.SUB, theme.BG).grid(
            row=1, column=0, sticky="w", pady=4)
        self.mode_var = tk.StringVar(value="新建计划")
        self.mode_box = ttk.Combobox(form, textvariable=self.mode_var, state="readonly",
                                     values=["新建计划"], font=app.f(10))
        self.mode_box.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)

        self.start_lbl = widgets.label(form, "起始日期", 10, theme.SUB, theme.BG)
        self.start_var = tk.StringVar(value=dt.date.today().strftime("%Y-%m-%d"))
        self.start_entry = tk.Entry(form, textvariable=self.start_var, bg=theme.GLASS_SOFT,
                                    fg=theme.TEXT, insertbackground=theme.CYAN, bd=0,
                                    highlightthickness=1, highlightbackground=theme.LINE,
                                    font=app.f(10))
        form.grid_columnconfigure(1, weight=1)

        self.footer(self, [("取消", self.cancel, "ghost"),
                           ("选择文件…", self._choose, "ghost"),
                           ("导入", self._do_import, "primary")])

        if path:
            self._load(path)
        else:
            self.after(120, self._choose)

    def _choose(self):
        last = self.app.settings.get("last_import_dir") or template.desktop_dir()
        path = filedialog.askopenfilename(
            parent=self, title="选择计划文件", initialdir=last,
            filetypes=[("计划文件", "*.xlsx *.xlsm *.csv *.tsv *.docx *.pdf *.txt *.md"),
                       ("Excel", "*.xlsx *.xlsm"), ("CSV", "*.csv *.tsv"),
                       ("Word", "*.docx"), ("PDF", "*.pdf"),
                       ("文本", "*.txt *.md"), ("所有文件", "*.*")])
        if not path:
            if not self.source:
                self.cancel()
            return
        self.app.settings.set("last_import_dir", os.path.dirname(path))
        self._load(path)

    def _load(self, path):
        self.source = path
        result = importer.read_file(path)
        self._apply(result)

    def _apply(self, result):
        self.result_rows = result.rows
        self.warnings = list(result.warnings)
        self.errors = list(result.errors)
        self.info.configure(text="来源：%s ｜ 解析出 %d 行任务" % (
            result.source, len(result.rows)))
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, row in enumerate(result.rows):
            date = row["date"].strftime("%Y-%m-%d") if row.get("date") else ""
            self.tree.insert("", "end", values=(
                date, row.get("day") or "", row.get("subject") or "",
                row.get("text") or "",
                theme.hours_text(row.get("hours")), theme.star_text(row.get("star"))),
                tags=("even",) if i % 2 else ())
        msgs = list(result.errors) + list(result.warnings)
        self.msg.configure(text="\n".join(msgs[:4]),
                           fg=theme.DANGER if result.errors else theme.WARN)

        if not self.name_var.get():
            base = os.path.splitext(os.path.basename(result.source))[0]
            self.name_var.set(base if base and base != "手动粘贴" else "我的计划")

        need_start = any(r.get("date") is None and r.get("day") for r in result.rows)
        self.need_start = need_start
        if need_start:
            self.start_lbl.grid(row=2, column=0, sticky="w", pady=4)
            self.start_entry.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=4, ipady=5)
        else:
            self.start_lbl.grid_forget()
            self.start_entry.grid_forget()

        # 导入方式：可覆盖已有计划
        values = ["新建计划"]
        self._plan_ids = [""]
        for item in self.app.library.plans():
            values.append("覆盖：%s" % item.get("name"))
            self._plan_ids.append(item.get("id"))
        self.mode_box.configure(values=values)
        if self.mode_var.get() not in values:
            self.mode_var.set(values[0])

    def _do_import(self):
        if self.errors:
            messagebox.showerror("无法导入", "\n".join(self.errors[:6]), parent=self)
            return
        if not self.result_rows:
            messagebox.showwarning("没有数据", "没有解析出任何任务行。", parent=self)
            return
        start = None
        if self.need_start:
            start = model.parse_date(self.start_var.get())
            if not start:
                messagebox.showwarning("日期不对", "起始日期格式应为 2026-03-05。", parent=self)
                return
        name = (self.name_var.get() or "").strip() or "我的计划"
        data, problems = importer.build_plan(self.result_rows, name, start_date=start)
        if not data:
            messagebox.showerror("生成失败", "\n".join(problems[:6]) or "没有有效数据",
                                 parent=self)
            return

        idx = self.mode_box.current()
        overwrite_id = self._plan_ids[idx] if idx > 0 else None
        if overwrite_id:
            old = self.app.library.load_plan(overwrite_id)
            if old:
                new_plan = model.Plan(data)
                recs = model.Records.load(overwrite_id)
                keep, lost = recs.migrate(old, new_plan)
                if lost:
                    ok = messagebox.askyesno(
                        "确认覆盖",
                        "新计划里有 %d 条旧打卡记录对不上（任务内容或日期变了），"
                        "这些记录会丢失。\n\n保留 %d 条。要继续吗？" % (lost, keep),
                        parent=self)
                    if not ok:
                        return
        ok, message = self.app.install_plan(data, overwrite_id=overwrite_id)
        self.app.toast(message)
        self.cancel()


# ---------------------------------------------------------------- 手动新建
class ManualDialog(BaseDialog):
    def __init__(self, app):
        BaseDialog.__init__(self, app, "手动新建计划", 940, 700)
        self.header(self, "手动新建 / 粘贴",
                    "每行一个任务，用 Tab、逗号或竖线分列：日期 | 科目 | 任务内容 | 小时 | 星级")
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=26)

        widgets.label(body, "示例：", 9, theme.MUTED, theme.BG).pack(anchor="w")
        widgets.label(body, "2026-03-05, 数学, 高数第一章习题, 3, 3\n"
                            "2026-03-05, 英语, 背单词 80 个, 1, 2\n"
                            "3, 专业课, 数据结构线性表, 2.5, 3",
                      9, theme.DIM, theme.BG, justify="left").pack(anchor="w", pady=(2, 10))

        wrap = tk.Frame(body, bg=theme.GLASS_SOFT, highlightthickness=1,
                        highlightbackground=theme.LINE)
        wrap.pack(fill="both", expand=True)
        self.text = tk.Text(wrap, bg=theme.GLASS_SOFT, fg=theme.TEXT, bd=0,
                            highlightthickness=0, wrap="none", undo=True,
                            insertbackground=theme.CYAN, font=app.f(10),
                            padx=12, pady=10)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        form = tk.Frame(body, bg=theme.BG)
        form.pack(fill="x", pady=(10, 0))
        widgets.label(form, "计划名称", 10, theme.SUB, theme.BG).grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value="我的计划")
        tk.Entry(form, textvariable=self.name_var, bg=theme.GLASS_SOFT, fg=theme.TEXT,
                 insertbackground=theme.CYAN, bd=0, highlightthickness=1,
                 highlightbackground=theme.LINE, font=app.f(10), width=32).grid(
            row=0, column=1, sticky="w", padx=(10, 24), ipady=5)
        widgets.label(form, "起始日期", 10, theme.SUB, theme.BG).grid(row=0, column=2, sticky="w")
        self.start_var = tk.StringVar(value=dt.date.today().strftime("%Y-%m-%d"))
        tk.Entry(form, textvariable=self.start_var, bg=theme.GLASS_SOFT, fg=theme.TEXT,
                 insertbackground=theme.CYAN, bd=0, highlightthickness=1,
                 highlightbackground=theme.LINE, font=app.f(10), width=16).grid(
            row=0, column=3, sticky="w", padx=(10, 0), ipady=5)

        self.footer(self, [("取消", self.cancel, "ghost"), ("创建", self._create, "primary")])

    def _create(self):
        text = self.text.get("1.0", "end")
        result = importer.read_text_block(text)
        if result.errors:
            messagebox.showerror("解析失败", "\n".join(result.errors[:5]), parent=self)
            return
        start = model.parse_date(self.start_var.get()) or dt.date.today()
        data, problems = importer.build_plan(result.rows, self.name_var.get() or "我的计划",
                                             start_date=start)
        if not data:
            messagebox.showerror("生成失败", "\n".join(problems[:5]) or "没有有效数据",
                                 parent=self)
            return
        ok, message = self.app.install_plan(data)
        self.app.toast(message)
        self.cancel()


# ---------------------------------------------------------------- 下载模板
class TemplateDialog(BaseDialog):
    def __init__(self, app):
        BaseDialog.__init__(self, app, "下载计划模板", 780, 620)
        self.header(self, "下载计划模板",
                    "存成 xlsx，填完再导入；也可以直接复制下面的 AI 提示词")
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=26)

        widgets.label(body, "模板列", 11, theme.TEXT, theme.BG, bold=True).pack(anchor="w")
        widgets.label(body, "日期 ｜ 第几天 ｜ 科目 ｜ 任务内容 ｜ 小时 ｜ 星级 ｜ 备注",
                      10, theme.CYAN, theme.BG).pack(anchor="w", pady=(4, 12))
        widgets.label(body, "日期与「第几天」二选一，其余列都可以留空。示例已经填好 10 行。",
                      9, theme.MUTED, theme.BG).pack(anchor="w", pady=(0, 16))

        widgets.label(body, "让 AI 帮你排计划", 11, theme.TEXT, theme.BG, bold=True).pack(anchor="w")
        wrap = tk.Frame(body, bg=theme.GLASS_SOFT, highlightthickness=1,
                        highlightbackground=theme.LINE)
        wrap.pack(fill="both", expand=True, pady=(6, 10))
        self.prompt = tk.Text(wrap, bg=theme.GLASS_SOFT, fg=theme.SUB, bd=0,
                              highlightthickness=0, wrap="word", height=8,
                              insertbackground=theme.CYAN, font=app.f(9),
                              padx=12, pady=10)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.prompt.yview)
        self.prompt.configure(yscrollcommand=sb.set)
        self.prompt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.prompt.insert("1.0", template.PROMPT)

        self.state = widgets.label(body, "", 9, theme.OK, theme.BG)
        self.state.pack(anchor="w")

        self.footer(self, [("关闭", self.cancel, "ghost"),
                           ("复制提示词", self._copy, "ghost"),
                           ("另存为 xlsx", self._save, "primary")])

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.prompt.get("1.0", "end").strip())
            self.state.configure(text="提示词已复制，粘给 AI 就行")
        except Exception as exc:
            self.state.configure(text="复制失败：%s" % exc, fg=theme.DANGER)

    def _save(self):
        last = self.app.settings.get("last_template_dir") or template.desktop_dir()
        path = filedialog.asksaveasfilename(
            parent=self, title="保存计划模板",
            initialdir=last, initialfile=template.default_template_name(),
            defaultextension=".xlsx",
            filetypes=[("Excel 工作簿", "*.xlsx")])
        if not path:
            return
        ok, message = template.export_template(path)
        if not ok:
            messagebox.showerror("保存失败", message, parent=self)
            return
        self.app.settings.set("last_template_dir", os.path.dirname(path))
        self.state.configure(text="已保存到 %s" % path, fg=theme.OK)
        if messagebox.askyesno("保存成功", "模板已保存到：\n%s\n\n要打开所在文件夹吗？" % path,
                               parent=self):
            try:
                os.startfile(os.path.dirname(path))
            except Exception:
                pass


# ---------------------------------------------------------------- 换背景
class ArtDialog(BaseDialog):
    def __init__(self, app):
        BaseDialog.__init__(self, app, "换背景图", 900, 640)
        self.header(self, "换背景图",
                    "每页可以单独换，也可以恢复默认。只支持 jpg / png，会自动修正方向并缩到 2560 宽")
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=26)

        self.vars = {}
        self.custom_now = dict(app.settings.get("custom_art") or {})
        pages = [("today", "今日"), ("prog", "进度"), ("cal", "日历"), ("set", "设置"),
                 ("splash", "启动画面")]
        keys = list(art.ART_ORDER)
        values = ["%s（%s）" % (k, art.ART_NAMES.get(k, k)) for k in keys]
        for key, name in pages:
            row = tk.Frame(body, bg=theme.BG)
            row.pack(fill="x", pady=5)
            widgets.label(row, name, 10, theme.TEXT, theme.BG, bold=True,
                          width=8, anchor="w").pack(side="left")
            current = (app.settings.get("start_art") if key == "splash"
                       else app.settings.art_of(key))
            var = tk.StringVar(value="%s（%s）" % (current, art.ART_NAMES.get(current, current)))
            box = ttk.Combobox(row, textvariable=var, state="readonly",
                               values=values, width=24, font=app.f(10))
            box.pack(side="left", padx=(0, 10))
            self.vars[key] = (var, keys, current)
            widgets.Pill(row, "选本地图片…",
                         lambda k=key: self._pick_file(k),
                         width=124, height=32, bg=theme.BG).pack(side="left")
            if art.page_to_art_key(key) in self.custom_now:
                widgets.label(row, "（已用自定义图）", 9, theme.OK, theme.BG).pack(
                    side="left", padx=(8, 0))

        widgets.label(body, "自定义图片会复制到数据目录的 assets/user 下，原文件删掉也不影响。",
                      9, theme.MUTED, theme.BG).pack(anchor="w", pady=(14, 0))
        self.state = widgets.label(body, "", 9, theme.OK, theme.BG)
        self.state.pack(anchor="w", pady=(4, 0))

        self.footer(self, [("取消", self.cancel, "ghost"),
                           ("恢复默认", self._reset, "ghost"),
                           ("应用", self._apply, "primary")])

    def _pick_file(self, page_key):
        last = self.app.settings.get("last_import_dir") or template.desktop_dir()
        path = filedialog.askopenfilename(
            parent=self, title="选择背景图", initialdir=last,
            filetypes=[("图片", "*.jpg *.jpeg *.png"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            ok, message = self._import_image(path, page_key)
        except Exception as exc:
            ok, message = False, "处理失败：%s" % exc
        if ok:
            self.state.configure(text="已导入并应用：%s" % message, fg=theme.OK)
            self.app.settings.set("last_import_dir", os.path.dirname(path))
        else:
            self.state.configure(text=message, fg=theme.DANGER)

    def _import_image(self, path, page_key):
        """把图片规范成 2560 宽以内 jpg，存到 USER_ASSETS，并立即应用。"""
        Image, ImageOps = art.pil()[0], art.pil()[4]
        im = Image.open(path)
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        if w > 2560:
            im = im.resize((2560, int(h * 2560.0 / w)), Image.LANCZOS)
        name = "custom_%s_%s.jpg" % (page_key, dt.datetime.now().strftime("%H%M%S"))
        paths.ensure_dirs()
        target = os.path.join(paths.USER_ASSETS, name)
        im.save(target, "JPEG", quality=92)

        custom = self.app.settings.get("custom_art") or {}
        # 统一按「图 key」存：art_path() 是按图 key 查的，老版本按页面 key 存
        # 会永远查不到，这就是「换图只是做样子」的第一层原因。
        art_key = art.page_to_art_key(page_key)
        custom[art_key] = name
        self.app.settings.set("custom_art", custom)
        self.custom_now[art_key] = name
        art.set_custom_map(custom)
        art.clear_art_cache()
        # 立刻生效（用户点了「选本地图片」就应该马上看到）
        self.app.apply_art_change(None if page_key == "splash" else page_key)
        return True, os.path.basename(path)

    def _reset(self):
        defaults = {"today": "gen_night", "prog": "gen_ring", "cal": "gen_hat",
                    "set": "gen_clash", "splash": "gen_ring"}
        for key, value in defaults.items():
            if key == "splash":
                self.app.settings.set("start_art", value)
            else:
                self.app.settings.set_art(key, value)
        self.app.settings.set("custom_art", {})
        self.custom_now = {}
        art.set_custom_map({})
        art.clear_art_cache()
        keys = list(art.ART_ORDER)
        for key, (var, _keys, _cur) in self.vars.items():
            value = defaults[key]
            var.set("%s（%s）" % (value, art.ART_NAMES.get(value, value)))
        self.state.configure(text="已恢复默认，点「应用」后生效", fg=theme.OK)

    def _apply(self):
        for key, (var, keys, _cur) in self.vars.items():
            text = var.get()
            value = text.split("（")[0].strip()
            if value not in keys:
                continue
            if key == "splash":
                self.app.settings.set("start_art", value)
            else:
                self.app.settings.set_art(key, value)
            # 只有用户「明确改选了别的内置图」才取消该页的自定义图。
            # 之前是无条件 pop：点「选本地图片」生效后再点「应用」，
            # 因为下拉框还停在原内置图上，自定义图会被立刻删掉 ——
            # 这正是「换图只是做样子」的直接原因。
            art_key = art.page_to_art_key(key)
            if art_key in self.custom_now and value != art_key:
                custom = self.app.settings.get("custom_art") or {}
                custom.pop(art_key, None)
                custom.pop(key, None)
                self.app.settings.set("custom_art", custom)
                self.custom_now.pop(art_key, None)
        art.set_custom_map(self.app.settings.get("custom_art") or {})
        art.clear_art_cache()
        self.app.apply_art_change()
        self.app.toast("背景已更新")
        self.cancel()


# ---------------------------------------------------------------- 字号与选项
class OptionsDialog(BaseDialog):
    def __init__(self, app):
        BaseDialog.__init__(self, app, "字号与选项", 700, 520)
        self.header(self, "字号与选项", "改完重启软件，字号会完全生效")
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=26)

        widgets.label(body, "界面字号", 11, theme.TEXT, theme.BG, bold=True).pack(anchor="w")
        self.font_key = app.settings.get("font_size")
        if self.font_key not in ("small", "medium", "large"):
            self.font_key = "medium"
        row = tk.Frame(body, bg=theme.BG)
        row.pack(anchor="w", pady=(8, 20))
        self.font_btns = {}
        for value, label_text in (("small", "小"), ("medium", "中"), ("large", "大")):
            btn = widgets.Pill(row, label_text,
                               lambda v=value: self._set_font(v),
                               width=76, height=34, bg=theme.BG,
                               kind="primary" if value == self.font_key else "ghost")
            btn.pack(side="left", padx=(0, 8))
            self.font_btns[value] = btn

        widgets.label(body, "启动画面", 11, theme.TEXT, theme.BG, bold=True).pack(anchor="w")
        self.splash_var = tk.BooleanVar(value=bool(app.settings.get("show_splash", True)))
        tk.Checkbutton(body, text="启动时显示动画", variable=self.splash_var,
                       bg=theme.BG, fg=theme.SUB, selectcolor=theme.GLASS_SOFT,
                       activebackground=theme.BG, activeforeground=theme.TEXT,
                       font=app.f(10), bd=0, highlightthickness=0).pack(
            anchor="w", pady=(8, 20))

        widgets.label(body, "数据目录", 11, theme.TEXT, theme.BG, bold=True).pack(anchor="w")
        widgets.label(body, paths.DATA_DIR, 9, theme.CYAN, theme.BG).pack(anchor="w", pady=(4, 2))
        widgets.label(body, paths.data_location_note(), 9, theme.MUTED, theme.BG).pack(anchor="w")

        self.footer(self, [("取消", self.cancel, "ghost"), ("保存", self._save, "primary")])

    def _set_font(self, value):
        self.font_key = value
        for key, btn in self.font_btns.items():
            btn._kind = "primary" if key == value else "ghost"
            btn.draw()

    def _save(self):
        self.app.settings.set("font_size", self.font_key)
        self.app.settings.set("show_splash", bool(self.splash_var.get()))
        self.app.toast("已保存，重启后生效")
        self.cancel()


# ---------------------------------------------------------------- 导出 / 备份
def export_current(app):
    if not app.plan or not app.records:
        app.toast("还没有计划，先导入一份")
        return
    last = app.settings.get("last_export_dir") or template.desktop_dir()
    default = "%s_进度_%s.md" % (app.plan.name, dt.date.today().strftime("%Y%m%d"))
    path = filedialog.asksaveasfilename(
        parent=app.root, title="导出进度报告", initialdir=last,
        initialfile=default.replace("/", "_"),
        defaultextension=".md",
        filetypes=[("Markdown", "*.md"), ("文本", "*.txt")])
    if not path:
        return
    try:
        text = _report_text(app)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception as exc:
        messagebox.showerror("导出失败", str(exc), parent=app.root)
        return
    app.settings.set("last_export_dir", os.path.dirname(path))
    app.toast("已导出到 %s" % os.path.basename(path))


def _report_text(app):
    plan, recs = app.plan, app.records
    total = plan.total_tasks
    done = recs.tasks_done(plan)
    hours_plan = plan.total_hours
    hours_done = recs.hours_done(plan)
    run, best = recs.streak(plan)
    lines = ["# %s · 进度报告" % plan.name, "",
             "生成时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "| 项目 | 数值 |", "| --- | --- |",
             "| 计划跨度 | %s ~ %s |" % (plan.start, plan.end),
             "| 总天数 | %d |" % plan.total_days,
             "| 任务完成 | %d / %d |" % (done, total),
             "| 时长 | %.1f / %.1f 小时 |" % (hours_done, hours_plan),
             "| 连续打卡 | 当前 %d 天 / 最长 %d 天 |" % (run, best), "",
             "## 各科目", "", "| 科目 | 任务 | 完成 | 计划时长 | 已完成时长 |",
             "| --- | --- | --- | --- | --- |"]
    for subj, row in plan.subject_stats().items():
        n_done = sum(1 for d, t in plan.iter_tasks()
                     if (t.get("subject") or "未分类") == subj
                     and recs.is_done(d, t.get("id")))
        lines.append("| %s | %d | %d | %.1f | %.1f |" % (
            subj, row["tasks"], n_done, row["hours"], recs.hours_done(plan, subj)))
    lines += ["", "## 逐日记录", ""]
    for day in plan.days:
        date_str = day.get("date")
        d = model.parse_date(date_str)
        if not d:
            continue
        tasks = day.get("tasks") or []
        n_done = recs.done_count(date_str)
        mark = "✅" if tasks and n_done == len(tasks) else ("🟣" if n_done else "⬜")
        lines.append("### %s（周%s）%s %d/%d" % (
            date_str, "一二三四五六日"[d.weekday()], mark, n_done, len(tasks)))
        for task in tasks:
            flag = "x" if recs.is_done(date_str, task.get("id")) else " "
            extra = []
            if task.get("hours") is not None:
                extra.append(theme.hours_text(task.get("hours")))
            if task.get("star"):
                extra.append(theme.star_text(task.get("star")))
            lines.append("- [%s] %s｜%s%s" % (
                flag, task.get("subject") or "未分类", task.get("text") or "",
                ("｜" + " ".join(extra)) if extra else ""))
        note = recs.note_of(date_str)
        if note.strip():
            lines.append("  > 备注：%s" % note.strip().replace("\n", " / "))
        lines.append("")
    gnote = app.settings.get("global_note") or ""
    if gnote.strip():
        lines += ["## 总体备注", "", gnote, ""]
    return "\n".join(lines)


def backup_now(library):
    try:
        paths.ensure_dirs()
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        target = os.path.join(paths.BACKUP_DIR, "backup_%s" % stamp)
        os.makedirs(target, exist_ok=True)
        for name in os.listdir(paths.PLANS_DIR):
            src = os.path.join(paths.PLANS_DIR, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(target, name))
        _prune_backups()
        return True, "已备份到 backups/%s" % os.path.basename(target)
    except Exception as exc:
        return False, "备份失败：%s" % exc


def _prune_backups(keep=14):
    try:
        items = sorted([d for d in os.listdir(paths.BACKUP_DIR)
                        if os.path.isdir(os.path.join(paths.BACKUP_DIR, d))])
        for name in items[:-keep]:
            shutil.rmtree(os.path.join(paths.BACKUP_DIR, name), ignore_errors=True)
    except Exception:
        pass


def auto_backup(library):
    """每天第一次启动自动备份。"""
    try:
        paths.ensure_dirs()
        stamp = dt.date.today().strftime("%Y%m%d")
        target = os.path.join(paths.BACKUP_DIR, "auto_%s" % stamp)
        if os.path.exists(target):
            return
        os.makedirs(target, exist_ok=True)
        for name in os.listdir(paths.PLANS_DIR):
            src = os.path.join(paths.PLANS_DIR, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(target, name))
        _prune_backups()
    except Exception:
        pass
