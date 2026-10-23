"""配色与字体。深色磨砂主题。"""

# ---- 底色 ----
BG = "#070B18"
BG2 = "#0B1120"
GLASS = "#121A2A"
GLASS_SOFT = "#0E1727"
FOOT_BG = "#060A12"

# ---- 文字 ----
TEXT = "#E8EEF9"
SUB = "#A9B6CC"
MUTED = "#7C88A0"
DIM = "#5A6478"

# ---- 强调 ----
ACCENT = "#4DA3FF"
CYAN = "#7FE7FF"
PURPLE = "#A78BFA"
OK = "#4ADE80"
WARN = "#FBBF24"
DANGER = "#F87171"

LINE = "#22304A"
LINE_SOFT = "#1A2438"

# ---- 科目调色板（按顺序循环）----
PALETTE = [
    "#4DA3FF", "#A78BFA", "#4ADE80", "#FBBF24", "#F87171",
    "#22D3EE", "#F472B6", "#A3E635", "#FB923C", "#818CF8",
]

FONT = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

# 三档字号：以 base 为单位缩放
SIZES = {"small": 0.90, "medium": 1.0, "large": 1.12}


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def subject_color(index):
    return PALETTE[index % len(PALETTE)]


def mix_track():
    return "#1B2438"


def mix_primary():
    return "#3B8BE8"


def mix_soft(color, t=0.18):
    """把强调色混进底色，得到浅色底。"""
    c = hex_rgb(color)
    b = hex_rgb(GLASS)
    return "#%02X%02X%02X" % tuple(int(b[i] + (c[i] - b[i]) * t) for i in range(3))


def star_text(star):
    if not star:
        return ""
    try:
        n = int(star)
    except Exception:
        return ""
    return "★" * max(0, min(5, n))


def hours_text(hours):
    if hours is None:
        return ""
    try:
        value = float(hours)
    except Exception:
        return ""
    if abs(value - round(value)) < 1e-6:
        return "%d h" % int(round(value))
    return "%.1f h" % value
