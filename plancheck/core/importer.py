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

from .model import norm_text, parse_date, peel_date

# 列名同义词（全部小写比较）
COLUMNS = {
    "date": ["日期", "date", "日 期", "年月日", "开始日期"],
    "day": ["第几天", "第 几 天", "天数", "day", "序号", "第n天", "第N天"],
    "subject": ["科目", "学科", "课程", "分类", "类别", "subject", "category"],
    "text": ["任务", "任务内容", "内容", "事项", "计划", "安排", "task", "content", "描述", "学习内容"],
    "hours": ["小时", "时长", "用时", "时间", "hours", "hour", "h", "预计时长", "学时"],
    "star": ["星级", "重要度", "优先级", "star", "priority", "重要程度"],
    "note": ["备注", "说明", "note", "remark", "备注信息"],
}

SUBJECT_HINTS = ["计算机组成", "数据结构", "计算机网络", "计组", "计网", "数学", "英语",
                 "政治", "专业课", "健身", "跑步", "阅读", "工作", "项目"]


class ImportResult(object):
    def __init__(self):
        self.rows = []
        self.warnings = []
        self.errors = []
        self.source = ""

    def ok(self):
        return bool(self.rows) and not self.errors


def _norm_header(cell):
    return re.sub(r"[\s\u3000]+", "", str(cell or "")).lower()


def _match_column(header):
    """返回 {字段: 列下标}"""
    mapping = {}
    for idx, cell in enumerate(header):
        key = _norm_header(cell)
        if not key:
            continue
        for field, names in COLUMNS.items():
            if field in mapping:
                continue
            if key in [n.lower().replace(" ", "") for n in names]:
                mapping[field] = idx
                break
    return mapping


def _guess_header(rows):
    """在前 5 行里找最像表头的一行。"""
    best = (-1, None, {})
    for i, row in enumerate(rows[:5]):
        mapping = _match_column(row)
        score = len(mapping)
        if score > best[0]:
            best = (score, i, mapping)
    if best[0] >= 2:
        return best[1], best[2]
    return None, {}


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("小时", "").replace("h", "").replace("H", "")
    text = text.replace("．", ".").replace("。", ".")
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
    text = str(value)
    if "★" in text:
        return max(1, min(5, text.count("★")))
    m = re.search(r"\d", text)
    if not m:
        return None
    try:
        n = int(m.group(0))
        return n if 1 <= n <= 5 else None
    except Exception:
        return None


def _to_day(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def _looks_like_subject(text):
    text = str(text or "").strip()
    if not text or len(text) > 12:
        return False
    return any(h in text for h in SUBJECT_HINTS)


def _rows_to_entries(rows, header_idx, mapping, result):
    """把二维表转成行字典；没有表头时按启发式拆列。"""
    start = 0 if header_idx is None else header_idx + 1
    has_header = header_idx is not None

    for offset, row in enumerate(rows[start:], start=start + 1):
        cells = [c for c in row]
        if not any(str(c).strip() for c in cells if c is not None):
            continue

        if has_header:
            def cell(field, default=None):
                idx = mapping.get(field)
                if idx is None or idx >= len(cells):
                    return default
                return cells[idx]
            date_raw = cell("date")
            day_raw = cell("day")
            subject = str(cell("subject") or "").strip()
            text = str(cell("text") or "").strip()
            hours = _to_float(cell("hours"))
            star = _to_star(cell("star"))
            note = str(cell("note") or "").strip()
        else:
            # 无表头：按内容猜
            date_raw = day_raw = None
            subject = text = ""
            hours = star = None
            note = ""
            values = [str(c).strip() for c in cells if c is not None and str(c).strip()]
            # 单列且以日期开头：「2026-03-02 数学 高数第一章」
            if len(values) == 1:
                date_part, rest = peel_date(values[0])
                if date_part:
                    date_raw = date_part.strftime("%Y-%m-%d")
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
                if hours is None and re.fullmatch(r"\d+(?:\.\d+)?\s*(?:小时|h|H)?", value):
                    hours = _to_float(value)
                    continue
                if star is None and ("★" in value):
                    star = _to_star(value)
                    continue
                if not subject and _looks_like_subject(value):
                    subject = value
                    continue
                if not text:
                    text = value
                else:
                    text += " " + value

        date = parse_date(date_raw) if date_raw else None
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


# ---------------------------------------------------------------- 各格式读取
def _read_xlsx(path, result):
    try:
        from openpyxl import load_workbook
    except Exception:
        result.errors.append("缺少 openpyxl，无法读取 xlsx")
        return []
    wb = load_workbook(path, read_only=True, data_only=True)
    rows = []
    for sheet in wb.worksheets:
        if sheet.title in ("说明", "模板说明"):
            continue
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))
        if rows:
            break
    wb.close()
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
    # 没有表格：按段落切，交给文本解析
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    return [[line] for line in lines]


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
    for line in text.splitlines():
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
    _rows_to_entries(rows, header_idx, mapping, result)

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
    _rows_to_entries(rows, header_idx, mapping, result)
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
        # 兼容字符串日期：外部传进来的行数据不一定已经解析成 date
        if isinstance(date, str):
            date = parse_date(date.strip()) or None
        if date is None and row.get("day"):
            date = start_date + dt.timedelta(days=max(0, int(row["day"]) - 1))
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
