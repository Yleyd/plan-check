"""无窗口自检：不依赖 Tk，验证模型、导入、模板、路径。"""
import datetime as dt
import os
import sys
import tempfile


_LOG_STREAM = None


def _setup_stdout():
    """打包成窗口程序后 stdout 可能是 None，或是 GBK 控制台。

    GBK 编不了 "✓" 之类的字符会把自检本身搞崩；无控制台时 print 又会静默丢弃。
    两种情况都兜住：优先转 UTF-8，没有 stdout 就写 logs/selftest.log。
    """
    global _LOG_STREAM
    stream = sys.stdout
    if stream is not None:
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        return True
    try:
        from . import paths
        paths.ensure_dirs()
        path = os.path.join(paths.LOG_DIR, "selftest.log")
        _LOG_STREAM = open(path, "w", encoding="utf-8")
        sys.stdout = _LOG_STREAM
        sys.stderr = _LOG_STREAM
        return True
    except Exception:
        return False


def _ok(name, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    try:
        print("[%s] %s%s" % (mark, name, ("  " + detail) if detail else ""))
    except Exception:
        pass
    return bool(condition)


def _say(text):
    try:
        print(text)
    except Exception:
        pass


def run():
    _setup_stdout()
    from . import paths, template, theme
    from .core import importer, model
    from .core.settings import Settings

    results = []
    _say("=" * 62)
    _say("Plan check 自检  v%s" % paths.VERSION)
    _say("数据目录：%s" % paths.DATA_DIR)
    _say("=" * 62)

    paths.ensure_dirs()
    results.append(_ok("数据目录可写", os.access(paths.DATA_DIR, os.W_OK)))

    # ---- 日期与 ID ----
    results.append(_ok("日期解析 2026-03-05", model.parse_date("2026-03-05") == dt.date(2026, 3, 5)))
    results.append(_ok("日期解析 2026/3/5", model.parse_date("2026/3/5") == dt.date(2026, 3, 5)))
    results.append(_ok("日期解析 3月5日",
                       model.parse_date("3月5日") == dt.date(dt.date.today().year, 3, 5)))
    tid1 = model.task_id("2026-03-05", "数学", "高数 第一章")
    tid2 = model.task_id("2026-03-05", " 数学 ", "高数  第一章 ")
    results.append(_ok("任务 ID 归一化一致", tid1 == tid2, tid1))

    # ---- 示例计划 ----
    data, problems = template.sample_plan_dict(dt.date(2026, 3, 2))
    results.append(_ok("示例计划生成", bool(data) and not problems))
    plan = model.Plan(data)
    results.append(_ok("示例计划 5 天", plan.total_days == 5, "实际 %d 天" % plan.total_days))
    results.append(_ok("示例计划 10 个任务", plan.total_tasks == 10,
                       "实际 %d" % plan.total_tasks))
    results.append(_ok("示例计划科目识别", len(plan.subject_stats()) >= 3,
                       "、".join(plan.subject_stats().keys())))
    results.append(_ok("总时长 21.5h", abs(plan.total_hours - 21.5) < 1e-6,
                       "实际 %.1f" % plan.total_hours))

    # ---- 记录 ----
    recs = model.Records("selftest")
    first = plan.days[0]
    tasks = first["tasks"]
    recs.toggle(first["date"], tasks[0]["id"])
    results.append(_ok("勾选写入", recs.is_done(first["date"], tasks[0]["id"])))
    results.append(_ok("当日完成计数", recs.done_count(first["date"]) == 1))
    recs.mark_all(first["date"], [t["id"] for t in tasks], True)
    results.append(_ok("一键全完成", recs.is_day_complete(plan, first["date"])))
    run_days, best = recs.streak(plan)
    results.append(_ok("连续天数 ≥1", run_days >= 1, "当前 %d 最长 %d" % (run_days, best)))
    recs.set_note(first["date"], "自检备注")
    results.append(_ok("备注写入", recs.note_of(first["date"]) == "自检备注"))

    # ---- 迁移 ----
    old = model.Plan(data)
    new_data = model.Plan(data).to_json()
    new_data["days"][0]["tasks"][0]["text"] = "改过的任务"
    new_data["days"][0]["tasks"][0]["id"] = model.task_id(
        new_data["days"][0]["date"], new_data["days"][0]["tasks"][0]["subject"], "改过的任务")
    new_plan = model.Plan(new_data)
    keep, lost = recs.migrate(old, new_plan)
    results.append(_ok("覆盖时迁移记录", lost >= 1, "保留 %d 丢失 %d" % (keep, lost)))

    # ---- 导入 ----
    result = importer.read_text_block(
        "日期,科目,任务内容,小时,星级\n"
        "2026-03-02,数学,高数第一章,3,3\n"
        "2026-03-02,英语,背单词,1,2\n"
        "2026-03-03,专业课,数据结构,2.5,3\n")
    results.append(_ok("粘贴解析 3 行", len(result.rows) == 3, "实际 %d" % len(result.rows)))
    results.append(_ok("粘贴解析科目", result.rows[0]["subject"] == "数学"))
    results.append(_ok("粘贴解析小时", abs(result.rows[0]["hours"] - 3.0) < 1e-6))
    results.append(_ok("粘贴解析星级", result.rows[0]["star"] == 3))

    result2 = importer.read_text_block("2026-03-02\t数学\t高数\t3\t3")
    results.append(_ok("制表符解析", len(result2.rows) == 1))

    result3 = importer.read_text_block("- 2026-03-02 数学 高数第一章")
    results.append(_ok("无表头列表解析", len(result3.rows) == 1,
                       str(result3.rows[0] if result3.rows else "")))

    # ---- 只有「第几天」 ----
    result4 = importer.read_text_block("第几天,科目,任务内容\n1,数学,高数\n2,英语,单词")
    results.append(_ok("第几天解析", len(result4.rows) == 2))
    d4, _p = importer.build_plan(result4.rows, "天数计划", start_date=dt.date(2026, 3, 2))
    results.append(_ok("按第几天推算日期",
                       bool(d4) and d4["days"][0]["date"] == "2026-03-02"))

    # ---- 模板导出 ----
    tmpdir = tempfile.mkdtemp(prefix="plancheck_selftest_")
    xlsx = os.path.join(tmpdir, "t.xlsx")
    ok, message = template.export_template(xlsx)
    results.append(_ok("模板导出 xlsx", ok and os.path.exists(xlsx), str(message)))
    if ok:
        back = importer.read_file(xlsx)
        results.append(_ok("模板可再导入", len(back.rows) >= 8,
                           "读回 %d 行" % len(back.rows)))

    # ---- csv 往返 ----
    csv_path = os.path.join(tmpdir, "t.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("日期,科目,任务内容,小时,星级\n2026-03-02,数学,高数,3,3\n")
    back2 = importer.read_file(csv_path)
    results.append(_ok("csv 读取", len(back2.rows) == 1))

    # ---- 设置 ----
    st = Settings()
    results.append(_ok("设置默认值", st.get("font_size") in ("small", "medium", "large")))
    results.append(_ok("四页背景图映射", all(st.art_of(p) for p in ("today", "prog", "cal", "set"))))

    # ---- 主题 ----
    results.append(_ok("科目调色板 10 色", len(theme.PALETTE) == 10))
    results.append(_ok("星级渲染", theme.star_text(3) == "★★★"))
    results.append(_ok("小时渲染", theme.hours_text(2.5) == "2.5 h"))

    # ---- 内置背景图（1.0.2 起全部是程序生成的原创图）----
    from .ui import art as _art
    gen_keys = [k for k in _art.ART_ORDER if k.startswith("gen_")]
    missing = [k for k in gen_keys if not os.path.exists(_art.art_path(k))]
    results.append(_ok("内置生成图齐全", len(gen_keys) == 6 and not missing,
                       "缺 %s" % missing if missing else "%d 张" % len(gen_keys)))
    legacy_left = [k for k in ("night", "ring", "hat", "clash", "flame", "eye")
                   if os.path.exists(os.path.join(paths.DEFAULT_ASSETS,
                                                  _art.ART_FILES.get(k, "")))]
    results.append(_ok("旧插画未打包", not legacy_left, str(legacy_left)))

    # ---- 图标资源 ----
    results.append(_ok("窗口图标 icon.png", os.path.exists(paths.ICON_PNG), paths.ICON_PNG))
    results.append(_ok("安装图标 icon.ico", os.path.exists(paths.ICON_ICO), paths.ICON_ICO))
    try:
        from PIL import Image
        if os.path.exists(paths.ICON_PNG):
            with Image.open(paths.ICON_PNG) as ic:
                results.append(_ok("图标尺寸 512", ic.size == (512, 512), str(ic.size)))
        if os.path.exists(paths.ICON_ICO):
            with Image.open(paths.ICON_ICO) as ic:
                sizes = sorted(ic.ico.sizes())
            results.append(_ok("图标含 8 档尺寸", len(sizes) == 8,
                               " ".join(str(s[0]) for s in sizes)))
    except Exception as exc:
        results.append(_ok("图标可读", False, str(exc)))

    # ---- 清理 ----
    try:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass

    total = len(results)
    passed = sum(1 for r in results if r)
    _say("-" * 62)
    _say("通过 %d / %d" % (passed, total))
    _say("全部通过" if passed == total else "有失败项")
    if _LOG_STREAM is not None:
        try:
            _LOG_STREAM.flush()
        except Exception:
            pass
    return 0 if passed == total else 1
