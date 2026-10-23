"""图像处理：底图加载、磨砂、玻璃卡片、右侧插画栏。

所有函数都是纯 PIL，不碰 Tk；调用方负责把结果塞进 PhotoImage。
"""
import os

from .. import paths, theme

# 前 6 个是程序生成的原创图（tools/genart.py），可自由分发；
# 后 6 个是早期内置插画，保留是为了兼容老用户的设置文件。
ART_FILES = {
    "gen_night": "gen_night.jpg",
    "gen_ring": "gen_ring.jpg",
    "gen_hat": "gen_hat.jpg",
    "gen_clash": "gen_clash.jpg",
    "gen_flame": "gen_flame.jpg",
    "gen_eye": "gen_eye.jpg",
    "night": "art_night.jpg",
    "ring": "art_ring.jpg",
    "hat": "art_hat.jpg",
    "clash": "art_clash.jpg",
    "flame": "art_flame.jpg",
    "eye": "art_eye.jpg",
}

ART_NAMES = {
    "gen_night": "极光·蓝",
    "gen_ring": "光环·紫",
    "gen_hat": "星云·紫",
    "gen_clash": "对撞·青红",
    "gen_flame": "流光·青",
    "gen_eye": "同心环·蓝",
    "night": "蓝眼少女",
    "ring": "紫光环",
    "hat": "紫帽单眼",
    "clash": "红蓝对撞",
    "flame": "青焰女仆",
    "eye": "蓝瞳数据",
}

# 只展示程序生成的原创图（可自由分发）；早期插画已移到 assets/original，
# 不再打包进安装包，但仍保留 ART_FILES 映射，便于老配置文件里的 key 正常回退。
ART_ORDER = ["gen_night", "gen_ring", "gen_hat", "gen_clash", "gen_flame",
             "gen_eye"]

# 老 key -> 同主题的生成图，用于老配置文件的兜底
_LEGACY_TO_GEN = {
    "night": "gen_night", "ring": "gen_ring", "hat": "gen_hat",
    "clash": "gen_clash", "flame": "gen_flame", "eye": "gen_eye",
}

# 页面 key -> 默认图 key。custom_art 里老版本存的是页面 key（today/prog/...），
# 新版本统一存图 key（gen_night/...），这里用于双向兼容。
_PAGE_TO_ART_KEY = {
    "today": "gen_night", "prog": "gen_ring", "cal": "gen_hat",
    "set": "gen_clash", "splash": "gen_ring",
}
_ART_KEY_TO_PAGE = dict((v, k) for k, v in _PAGE_TO_ART_KEY.items())


def page_to_art_key(page_key, default=None):
    """把页面 key 换成图 key；已经是图 key 就原样返回。"""
    if page_key in ART_FILES:
        return page_key
    if page_key in _PAGE_TO_ART_KEY:
        return _PAGE_TO_ART_KEY[page_key]
    return default or "gen_night"


_PIL = None
_IMAGE = None
_DRAW = None
_FONT = None


def pil():
    """惰性导入 PIL，返回 (Image, ImageDraw, ImageFilter, ImageFont, ImageOps)。"""
    global _PIL, _IMAGE, _DRAW, _FONT
    if _PIL is None:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
        _PIL = (Image, ImageDraw, ImageFilter, ImageFont, ImageOps)
    return _PIL


_IMAGETK = None


def photo(im):
    """把 PIL 图转成 Tk 可用的 PhotoImage（惰性导入 ImageTk）。"""
    global _IMAGETK
    if _IMAGETK is None:
        from PIL import ImageTk
        _IMAGETK = ImageTk
    return _IMAGETK.PhotoImage(im)


# 用户在「换背景图」里选的本地图片：{页面 key: 文件名}。
# 由 App 启动时和换图后写入（避免 art 反向依赖 core.settings 造成循环导入）。
_CUSTOM = {}


def set_custom_map(mapping):
    """mapping 的 key 可以是「图 key」(gen_night) 也可以是「页面 key」(today)。

    历史原因两种都出现过，这里统一按图 key 存，同时保留页面 key 的别名，
    避免老配置（1.0.2 及之前写的是页面 key）失效。
    """
    global _CUSTOM
    raw = dict(mapping or {})
    resolved = {}
    for key, name in raw.items():
        resolved[key] = name
        # 页面 key → 对应的图 key，让 art_path 两个方向都能查到
        for pkey, ikey in _PAGE_TO_ART_KEY.items():
            if key == pkey and ikey not in resolved:
                resolved[ikey] = name
    _CUSTOM = resolved
    clear_art_cache()


def art_path(key):
    """自定义图优先，其次用户目录同名图，最后内置默认图。"""
    key = page_to_art_key(key) if key not in ART_FILES else key
    custom = _CUSTOM.get(key)
    if custom:
        p = os.path.join(paths.USER_ASSETS, custom)
        if os.path.exists(p):
            return p
    name = ART_FILES.get(key)
    if not name:
        return None
    user = os.path.join(paths.USER_ASSETS, name)
    if os.path.exists(user):
        return user
    default = os.path.join(paths.DEFAULT_ASSETS, name)
    if os.path.exists(default):
        return default
    # 老版本配置里的 key（night/ring/...）在 1.0.2 已不再内置，
    # 回退到同主题的生成图，避免退化成纯色块。
    fallback = _LEGACY_TO_GEN.get(key)
    if fallback:
        name2 = ART_FILES.get(fallback)
        if name2:
            p2 = os.path.join(paths.DEFAULT_ASSETS, name2)
            if os.path.exists(p2):
                return p2
    return None


_ART_CACHE = {}


def load_art(key):
    """返回 RGB 图（带缓存）；找不到返回纯色底图。"""
    if key in _ART_CACHE:
        return _ART_CACHE[key]
    Image = pil()[0]
    path = art_path(key)
    if path:
        try:
            im = Image.open(path)
            im = pil()[4].exif_transpose(im)
            im = im.convert("RGB")
        except Exception:
            im = Image.new("RGB", (1600, 900), theme.hex_rgb(theme.BG2))
    else:
        im = Image.new("RGB", (1600, 900), theme.hex_rgb(theme.BG2))
    _ART_CACHE[key] = im
    return im


def clear_art_cache(key=None):
    """清原图缓存，同时清页面底图缓存。

    只清 _ART_CACHE 是不够的：page_art 的签名是 (key,w,h,dark,blur)，
    换图后这些参数都没变，会直接命中 _PAGE_CACHE 返回旧图 —— 这就是
    「换背景图没反应」的第二层原因。
    """
    if key is None:
        _ART_CACHE.clear()
        _PAGE_CACHE.clear()
    else:
        _ART_CACHE.pop(key, None)
        for sig in list(_PAGE_CACHE.keys()):
            if sig and sig[0] == key:
                _PAGE_CACHE.pop(sig, None)


def cover_fit(im, w, h, fx=0.5, fy=0.5):
    """等比缩放到铺满 (w,h)，再按焦点裁切。"""
    if w <= 0 or h <= 0:
        return im.resize((max(1, w), max(1, h)))
    src_w, src_h = im.size
    scale = max(float(w) / src_w, float(h) / src_h)
    nw, nh = int(src_w * scale + 0.5), int(src_h * scale + 0.5)
    resized = im.resize((max(1, nw), max(1, nh)))
    left = int((nw - w) * max(0.0, min(1.0, fx)))
    top = int((nh - h) * max(0.0, min(1.0, fy)))
    left = max(0, min(nw - w, left))
    top = max(0, min(nh - h, top))
    return resized.crop((left, top, left + w, top + h))


def _hex(value):
    return theme.hex_rgb(value)


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = _hex(c1) if isinstance(c1, str) else c1
    b = _hex(c2) if isinstance(c2, str) else c2
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def avg_of(im, box):
    """取区域平均色。"""
    Image = pil()[0]
    w = max(1, box[2] - box[0])
    h = max(1, box[3] - box[1])
    crop = im.crop((box[0], box[1], box[0] + w, box[1] + h))
    tiny = crop.resize((1, 1), Image.BOX)
    return tiny.getpixel((0, 0))


def luma(im, box):
    """区域平均亮度 0-255。"""
    Image = pil()[0]
    w = max(1, box[2] - box[0])
    h = max(1, box[3] - box[1])
    crop = im.crop((box[0], box[1], box[0] + w, box[1] + h)).convert("L")
    return crop.resize((1, 1), Image.BOX).getpixel((0, 0))


_PAGE_CACHE = {}


def _art_stamp(key):
    """图文件的 (路径, mtime, 大小) 指纹，用于让页面底图缓存能感知换图。"""
    try:
        p = art_path(key)
        if not p:
            return ("", 0, 0)
        st = os.stat(p)
        return (p, int(st.st_mtime), st.st_size)
    except Exception:
        return ("", 0, 0)


def page_art(key, w, h, dark=0.42, blur=None):
    """页面底图：铺满 + 模糊 + 压暗 + 双光晕 + 暗角。"""
    # 签名带上图文件指纹：换图后即使 key/w/h 不变也不会命中旧缓存
    sig = (key, w, h, round(dark, 3), blur, _art_stamp(key))
    if sig in _PAGE_CACHE:
        return _PAGE_CACHE[sig].copy()

    Image, ImageDraw, ImageFilter = pil()[0], pil()[1], pil()[2]
    if blur is None:
        blur = max(3.0, w / 300.0)
    base = cover_fit(load_art(key), w, h, fx=0.5, fy=0.42)
    base = base.filter(ImageFilter.GaussianBlur(blur))

    # 压暗
    dark_layer = Image.new("RGB", (w, h), _hex(theme.BG))
    base = Image.blend(base, dark_layer, dark)

    # 两个光晕：左上偏冷、右下偏紫
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-w * 0.25, -h * 0.45, w * 0.62, h * 0.55], fill=(30, 78, 130))
    gd.ellipse([w * 0.45, h * 0.42, w * 1.25, h * 1.35], fill=(64, 42, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(max(40, w / 12)))
    base = Image.blend(base, glow, 0.30)

    # 暗角
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-w * 0.18, -h * 0.30, w * 1.18, h * 1.30], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(60, w / 8)))
    vign = Image.new("RGB", (w, h), (0, 0, 0))
    base = Image.composite(base, Image.blend(base, vign, 0.55), mask)

    _PAGE_CACHE[sig] = base
    return base.copy()


def art_column(base, key, w, h, col, dark=0.10, blur=1.0, fade=110):
    """在右侧贴一条竖构图插画，左缘渐隐。"""
    if col <= 0:
        return base
    Image, ImageDraw, ImageFilter = pil()[0], pil()[1], pil()[2]
    strip = cover_fit(load_art(key), col, h, fx=0.5, fy=0.34)
    if blur:
        strip = strip.filter(ImageFilter.GaussianBlur(blur))
    if dark:
        strip = Image.blend(strip, Image.new("RGB", (col, h), _hex(theme.BG)), dark)

    # 左缘渐隐遮罩
    mask = Image.new("L", (col, h), 255)
    md = ImageDraw.Draw(mask)
    fade = max(1, min(col // 2, int(fade)))
    for x in range(fade):
        value = int(255 * (float(x) / fade) ** 1.6)
        md.line([(x, 0), (x, h)], fill=value)
    out = base.copy()
    out.paste(strip, (w - col, 0), mask)
    return out


def hero_image(key, w, h):
    """设置页整屏图：铺满 + 轻微压暗 + 四角暗角 + 中心柔光。"""
    Image, ImageDraw, ImageFilter = pil()[0], pil()[1], pil()[2]
    im = cover_fit(load_art(key), w, h, fx=0.5, fy=0.46)
    # 只轻微压暗，让底图看得见；真正的可读性靠中心那块柔光
    im = Image.blend(im, Image.new("RGB", (w, h), _hex(theme.BG)), 0.10)

    # 中心柔光（让文字浮起来）
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = w * 0.5, h * 0.50
    gd.ellipse([cx - w * 0.34, cy - h * 0.34, cx + w * 0.34, cy + h * 0.34],
               fill=(6, 10, 18))
    glow = glow.filter(ImageFilter.GaussianBlur(max(40, w / 32.0)))
    im = Image.blend(im, glow, 0.34)

    # 四角暗角（弱一点，别把画面压死）
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-w * 0.20, -h * 0.32, w * 1.20, h * 1.32], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(50, w / 9.0)))
    vign = Image.new("RGB", (w, h), (0, 0, 0))
    im = Image.composite(im, Image.blend(im, vign, 0.42), mask)
    return im


def _round_mask(w, h, radius):
    Image, ImageDraw = pil()[0], pil()[1]
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return mask


def glass_panel(base, box, radius=18, alpha=0.58, tint=None, border=None):
    """在底图上画一块圆角玻璃，圆角外保留原像素。"""
    Image, ImageDraw = pil()[0], pil()[1]
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2:
        return base
    x0 = max(0, min(base.width - 2, x0))
    y0 = max(0, min(base.height - 2, y0))
    x1 = max(x0 + 2, min(base.width, x1))
    y1 = max(y0 + 2, min(base.height, y1))
    w, h = x1 - x0, y1 - y0
    radius = max(1, min(radius, min(w, h) // 2))

    region = base.crop((x0, y0, x1, y1)).convert("RGB")
    fill_color = tint or theme.GLASS
    tint_layer = Image.new("RGB", (w, h), _hex(fill_color) if isinstance(fill_color, str) else fill_color)
    region = Image.blend(region, tint_layer, alpha)

    # 顶部高光
    sheen = Image.new("RGB", (w, h), (255, 255, 255))
    smask = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(smask)
    sd.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=0)
    sd.rectangle([0, 0, w - 1, max(1, h // 2)], fill=16)
    smask = Image.composite(smask, Image.new("L", (w, h), 0), _round_mask(w, h, radius))
    region = Image.composite(Image.blend(region, sheen, 0.5), region, smask)

    mask = _round_mask(w, h, radius)
    out = base.copy()
    out.paste(region, (x0, y0), mask)

    if border:
        draw = ImageDraw.Draw(out)
        draw.rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=radius,
                               outline=border if not isinstance(border, tuple) else border,
                               width=1)
    return out


def add_shadow(im, rects, blur=14, alpha=120, dy=8, radius=18):
    """给一组圆角矩形加投影（叠在原图上）。"""
    Image, ImageDraw, ImageFilter = pil()[0], pil()[1], pil()[2]
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for box in rects:
        x0, y0, x1, y1 = box
        ld.rounded_rectangle([x0, y0 + dy, x1, y1 + dy], radius=radius,
                             fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    out = im.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def darken_band(im, top_from, top_to, strength=120, axis="y"):
    """在图片某段做竖向压暗（用于保证文字可读）。"""
    Image, ImageDraw = pil()[0], pil()[1]
    w, h = im.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    steps = 48
    for i in range(steps):
        y0 = top_from + (top_to - top_from) * i / float(steps)
        y1 = top_from + (top_to - top_from) * (i + 1) / float(steps)
        a = int(strength * (1.0 - i / float(steps)))
        ld.rectangle([0, int(y0), w, int(y1) + 1], fill=(0, 0, 0, a))
    out = im.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")
