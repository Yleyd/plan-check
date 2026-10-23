"""计划模板导出 / 示例计划 / AI 提示词。

模板列：日期 | 第几天 | 科目 | 任务内容 | 小时 | 星级 | 备注
日期与第几天二选一，其余可空。
"""
import datetime as dt
import os

from . import paths

COLUMNS = ["日期", "第几天", "科目", "任务内容", "小时", "星级", "备注"]
WIDTHS = [13, 9, 14, 46, 8, 8, 24]

SAMPLE_ROWS = [
    ["", 1, "数学", "高数第一章：极限与连续", 3, 3, "先看教材再做题"],
    ["", 1, "英语", "背单词 80 个", 1, 2, ""],
    ["", 2, "数学", "高数第一章习题 1-1 ~ 1-3", 3, 3, ""],
    ["", 2, "专业课", "数据结构：线性表", 2.5, 3, "手写单链表插入删除"],
    ["", 3, "数学", "高数第二章：导数", 3, 3, ""],
    ["", 3, "专业课", "数据结构：栈与队列", 2.5, 2, ""],
    ["", 4, "英语", "阅读理解 2 篇", 1.5, 2, ""],
    ["", 4, "专业课", "数据结构：串与 KMP", 2, 3, "next 数组要会手算"],
    ["", 5, "数学", "第二章习题", 2, 2, ""],
    ["", 5, "复盘", "本周错题整理", 1, 3, "周日固定动作"],
]

PROMPT = """你是学习计划助手。请帮我生成一份可以导入「Plan check」的计划表格。

请严格按下面 7 列输出，用 Markdown 表格或制表符分隔，第一行是表头：

日期 | 第几天 | 科目 | 任务内容 | 小时 | 星级 | 备注

规则：
1. 「日期」和「第几天」二选一填写：知道具体日期就写日期（2026-03-05 这种格式），
   只知道第几天就写数字，另一列留空。
2. 「科目」用简短名字，例如 数学 / 英语 / 专业课 / 政治。
3. 「任务内容」一句话说清当天要做什么，尽量可验收（例如"高数第一章习题 1-1~1-3"）。
4. 「小时」填数字，可以带一位小数，例如 2.5。
5. 「星级」填 1-5，5 表示最重要、必须完成。
6. 「备注」可留空。
7. 每天安排 2-4 个任务，总时长控制在合理范围。

我的情况：
- 目标：
- 截止日期：
- 每天可用时间：
- 当前进度：
"""


def export_template(path):
    """写一份 xlsx 模板到 path。返回 (成功, 消息)。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation
    except Exception:
        return False, "缺少 openpyxl，无法导出 xlsx 模板"

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "计划"

        head_fill = PatternFill("solid", fgColor="1F3864")
        head_font = Font(color="FFFFFF", bold=True, size=11, name="微软雅黑")
        thin = Side(style="thin", color="BFC8D8")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        center = Alignment(horizontal="center", vertical="center")

        ws.append(COLUMNS)
        for idx in range(1, len(COLUMNS) + 1):
            cell = ws.cell(row=1, column=idx)
            cell.fill = head_fill
            cell.font = head_font
            cell.alignment = center
            cell.border = border
            ws.column_dimensions[get_column_letter(idx)].width = WIDTHS[idx - 1]
        ws.row_dimensions[1].height = 26
        ws.freeze_panes = "A2"

        for row in SAMPLE_ROWS:
            ws.append(row)

        for row in ws.iter_rows(min_row=2, max_row=max(2, ws.max_row), max_col=len(COLUMNS)):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center",
                                           horizontal="center" if cell.column in (1, 2, 5, 6) else "left",
                                           wrap_text=cell.column == 4)
                cell.font = Font(name="微软雅黑", size=10)

        # 星级只能 1-5
        dv = DataValidation(type="whole", operator="between", formula1="1", formula2="5",
                            allow_blank=True, showErrorMessage=True,
                            errorTitle="星级", error="请填 1 到 5 的整数")
        ws.add_data_validation(dv)
        dv.add("F2:F2000")

        note = wb.create_sheet("填写说明")
        note.column_dimensions["A"].width = 100
        lines = [
            "Plan check 计划模板 · 填写说明",
            "",
            "1. 日期 与 第几天 二选一即可。只填「第几天」时，导入时会问你计划从哪天开始。",
            "2. 日期格式建议 2026-03-05；也认 2026/3/5、3月5日。",
            "3. 科目可以随便写，导入后会自动统计每个科目的小时数和完成率。",
            "4. 小时 填数字，可以带一位小数（2.5）。不填也能用，只是统计里没有时长。",
            "5. 星级 填 1-5，5 最重要。不填也能用。",
            "6. 一个日期下可以有多行，就是当天多个任务；顺序按行顺序。",
            "7. 想加别的列（比如「地点」）不影响导入，程序只认上面 7 个列名。",
            "8. 填完保存成 xlsx 或 csv 都可以，在软件里点「导入计划文件」选择即可。",
            "",
            "示例已经填在前 10 行，直接改成你自己的就行。",
        ]
        for i, line in enumerate(lines, start=1):
            cell = note.cell(row=i, column=1, value=line)
            cell.font = Font(name="微软雅黑", size=11 if i == 1 else 10,
                             bold=(i == 1), color="1F3864" if i == 1 else "333333")
            cell.alignment = Alignment(vertical="center", wrap_text=True)

        wb.save(path)
        return True, path
    except Exception as exc:
        return False, "导出失败：%s" % exc


def default_template_name():
    return "PlanCheck_计划模板.xlsx"


def sample_plan_dict(start=None):
    """内置示例计划（10 天，直接用，不经过文件）。"""
    from .core.importer import build_plan
    start = start or dt.date.today()
    rows = []
    for i, row in enumerate(SAMPLE_ROWS, start=1):
        rows.append({
            "date": start + dt.timedelta(days=int(row[1]) - 1),
            "day": row[1],
            "subject": row[2],
            "text": row[3],
            "hours": row[4],
            "star": row[5],
            "note": row[6],
            "row": i,
        })
    data, problems = build_plan(rows, "示例计划（可删）", start_date=start)
    return data, problems


def last_dir_path():
    return os.path.join(paths.DATA_DIR, "last_dir.txt")


def read_last_dir():
    try:
        with open(last_dir_path(), "r", encoding="utf-8") as fh:
            value = fh.read().strip()
        if value and os.path.isdir(value):
            return value
    except Exception:
        pass
    return ""


def write_last_dir(path):
    try:
        with open(last_dir_path(), "w", encoding="utf-8") as fh:
            fh.write(path or "")
    except Exception:
        pass


def desktop_dir():
    home = os.path.expanduser("~")
    for name in ("Desktop", "桌面"):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return path
    return home
