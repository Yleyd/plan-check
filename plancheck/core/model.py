"""计划与打卡数据模型。

计划 = 若干天，每天若干任务；任务 id 由「日期+科目+内容」哈希得到，
所以重新导入计划时，能对上的任务仍然保留历史打卡。
"""
import datetime as dt
import hashlib
import json
import os
import re

from .. import paths

PLAN_VERSION = 1
REC_VERSION = 1
DATE_FMT = "%Y-%m-%d"


def today_str():
    return dt.date.today().strftime(DATE_FMT)


_DATE_PATTERNS = [
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"),
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$"),
    re.compile(r"^(\d{1,2})月(\d{1,2})日$"),
    re.compile(r"^(\d{1,2})[-/.](\d{1,2})$"),
]


def parse_date(text):
    """严格解析日期。整串必须是日期，不允许尾巴带别的字。"""
    text = (text or "").strip()
    if not text:
        return None
    for pattern in _DATE_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        groups = m.groups()
        try:
            if len(groups) == 3:
                return dt.date(int(groups[0]), int(groups[1]), int(groups[2]))
            return dt.date(dt.date.today().year, int(groups[0]), int(groups[1]))
        except Exception:
            return None
    return None


def peel_date(text):
    """从「2026-03-02 数学 高数」这种行首日期里剥出日期和剩余文本。"""
    text = (text or "").strip()
    m = re.match(r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日?"
                 r"|\d{1,2}月\d{1,2}日)\s*[，,、:：|]?\s*(.*)$", text)
    if not m:
        return None, text
    date = parse_date(m.group(1))
    if not date:
        return None, text
    return date, (m.group(2) or "").strip()


def norm_text(text):
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def task_id(date, subject, text):
    raw = "%s|%s|%s" % (date, norm_text(subject), norm_text(text))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def week_index(start, date):
    return (date - start).days // 7 + 1


class Plan(object):
    def __init__(self, data):
        self.data = data
        self.id = data.get("id") or ""
        self.name = data.get("name") or "未命名计划"
        self.start = parse_date(data.get("start")) or dt.date.today()
        self.end = parse_date(data.get("end")) or self.start
        self.days = data.get("days") or []
        self.subjects = data.get("subjects") or []

    # ---- 基本信息 ----
    @property
    def total_days(self):
        return len(self.days)

    def dates(self):
        out = []
        for day in self.days:
            d = parse_date(day.get("date"))
            if d:
                out.append(d)
        return out

    def tasks_of(self, date_str):
        for day in self.days:
            if day.get("date") == date_str:
                return day.get("tasks") or []
        return []

    def day_of(self, date_str):
        for day in self.days:
            if day.get("date") == date_str:
                return day
        return None

    def iter_tasks(self):
        for day in self.days:
            for task in day.get("tasks") or []:
                yield day.get("date"), task

    @property
    def total_tasks(self):
        return sum(len(day.get("tasks") or []) for day in self.days)

    @property
    def total_hours(self):
        return sum(float(t.get("hours") or 0) for _, t in self.iter_tasks())

    def subject_stats(self):
        out = {}
        for _, task in self.iter_tasks():
            subj = task.get("subject") or "未分类"
            row = out.setdefault(subj, {"tasks": 0, "hours": 0.0})
            row["tasks"] += 1
            row["hours"] += float(task.get("hours") or 0)
        return out

    def week_stats(self):
        out = {}
        for day in self.days:
            d = parse_date(day.get("date"))
            if not d:
                continue
            wk = week_index(self.start, d)
            row = out.setdefault(wk, {"days": 0, "tasks": 0})
            row["days"] += 1
            row["tasks"] += len(day.get("tasks") or [])
        return out

    def subject_list(self):
        if self.subjects:
            return list(self.subjects)
        seen = []
        for _, task in self.iter_tasks():
            subj = task.get("subject") or "未分类"
            if subj not in seen:
                seen.append(subj)
        return seen

    def to_json(self):
        """返回可直接落盘的副本（深拷贝）。"""
        self.data = json.loads(json.dumps(self.data))
        self.data["id"] = self.id
        self.data["name"] = self.name
        self.data["start"] = self.start.strftime(DATE_FMT)
        self.data["end"] = self.end.strftime(DATE_FMT)
        self.data["days"] = self.days
        self.data["subjects"] = self.subject_list()
        self.data["version"] = PLAN_VERSION
        return self.data


class Records(object):
    """一个计划对应一份打卡记录。"""

    def __init__(self, plan_id, data=None):
        self.plan_id = plan_id
        self.data = data or {"version": REC_VERSION, "days": {}}

    @property
    def path(self):
        return os.path.join(paths.PLANS_DIR, "records_%s.json" % self.plan_id)

    @classmethod
    def load(cls, plan_id):
        path = os.path.join(paths.PLANS_DIR, "records_%s.json" % plan_id)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("days", {})
                return cls(plan_id, data)
        except Exception:
            pass
        return cls(plan_id)

    def save(self):
        write_json(self.path, self.data)

    def day(self, date_str):
        row = self.data["days"].setdefault(date_str, {})
        row.setdefault("done", [])
        row.setdefault("all", False)
        row.setdefault("note", "")
        return row

    def is_done(self, date_str, tid):
        return tid in self.data.get("days", {}).get(date_str, {}).get("done", [])

    def toggle(self, date_str, tid):
        row = self.day(date_str)
        if tid in row["done"]:
            row["done"].remove(tid)
        else:
            row["done"].append(tid)
        row["all"] = False
        self.save()
        return tid in row["done"]

    def mark_all(self, date_str, tids, value=True):
        row = self.day(date_str)
        row["done"] = list(tids) if value else []
        row["all"] = bool(value)
        self.save()

    def set_note(self, date_str, text):
        self.day(date_str)["note"] = text or ""
        self.save()

    def note_of(self, date_str):
        return self.data.get("days", {}).get(date_str, {}).get("note", "")

    def done_count(self, date_str):
        return len(self.data.get("days", {}).get(date_str, {}).get("done", []))

    def is_day_complete(self, plan, date_str):
        tasks = plan.tasks_of(date_str)
        if not tasks:
            return False
        done = set(self.data.get("days", {}).get(date_str, {}).get("done", []))
        return all(t.get("id") in done for t in tasks)

    def streak(self, plan, today=None):
        today = today or dt.date.today()
        dates = sorted(plan.dates())
        if not dates:
            return 0, 0
        done_days = [d for d in dates if self.is_day_complete(plan, d.strftime(DATE_FMT))]
        if not done_days:
            return 0, 0
        # 当前连续：从今天（或计划内最后一天）往回数
        pool = set(d.strftime(DATE_FMT) for d in done_days)
        cur = today
        if cur.strftime(DATE_FMT) not in pool:
            earlier = [d for d in done_days if d <= today]
            if not earlier:
                return 0, 0
            cur = earlier[-1]
        run = 0
        while cur.strftime(DATE_FMT) in pool:
            run += 1
            cur -= dt.timedelta(days=1)
        # 历史最长
        best = run
        seq = 0
        prev = None
        for d in done_days:
            if prev and (d - prev).days == 1:
                seq += 1
            else:
                seq = 1
            best = max(best, seq)
            prev = d
        return run, best

    def hours_done(self, plan, subject=None):
        total = 0.0
        for date_str, task in plan.iter_tasks():
            if subject and (task.get("subject") or "未分类") != subject:
                continue
            if self.is_done(date_str, task.get("id")):
                total += float(task.get("hours") or 0)
        return total

    def tasks_done(self, plan):
        n = 0
        for date_str, task in plan.iter_tasks():
            if self.is_done(date_str, task.get("id")):
                n += 1
        return n

    def migrate(self, old_plan, new_plan):
        """把旧记录里仍能在新计划中找到的任务迁移过来。

        返回 (保留条数, 丢失条数)。
        """
        keep, lost = 0, 0
        new_ids = set()
        for date_str, task in new_plan.iter_tasks():
            new_ids.add((date_str, task.get("id")))
        for date_str, day in self.data.get("days", {}).items():
            done = day.get("done") or []
            kept = []
            for tid in done:
                if (date_str, tid) in new_ids:
                    kept.append(tid)
                    keep += 1
                else:
                    lost += 1
            day["done"] = kept
            day["all"] = False
        return keep, lost


class Library(object):
    """多计划管理：index.json + plans/*.json"""

    def __init__(self):
        self.index_path = os.path.join(paths.PLANS_DIR, "index.json")
        self.index = {"version": 1, "current": "", "plans": []}
        self.load()

    def load(self):
        try:
            with open(self.index_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("plans", [])
                data.setdefault("current", "")
                self.index = data
        except Exception:
            pass
        # 清理已删除文件的条目
        alive = []
        for item in self.index["plans"]:
            if os.path.exists(self.plan_path(item.get("id"))):
                alive.append(item)
        if len(alive) != len(self.index["plans"]):
            self.index["plans"] = alive
            if self.index.get("current") not in [p.get("id") for p in alive]:
                self.index["current"] = alive[0]["id"] if alive else ""
            self.save()

    def save(self):
        write_json(self.index_path, self.index)

    @staticmethod
    def plan_path(plan_id):
        return os.path.join(paths.PLANS_DIR, "plan_%s.json" % plan_id)

    def plans(self):
        return list(self.index.get("plans", []))

    def active_plans(self):
        return [p for p in self.plans() if not p.get("archived")]

    def current_id(self):
        return self.index.get("current") or ""

    def set_current(self, plan_id):
        self.index["current"] = plan_id
        self.save()

    def load_plan(self, plan_id=None):
        plan_id = plan_id or self.current_id()
        if not plan_id:
            return None
        try:
            with open(self.plan_path(plan_id), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return Plan(data)
        except Exception:
            return None

    def add_plan(self, plan):
        plan.data["id"] = plan.id
        write_json(self.plan_path(plan.id), plan.to_json())
        entry = {
            "id": plan.id,
            "name": plan.name,
            "start": plan.start.strftime(DATE_FMT),
            "end": plan.end.strftime(DATE_FMT),
            "archived": False,
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        self.index["plans"] = [p for p in self.index["plans"] if p.get("id") != plan.id]
        self.index["plans"].append(entry)
        self.index["current"] = plan.id
        self.save()
        return entry

    def save_plan(self, plan):
        write_json(self.plan_path(plan.id), plan.to_json())
        for item in self.index["plans"]:
            if item.get("id") == plan.id:
                item["name"] = plan.name
                item["start"] = plan.start.strftime(DATE_FMT)
                item["end"] = plan.end.strftime(DATE_FMT)
        self.save()

    def archive(self, plan_id, archived=True):
        for item in self.index["plans"]:
            if item.get("id") == plan_id:
                item["archived"] = bool(archived)
        self.save()

    def rename(self, plan_id, name):
        for item in self.index["plans"]:
            if item.get("id") == plan_id:
                item["name"] = name
        plan = self.load_plan(plan_id)
        if plan:
            plan.name = name
            self.save_plan(plan)

    def delete(self, plan_id):
        for path in (self.plan_path(plan_id),
                     os.path.join(paths.PLANS_DIR, "records_%s.json" % plan_id)):
            try:
                os.remove(path)
            except Exception:
                pass
        self.index["plans"] = [p for p in self.index["plans"] if p.get("id") != plan_id]
        if self.index.get("current") == plan_id:
            rest = self.index["plans"]
            self.index["current"] = rest[0]["id"] if rest else ""
        self.save()


def write_json(path, obj):
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def new_plan_id():
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    salt = hashlib.sha1(stamp.encode()).hexdigest()[:4]
    return "%s%s" % (stamp, salt)
