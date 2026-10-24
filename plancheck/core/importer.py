"""计划导入：xlsx / csv / tsv / docx / pdf(文字版) / txt / md / 手动粘贴。

所有来源最终都归一到同一种「行」：

    {"date": date|None, "day": int|None, "subject": str, "text": str,
     "hours": float|None, "star": int|None, "note": str, "row": int}

调用方拿到的是一份 ImportResult，里面带 rows、warnings、errors，
再交给预览页让用户确认和修改。
"""
import csv
import datetime as dt
import io
import os
import re
import unicodedata

from .model import _as_text, norm_text, parse_date, peel_date

# 列名同义词（比较前会做全角转半角 + 去空白 + 小写）
COLUMNS = {
    "date": ["日期", "date", "年月日", "开始日期", "起止日期", "日子"],
    "day": ["第几天", "天数", "day", "序号", "第n天", "第几天开始", "dayno", "第几周"],
    "subject": ["科目", "学科", "课程", "分类", "类别", "subject", "category",
                "课程名", "科目名称"],
    "text": ["任务", "任务内容", "内容", "事项", "计划", "安排", "task", "content",
             "描述", "学习内容", "具体任务", "任务描述", "学习任务"],
    "hours": ["小时", "时长", "用时", "时间", "hours", "hour", "h", "预计时长",
              "学时", "耗时", "预计用时"],
    "star": ["星级", "重要度", "优先级", "star", "priority", "重要程度", "权重",
             "重要级别"],
    "note": ["备注", "说明", "note", "remark", "备注信息", "补充", "其他"],
}

# 中文数字 -> 阿拉伯数字（星级/第几天都可能手写成中文）
_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

SUBJECT_HINTS = ["计算机组成", "数据结构", "计算机网络", "计组", "计网", "数学", "英语",
                 "政治", "专业课", "健身", "跑步", "阅读", "工作", "项目", "复盘",
                 "复习", "刷题", "背单词", "物理", "化学", "语文", "历史", "地理"]


class ImportResult(object):
    def __init__(self):
        self.rows = []
        self.warnings = []
        self.errors = []
        self.source = ""

    def ok(self):
        return bool(self.rows) and not self.errors


def _norm_header(cell):
    """表头归一化：全角转半角、去空白与标点、转小写。

    用户手改模板时很容易留下「任务内容（必填）」「小 时」「日期:」这类写法，
    旧版只去空格，匹配不上就整列丢失。
    """
    text = _as_text(cell)
    text = unicodedata.normalize("NFKC", text)          # 全角字母数字括号 -> 半角
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[（(【\[].*?[）)】\]]", "", text)      # 去掉括号里的备注
    text = re.sub(r"[：:、，,。.．/\\|*#\-_]+", "", text)
    return text.lower()


_NORM_COLUMNS = dict((f, [re.sub(r"[\s\u3000]+", "", n.lower()) for n in names])
                     for f, names in COLUMNS.items())


def _match_column(header):
    """返回 {字段: 列下标}。精确匹配优先，其次包含匹配。"""
    mapping = {}
    cells = [_norm_header(c) for c in header]
    # 第一轮：精确
    for idx, key in enumerate(cells):
        if not key:
            continue
        for field, names in _NORM_COLUMNS.items():
            if field in mapping:
                continue
            if key in names:
                mapping[field] = idx
                break
    # 第二轮：包含（「任务内容必填」-> text）
    for idx, key in enumerate(cells):
        if not key:
            continue
        for field, names in _NORM_COLUMNS.items():
            if field in mapping:
                continue
            for name in names:
                if len(name) >= 2 and name in key:
                    mapping[field] = idx
                    break
    return mapping


def _looks_like_data_row(row):
    """这一行更像数据而不是表头。"""
    for cell in row:
        text = _as_text(cell)
        if not text:
            continue
        if parse_date(text):
            return True
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return True
    return False


def _guess_header(rows):
    """在前 8 行里找最像表头的一行。"""
    best = (-1, None, {})
    for i, row in enumerate(rows[:8]):
        mapping = _match_column(row)
        score = len(mapping)
        if score <= 0:
            continue
        # 数据行（含日期/纯数字）不可能是表头
        if _looks_like_data_row(row) and score < 3:
            continue
        if score > best[0]:
            best = (score, i, mapping)
    # 只要认出 1 列就够（用户可能把模板裁成只剩两列），
    # 旧版要求 >=2，导致单列/两列表格认不出表头、把表头当成第一条任务。
    if best[0] >= 1:
        return best[1], best[2]
    return None, {}


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = unicodedata.normalize("NFKC", _as_text(value))
    text = text.replace("小时", "").replace("分钟", "").replace("min", "")
    text = text.replace("h", "").replace("H", "").replace("分", "")
    text = text.replace("约", "").replace("大约", "").replace("左右", "")
    text = text.replace("．", ".").replace("。", ".").replace("，", ".")
    m = re.search(r"\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _to_star(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if 1 <= n <= 5 else None
    text = unicodedata.normalize("NFKC", _as_text(value))
    if "★" in text or "☆" in text:
        return max(1, min(5, text.count("★") + text.count("☆")))
    if "星" in text:
        m = re.search(r"[1-5]", text)
        if m:
            return int(m.group(0))
        for ch, num in _CN_NUM.items():
            if ch in text and 1 <= num <= 5:
                return num
        return None
    m = re.search(r"[1-5]", text)
    if m:
        return int(m.group(0))
    for ch, num in _CN_NUM.items():
        if ch in text and 1 <= num <= 5:
            return num
    return None


def _to_day(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = unicodedata.normalize("NFKC", _as_text(value))
    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))
    for ch, num in _CN_NUM.items():
        if ch in text:
            return num
    return None


def _looks_like_subject(text):
    text = _as_text(text)
    if not text or len(text) > 12:
        return False
    return any(h in text for h in SUBJECT_HINTS)


# 明显是「汇总/说明」而不是任务的行，跳过但记一条提示
_SKIP_WORDS = ("合计", "总计", "小计", "说明：", "说明:", "注：", "注:", "备注：",
               "以下为", "以上为", "总计", "总时长", "统计")


def _is_summary_row(cells):
    joined = "".join(_as_text(c) for c in cells)
    if not joined:
        return False
    if any(w in joined for w in _SKIP_WORDS):
        # 只有「合计」但没有具体任务内容的，才算汇总行
        return True
    return False


def _rows_to_entries(rows, header_idx, mapping, result):
    """把二维表转成行字典；没有表头时按启发式拆列。"""
    start = 0 if header_idx is None else header_idx + 1
    has_header = header_idx is not None
    skipped = 0

    for offset, row in enumerate(rows[start:], start=start + 1):
        cells = list(row)
        if not any(_as_text(c) for c in cells):
            continue
        if _is_summary_row(cells):
            skipped += 1
            continue

        if has_header:
            def cell(field, default=None):
                idx = mapping.get(field)
                if idx is None or idx >= len(cells):
                    return default
                return cells[idx]
            date_raw = cell("date")
            day_raw = cell("day")
            subject = _as_text(cell("subject"))
            text = _as_text(cell("text"))
            hours = _to_float(cell("hours"))
            star = _to_star(cell("star"))
            note = _as_text(cell("note"))
            # 有表头但日期列空、其它列里混了日期：兜底再找一次
            if date_raw is None and day_raw is None:
                for c in cells:
                    if parse_date(c):
                        date_raw = c
                        break
        else:
            # 无表头：按内容猜
            date_raw = day_raw = None
            subject = text = ""
            hours = star = None
            note = ""
            values = [_as_text(c) for c in cells if _as_text(c)]
            # 单列且以日期开头：「2026-03-02 数学 高数第一章」
            if len(values) == 1:
                date_part, rest = peel_date(values[0])
                if date_part:
                    date_raw = date_part
                    rest = re.sub(r"^[\s,，、:：|]+", "", rest)
                    parts = re.split(r"[\s,，、:：|]+", rest, maxsplit=2)
                    if len(parts) >= 2:
                        subject = parts[0]
                        text = parts[1] if len(parts) == 2 else " ".join(parts[1:])
                    elif parts:
                        text = parts[0]
                    values = []
            for value in values:
                if date_raw is None and parse_date(value):
                    date_raw = value
                    continue
                if hours is None and re.fullmatch(
                        r"\d+(?:\.\d+)?\s*(?:小时|h|H|学时|min|分钟)?", value):
                    hours = _to_float(value)
                    continue
                if star is None and ("★" in value or "星" in value):
                    got = _to_star(value)
                    if got:
                        star = got
                        continue
                if not subject and _looks_like_subject(value):
                    subject = value
                    continue
                if not text:
                    text = value
                else:
                    text += " " + value

        date = parse_date(date_raw) if date_raw not in (None, "") else None
        day_no = _to_day(day_raw)
        if date is None and day_no is None and not text:
            continue
        if not text and not subject:
            continue
        result.rows.append({
            "date": date,
            "day": day_no,
            "subject": subject or "未分类",
            "text": text,
            "hours": hours,
            "star": star,
            "note": note,
            "row": offset,
        })

    if skipped:
        result.warnings.append("跳过了 %d 行汇总/说明行" % skipped)


# ---------------------------------------------------------------- 各格式读取
def _read_xlsx(path, result):
    """读 xlsx。**所有工作表都读**，按出现顺序拼起来。

    旧版读到一个非空 sheet 就 break，用户把计划拆到「第一周 / 第二周」
    两个 sheet 里时，第二个表的内容会整份丢掉。
    """
    try:
        from openpyxl import load_workbook
    except Exception:
        result.errors.append("缺少 openpyxl，无法读取 xlsx")
        return []
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        result.errors.append("Excel 打不开：%s" % exc)
        return []

    rows = []
    used = []
    for sheet in wb.worksheets:
        title = (sheet.title or "").strip()
        if title in ("说明", "模板说明", "填写说明", "使用说明"):
            continue
        sheet_rows = []
        try:
            for row in sheet.iter_rows(values_only=True):
                sheet_rows.append(list(row))
        except Exception:
            continue
        if not any(_as_text(c) for r in sheet_rows for c in r):
            continue
        used.append(title or sheet.title)
        rows.extend(sheet_rows)
    try:
        wb.close()
    except Exception:
        pass
    if len(used) > 1:
        result.warnings.append("读取了 %d 个工作表：%s" % (len(used), "、".join(used)))
    return rows


def _read_csv(path, result):
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "big5"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [row for row in reader]


def _read_docx(path, result):
    try:
        import docx
    except Exception:
        result.errors.append("缺少 python-docx，无法读取 docx")
        return []
    document = docx.Document(path)
    rows = []
    for table in document.tables:
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
    if rows:
        return rows
    # 没有表格：段落里常见的「日期 科目 任务 小时」用空格/制表符隔开，
    # 交给 _split_text 按分隔符切列，而不是一行一整条塞进单列。
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    return _split_text("\n".join(lines))


def _read_pdf(path, result):
    try:
        import pdfplumber
    except Exception:
        result.errors.append("缺少 pdfplumber，无法读取 pdf")
        return []
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                for row in table:
                    rows.append([(c or "").strip() for c in row])
            if not tables:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    if line.strip():
                        rows.append([line.strip()])
    if not rows:
        result.errors.append("这个 PDF 没有可提取的文字（可能是扫描件），请改用 Excel/CSV")
    return rows


def _read_text(path, result):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    else:
        text = raw.decode("utf-8", "replace")
    return _split_text(text)


def _split_text(text):
    """纯文本：优先按分隔符切列，否则一行一条。"""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip().strip("|").strip()
        if not line or set(line) <= set("-|: "):
            continue
        if "\t" in line:
            rows.append([c.strip() for c in line.split("\t")])
        elif line.count(",") >= 2:
            rows.append([c.strip() for c in line.split(",")])
        elif line.count("|") >= 2:
            rows.append([c.strip() for c in line.split("|")])
        elif re.match(r"^[-*+]\s+", line) or re.match(r"^\d+[.、)]\s*", line):
            rows.append([re.sub(r"^[-*+]\s+|^\d+[.、)]\s*", "", line)])
        else:
            # 一行里既有日期又有多个空格分隔的字段：「2026-03-05 数学 高数 3h 3星」
            date_part, rest = peel_date(line)
            if date_part and rest and len(re.split(r"\s{2,}", rest)) >= 2:
                cells = [date_part.strftime("%Y-%m-%d")]
                cells.extend([c.strip() for c in re.split(r"\s{2,}", rest) if c.strip()])
                rows.append(cells)
            else:
                rows.append([line])
    return rows


def read_file(path):
    result = ImportResult()
    result.source = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".xlsx", ".xlsm"):
            rows = _read_xlsx(path, result)
        elif ext in (".csv", ".tsv", ".txt", ".md", ".markdown"):
            rows = _read_csv(path, result) if ext in (".csv", ".tsv") else _read_text(path, result)
        elif ext == ".docx":
            rows = _read_docx(path, result)
        elif ext == ".pdf":
            rows = _read_pdf(path, result)
        elif ext == ".xls":
            result.errors.append("不支持旧版 .xls，请用 Excel 另存为 .xlsx")
            return result
        else:
            result.errors.append("不支持的文件类型：%s" % ext)
            return result
    except Exception as exc:
        result.errors.append("读取失败：%s" % exc)
        return result

    if not rows:
        result.errors.append("文件里没有读到任何内容")
        return result

    header_idx, mapping = _guess_header(rows)
    if header_idx is None:
        result.warnings.append("没有找到表头，已按内容自动分列，请在预览页核对")
    try:
        _rows_to_entries(rows, header_idx, mapping, result)
    except Exception as exc:
        result.errors.append("解析行失败：%s" % exc)
        return result

    # 有表头却一行都没解出来：多半是表头认错了（比如把数据行当表头），
    # 退回「无表头」模式再试一次，别让用户对着空预览页干瞪眼。
    if not result.rows and header_idx is not None:
        result.warnings.append("按表头没解析出内容，已改用自动分列重试")
        try:
            _rows_to_entries(rows, None, {}, result)
        except Exception:
            pass

    if not result.rows:
        result.errors.append("没有解析出任何任务行")
    return result


def read_text_block(text):
    result = ImportResult()
    result.source = "手动粘贴"
    rows = _split_text(text or "")
    if not rows:
        result.errors.append("没有内容")
        return result
    header_idx, mapping = _guess_header(rows)
    try:
        _rows_to_entries(rows, header_idx, mapping, result)
    except Exception as exc:
        result.errors.append("解析失败：%s" % exc)
        return result
    if not result.rows and header_idx is not None:
        try:
            _rows_to_entries(rows, None, {}, result)
        except Exception:
            pass
    if not result.rows:
        result.errors.append("没有解析出任何任务行")
    return result


# ---------------------------------------------------------------- 落成计划
def build_plan(rows, name, start_date=None, plan_id=None):
    """把行数据整理成 Plan 需要的 days 结构。

    rows 里的 date 可能为空，只有 day（第 N 天）；此时用 start_date 推算。
    返回 (plan_dict, 问题列表)
    """
    from .model import Plan, new_plan_id, parse_date, task_id, week_index

    problems = []
    start_date = start_date or dt.date.today()
    if isinstance(start_date, str):
        start_date = parse_date(start_date) or dt.date.today()

    # 先确定每一天的日期
    resolved = []
    for row in rows:
        date = row.get("date")
        # 兼容字符串/日期对象：外部传进来的行数据不一定已经解析成 date
        if isinstance(date, (str, dt.date, dt.datetime)):
            date = parse_date(date) or None
        if date is None and row.get("day"):
            try:
                date = start_date + dt.timedelta(days=max(0, int(row["day"]) - 1))
            except Exception:
                date = None
        if date is None:
            problems.append("第 %s 行：没有日期也没有“第几天”，已跳过" % row.get("row"))
            continue
        resolved.append((date, row))

    if not resolved:
        return None, problems

    # 排序 + 按日期归组
    resolved.sort(key=lambda item: (item[0], item[1].get("row") or 0))
    days = {}
    order = []
    for date, row in resolved:
        key = date.strftime("%Y-%m-%d")
        if key not in days:
            days[key] = {"date": key, "tasks": []}
            order.append(key)
        text = (row.get("text") or "").strip()
        subject = (row.get("subject") or "未分类").strip() or "未分类"
        tid = task_id(key, subject, text)
        days[key]["tasks"].append({
            "id": tid,
            "subject": subject,
            "text": text,
            "hours": row.get("hours"),
            "star": row.get("star"),
            "note": (row.get("note") or "").strip(),
        })

    start = min(d[0] for d in resolved)
    end = max(d[0] for d in resolved)
    data = {
        "version": 1,
        "id": plan_id or new_plan_id(),
        "name": name or "我的计划",
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "days": [days[k] for k in order],
        "subjects": [],
    }
    plan = Plan(data)
    data["subjects"] = plan.subject_list()
    return data, problems
