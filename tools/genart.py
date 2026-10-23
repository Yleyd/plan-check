# -*- coding: utf-8 -*-
"""程序化生成内置背景图（纯代码绘制，无第三方素材，可自由分发）。

用法：
    python tools/genart.py [输出目录]

默认输出到 assets/default/，生成 6 张 1920x1080 的 JPEG。
运行期软件不会 import 这个文件，它只是打包前的素材生成器。
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080


# ------------------------------------------------------------------ 基础工具
def lerp(a, b, t):
    return a + (b - a) * t


def vgrad(w, h, stops):
    """竖向多段渐变。stops = [(位置0-1, (r,g,b)), ...]"""
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    out = np.zeros((h, 3), dtype=np.float32)
    stops = sorted(stops, key=lambda s: s[0])
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        mask = (ys >= p0) & (ys <= p1)
        if not mask.any():
            continue
        t = (ys[mask] - p0) / max(1e-6, (p1 - p0))
        for ch in range(3):
            out[mask, ch] = c0[ch] + (c1[ch] - c0[ch]) * t
    out[ys < stops[0][0]] = stops[0][1]
    out[ys > stops[-1][0]] = stops[-1][1]
    return np.repeat(out[:, None, :], w, axis=1)


def diag_grad(w, h, c0, c1, angle=35.0):
    """斜向渐变。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle)
    t = (xx * math.cos(a) + yy * math.sin(a))
    t = (t - t.min()) / max(1e-6, (t.max() - t.min()))
    t = t[..., None]
    return np.array(c0, dtype=np.float32) * (1 - t) + np.array(c1, dtype=np.float32) * t


def radial(w, h, cx, cy, rx, ry, power=2.0):
    """椭圆径向衰减 0-1（中心 1）。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - cx) / max(1e-6, rx)) ** 2 + ((yy - cy) / max(1e-6, ry)) ** 2)
    d = np.clip(1.0 - d, 0.0, 1.0) ** power
    return d[..., None]


def add_glow(base, cx, cy, rx, ry, color, strength=1.0, power=2.2):
    g = radial(base.shape[1], base.shape[0], cx, cy, rx, ry, power)
    return base + g * np.array(color, dtype=np.float32) * strength


def screen(base, layer):
    a = np.clip(base / 255.0, 0, 1)
    b = np.clip(layer / 255.0, 0, 1)
    return (1.0 - (1.0 - a) * (1.0 - b)) * 255.0


def ribbon(base, y0, amp, freq, phase, thick, color, alpha=0.55, blur=26):
    """一条正弦光带（在独立图层上画，再模糊叠加）。"""
    h, w = base.shape[0], base.shape[1]
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    pts = []
    for x in range(0, w + 8, 8):
        t = x / float(w)
        y = y0 + amp * math.sin(t * freq * math.tau + phase) + \
            amp * 0.35 * math.sin(t * freq * 2.7 * math.tau + phase * 1.7)
        pts.append((x, y))
    d.line(pts, fill=int(255 * alpha), width=int(thick), joint="curve")
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(layer, dtype=np.float32)[..., None] / 255.0
    return base + m * np.array(color, dtype=np.float32)


def bokeh(base, seed, count=46, color=(190, 220, 255), rmin=3, rmax=26, alpha=0.5):
    h, w = base.shape[0], base.shape[1]
    rng = np.random.default_rng(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        cx = rng.uniform(0, w)
        cy = rng.uniform(0, h)
        r = rng.uniform(rmin, rmax)
        a = int(255 * alpha * rng.uniform(0.25, 1.0))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)
    layer = layer.filter(ImageFilter.GaussianBlur(2.2))
    m = np.asarray(layer, dtype=np.float32)[..., None] / 255.0
    return base + m * np.array(color, dtype=np.float32)


def streaks(base, seed, count=22, color=(120, 190, 255), alpha=0.28, blur=8):
    """竖向细光条。"""
    h, w = base.shape[0], base.shape[1]
    rng = np.random.default_rng(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        x = rng.uniform(0, w)
        wd = rng.uniform(1, 4)
        y0 = rng.uniform(-0.2, 0.5) * h
        y1 = y0 + rng.uniform(0.15, 0.7) * h
        d.rectangle([x, y0, x + wd, y1], fill=int(255 * alpha * rng.uniform(0.3, 1.0)))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(layer, dtype=np.float32)[..., None] / 255.0
    return base + m * np.array(color, dtype=np.float32)


def grid(base, step=96, color=(110, 150, 220), alpha=0.10, blur=0.8):
    h, w = base.shape[0], base.shape[1]
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    a = int(255 * alpha)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=a, width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=a, width=1)
    if blur:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(layer, dtype=np.float32)[..., None] / 255.0
    return base + m * np.array(color, dtype=np.float32)


def ring(base, cx, cy, radius, thick, color, strength=1.0, blur=30, glow=1.0):
    """一圈发光环。"""
    h, w = base.shape[0], base.shape[1]
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              outline=int(255 * strength), width=int(thick))
    if blur:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(layer, dtype=np.float32)[..., None] / 255.0
    out = base + m * np.array(color, dtype=np.float32) * glow
    return out


def vignette(base, strength=0.55, power=1.4):
    h, w = base.shape[0], base.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2.0) / (w / 2.0)
    ny = (yy - h / 2.0) / (h / 2.0)
    d = np.sqrt(nx * nx + ny * ny) / math.sqrt(2.0)
    m = np.clip(d ** power, 0, 1) * strength
    return base * (1.0 - m[..., None])


def grain(base, seed, amount=3.2):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, amount, base.shape[:2])[..., None]
    return base + n


def to_image(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ 六张图
def art_night(seed=11):
    """深蓝极光：适合「今日」页。"""
    base = vgrad(W, H, [(0.0, (8, 14, 34)), (0.42, (12, 26, 62)),
                        (0.72, (16, 40, 92)), (1.0, (5, 9, 20))])
    base = add_glow(base, W * 0.30, H * 0.20, W * 0.55, H * 0.45, (30, 92, 170), 0.85)
    base = add_glow(base, W * 0.80, H * 0.72, W * 0.45, H * 0.40, (96, 60, 190), 0.55)
    base = ribbon(base, H * 0.34, H * 0.10, 1.15, 0.4, 120, (70, 150, 255), 0.42, 34)
    base = ribbon(base, H * 0.52, H * 0.07, 1.6, 2.1, 70, (120, 200, 255), 0.30, 22)
    base = streaks(base, seed, 26, (130, 200, 255), 0.22)
    base = bokeh(base, seed + 1, 54, (200, 228, 255), 3, 22, 0.45)
    base = vignette(base, 0.50)
    base = grain(base, seed, 3.0)
    return to_image(base)


def art_ring(seed=21):
    """紫光环：启动画面用。"""
    base = vgrad(W, H, [(0.0, (10, 8, 28)), (0.40, (26, 16, 62)),
                        (0.70, (44, 26, 96)), (1.0, (8, 6, 20))])
    base = add_glow(base, W * 0.50, H * 0.52, W * 0.42, H * 0.55, (86, 60, 190), 0.95)
    base = add_glow(base, W * 0.18, H * 0.78, W * 0.40, H * 0.42, (28, 60, 150), 0.70)
    base = add_glow(base, W * 0.86, H * 0.22, W * 0.34, H * 0.36, (170, 70, 210), 0.55)
    cx, cy = W * 0.56, H * 0.50
    base = ring(base, cx, cy, H * 0.30, 5, (150, 120, 255), 0.55, 40, 0.9)
    base = ring(base, cx, cy, H * 0.30, 2, (210, 190, 255), 0.75, 10, 1.0)
    base = ring(base, cx, cy, H * 0.42, 2, (120, 160, 255), 0.22, 60, 0.7)
    base = ribbon(base, H * 0.50, H * 0.045, 1.0, 1.2, 90, (190, 150, 255), 0.45, 30)
    base = bokeh(base, seed, 64, (225, 210, 255), 2, 20, 0.42)
    base = vignette(base, 0.58)
    base = grain(base, seed, 3.2)
    return to_image(base)


def art_hat(seed=31):
    """紫蓝星云：适合「日历」页。"""
    base = vgrad(W, H, [(0.0, (12, 10, 32)), (0.45, (30, 22, 70)),
                        (0.75, (22, 34, 86)), (1.0, (7, 8, 20))])
    base = add_glow(base, W * 0.72, H * 0.30, W * 0.46, H * 0.48, (110, 70, 200), 0.80)
    base = add_glow(base, W * 0.22, H * 0.62, W * 0.42, H * 0.44, (40, 90, 180), 0.65)
    base = grid(base, 120, (120, 140, 230), 0.055, 1.0)
    base = ribbon(base, H * 0.68, H * 0.06, 0.85, 3.4, 110, (140, 110, 240), 0.34, 34)
    base = bokeh(base, seed, 70, (215, 205, 255), 2, 16, 0.40)
    base = streaks(base, seed + 2, 16, (160, 140, 255), 0.18)
    base = vignette(base, 0.52)
    base = grain(base, seed, 3.0)
    return to_image(base)


def art_clash(seed=41):
    """冷蓝与玫红对撞：适合「设置」页。"""
    base = diag_grad(W, H, (10, 18, 44), (46, 14, 40), 28.0)
    base = add_glow(base, W * 0.22, H * 0.30, W * 0.46, H * 0.50, (40, 120, 220), 0.95)
    base = add_glow(base, W * 0.80, H * 0.70, W * 0.44, H * 0.48, (210, 60, 130), 0.80)
    base = add_glow(base, W * 0.52, H * 0.50, W * 0.26, H * 0.30, (140, 90, 255), 0.55)
    base = ribbon(base, H * 0.46, H * 0.08, 0.9, 0.0, 140, (255, 140, 200), 0.26, 40)
    base = streaks(base, seed, 20, (200, 220, 255), 0.20)
    base = bokeh(base, seed, 50, (255, 225, 240), 2, 20, 0.38)
    base = vignette(base, 0.55)
    base = grain(base, seed, 3.2)
    return to_image(base)


def art_flame(seed=51):
    """青绿流光：备用（青焰）。"""
    base = vgrad(W, H, [(0.0, (6, 20, 24)), (0.42, (10, 44, 52)),
                        (0.72, (12, 66, 78)), (1.0, (4, 10, 14))])
    base = add_glow(base, W * 0.62, H * 0.34, W * 0.44, H * 0.48, (24, 150, 160), 0.85)
    base = add_glow(base, W * 0.20, H * 0.74, W * 0.40, H * 0.42, (30, 90, 140), 0.60)
    base = ribbon(base, H * 0.42, H * 0.09, 1.35, 1.8, 110, (90, 240, 220), 0.40, 30)
    base = ribbon(base, H * 0.60, H * 0.05, 1.9, 0.6, 60, (170, 255, 240), 0.26, 20)
    base = bokeh(base, seed, 48, (200, 255, 245), 2, 18, 0.38)
    base = vignette(base, 0.52)
    base = grain(base, seed, 3.0)
    return to_image(base)


def art_eye(seed=61):
    """同心蓝环：备用。"""
    base = vgrad(W, H, [(0.0, (6, 12, 30)), (0.45, (10, 30, 72)),
                        (0.75, (14, 46, 104)), (1.0, (4, 8, 18))])
    base = add_glow(base, W * 0.50, H * 0.50, W * 0.40, H * 0.52, (30, 110, 210), 0.90)
    for i, r in enumerate((0.16, 0.24, 0.33, 0.43)):
        base = ring(base, W * 0.50, H * 0.50, H * r, 3,
                    (90, 190, 255), 0.45 - i * 0.07, 26, 0.85)
    base = bokeh(base, seed, 40, (190, 235, 255), 2, 14, 0.35)
    base = vignette(base, 0.56)
    base = grain(base, seed, 3.0)
    return to_image(base)


ARTS = {
    "gen_night.jpg": art_night,
    "gen_ring.jpg": art_ring,
    "gen_hat.jpg": art_hat,
    "gen_clash.jpg": art_clash,
    "gen_flame.jpg": art_flame,
    "gen_eye.jpg": art_eye,
}


def build(out_dir, quality=92):
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for name, fn in ARTS.items():
        im = fn()
        path = os.path.join(out_dir, name)
        im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
        made.append((name, os.path.getsize(path)))
    return made


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "default")
    for name, size in build(target):
        print("%-18s %8.1f KB" % (name, size / 1024.0))
    print("输出目录:", target)
