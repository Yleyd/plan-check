"""用户设置：窗口大小位置、字体档位、背景图映射、上次目录等。"""
import json
import os

from .. import paths

DEFAULTS = {
    "version": 1,
    "win": {"w": 1280, "h": 840, "x": -1, "y": -1},
    "font_size": "medium",
    "start_art": "gen_ring",
    "page_art": {"today": "gen_night", "prog": "gen_ring",
                 "cal": "gen_hat", "set": "gen_clash"},
    "last_import_dir": "",
    "last_export_dir": "",
    "last_template_dir": "",
    "global_note": "",
    "show_splash": True,
    # 用户自选背景图：{图 key: USER_ASSETS 下的文件名}。
    # 必须出现在 DEFAULTS 里，否则 load() 的「只收已知键」逻辑会把它丢掉，
    # 表现为「换完图当次生效，重启又变回初始背景」。
    "custom_art": {},
}

PAGES = ["today", "prog", "cal", "set"]
PAGE_NAMES = {"today": "今日", "prog": "进度", "cal": "日历", "set": "设置"}


class Settings(object):
    def __init__(self):
        self.path = os.path.join(paths.DATA_DIR, "settings.json")
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in self.data:
                        if isinstance(self.data[key], dict) and isinstance(value, dict):
                            self.data[key].update(value)
                        else:
                            self.data[key] = value
        except Exception:
            pass
        # 修正非法值
        if self.data.get("font_size") not in ("small", "medium", "large"):
            self.data["font_size"] = "medium"
        # 1.0.1 及更早版本的默认值是内置插画，1.0.2 换成了程序生成的原创图。
        # 只迁移「还是默认值」的情况，用户自己选过的保持不动。
        legacy = {"night": "gen_night", "ring": "gen_ring", "hat": "gen_hat",
                  "clash": "gen_clash", "flame": "gen_flame", "eye": "gen_eye"}
        if self.data.get("start_art") in legacy:
            self.data["start_art"] = legacy[self.data["start_art"]]
        page_art = self.data.get("page_art") or {}
        for page in PAGES:
            if page not in page_art:
                page_art[page] = DEFAULTS["page_art"][page]
            elif page_art[page] in legacy:
                page_art[page] = legacy[page_art[page]]
        self.data["page_art"] = page_art

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # ---- 窗口 ----
    def win(self):
        return self.data.get("win") or dict(DEFAULTS["win"])

    def set_win(self, w, h, x, y):
        self.data["win"] = {"w": int(w), "h": int(h), "x": int(x), "y": int(y)}
        self.save()

    # ---- 字体 ----
    def scale(self):
        from .. import theme
        return theme.SIZES.get(self.data.get("font_size", "medium"), 1.0)

    # ---- 背景图 ----
    def art_of(self, page):
        return (self.data.get("page_art") or {}).get(page) or DEFAULTS["page_art"][page]

    def set_art(self, page, key):
        self.data.setdefault("page_art", {})[page] = key
        self.save()
