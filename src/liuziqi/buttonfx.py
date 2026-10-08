# -*- coding: utf-8 -*-
"""
buttonfx.py —— 玻璃质感按钮渲染器（PIL 超采样 + 真 Alpha 合成）。

为什么需要它
------------
Tk Canvas 既不支持抗锯齿，也不支持 Alpha 合成：

  * create_polygon 画圆角矩形只能用整数坐标顶点去拟合弧线，边缘呈阶梯状
    锯齿 —— 这就是「按钮边缘模糊 / 发毛」的根本原因，无论顶点取多密都无法
    消除（Tk 的多边形填充不做边缘覆盖度计算）。
  * 「通透感」所必需的半透明高光、柔化投影、外发光，Tk 只能用不透明色块
    近似叠加，层数一多就越来越浑浊，反而更糊。

方案
----
改用 PIL 在 SS 倍（默认 4×）超采样画布上，以**真 Alpha 通道**逐层合成：

     1  环境阴影        2  投射阴影       3  悬停外发光
     4  立体侧壁        5  主体渐变       6  玻璃 sheen（上半高光）
     7  底部内缘透光    8  镜面反光斑     9  内斜角环（上亮 / 下柔）
    10  按下内阴影     11  清晰描边      12  文字（真字体渲染 + 文字阴影）

最后用 LANCZOS 降采样回原始尺寸。得到的是**真正的抗锯齿平滑边缘**与
**真正的半透明叠加**，因此既锐利又通透。
"""

from __future__ import annotations

# ------------------------------------------------------------------ 依赖探测
_PIL_OK = False
try:
    from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont
    _PIL_OK = True
except Exception:                                    # pragma: no cover
    Image = ImageDraw = ImageFilter = ImageChops = ImageFont = None

_TK_OK = False
try:
    from PIL import ImageTk
    _TK_OK = True
except Exception:                                    # pragma: no cover
    ImageTk = None


SS = 4          # 超采样倍数（4× 在清晰度与性能间取得平衡）
_MAX_CACHE = 900

_CACHE: dict = {}
_TK_SCALE = [None]      # 缓存 tk scaling（每个解释器只算一次）


# ------------------------------------------------------------------ 颜色工具
def _parse(color):
    c = (color or "#000000").lstrip("#")
    if len(c) == 3:
        c = c[0] * 2 + c[1] * 2 + c[2] * 2
    try:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    except Exception:
        return (0, 0, 0)


def _hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(c1, c2, t):
    a, b = _parse(c1), _parse(c2)
    return _hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def shade(c, factor):
    r, g, b = _parse(c)
    return _hex((r * factor, g * factor, b * factor))


def _lum(c):
    r, g, b = _parse(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


# ------------------------------------------------------------------ 形状遮罩
def _shape(size, box, r, inset=0.0):
    """L 模式圆角矩形遮罩。inset 为内缩像素（超采样坐标系）。"""
    m = Image.new("L", size, 0)
    x0, y0, x1, y1 = box
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    if x1 <= x0 or y1 <= y0:
        return m
    rr = max(0.0, min(float(r), (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    ImageDraw.Draw(m).rounded_rectangle([x0, y0, x1, y1], radius=rr, fill=255)
    return m


def _grad_l(size, box, stops):
    """垂直渐变遮罩（L 模式）。stops = [(位置0..1, 亮度0..255), ...]。"""
    img = Image.new("L", size, 0)
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    vals = []
    for i in range(h):
        t = i / (h - 1) if h > 1 else 0.0
        v = stops[0][1]
        for k in range(len(stops) - 1):
            p0, v0 = stops[k]
            p1, v1 = stops[k + 1]
            if t <= p1 or k == len(stops) - 2:
                r = 0.0 if p1 <= p0 else (t - p0) / (p1 - p0)
                r = max(0.0, min(1.0, r))
                v = v0 + (v1 - v0) * r
                break
        vals.append(max(0, min(255, int(round(v)))))
    strip = Image.new("L", (1, h))
    strip.putdata(vals)
    img.paste(strip.resize((w, h), Image.NEAREST), (x0, y0))
    return img


def _grad_rgba(size, box, stops):
    """垂直渐变彩色图层（RGBA）。stops = [(位置0..1, "#RRGGBB"), ...]。"""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    vals = []
    for i in range(h):
        t = i / (h - 1) if h > 1 else 0.0
        col = stops[0][1]
        for k in range(len(stops) - 1):
            p0, c0 = stops[k]
            p1, c1 = stops[k + 1]
            if t <= p1 or k == len(stops) - 2:
                r = 0.0 if p1 <= p0 else (t - p0) / (p1 - p0)
                r = max(0.0, min(1.0, r))
                col = mix(c0, c1, r)
                break
        vals.append(_parse(col))
    strip = Image.new("RGB", (1, h))
    strip.putdata(vals)
    layer.paste(strip.resize((w, h), Image.NEAREST), (x0, y0))
    return layer


def _tint(mask, color, alpha=255, blur=0.0):
    """把 L 遮罩变成纯色 RGBA 图层；alpha 为整体不透明度(0..255)。"""
    layer = Image.new("RGBA", mask.size, _parse(color) + (0,))
    a = mask
    if alpha < 255:
        a = a.point(lambda v: int(v * alpha / 255))
    layer.putalpha(a)
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return layer


def _over(base, layer):
    return Image.alpha_composite(base, layer)


def _mul(a, b):
    return ImageChops.multiply(a, b)


# ------------------------------------------------------------------ 字体解析
_FONT_CACHE: dict = {}
_FAMILY_PATH: dict = {}
_FAMILY_READY = [False]

_SYS_MSYH = "C:/Windows/Fonts/msyh.ttc"
_SYS_MSYHBD = "C:/Windows/Fonts/msyhbd.ttc"
# 字形回退用的字体家族（微软雅黑，字形覆盖最全，且永远可解析到 msyh.ttc）
_FALLBACK_TTF = "Microsoft YaHei UI"


def _build_family_map():
    if _FAMILY_READY[0]:
        return
    _FAMILY_READY[0] = True
    try:
        from . import fonts as _f
        for fname, family in getattr(_f, "_FNAME_FAMILY", {}).items():
            import os
            p = os.path.join(getattr(_f, "FONTS_DIR", ""), fname)
            if os.path.exists(p):
                _FAMILY_PATH[family] = p
    except Exception:
        pass
    for fam in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑"):
        _FAMILY_PATH.setdefault(fam, _SYS_MSYH)


def _get_font(family, size_px, bold):
    """取得 PIL 字体对象（带缓存）。size_px 为超采样后的像素字号。"""
    _build_family_map()
    key = (family, int(size_px), bool(bold))
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    size_px = max(6, int(size_px))
    path = _FAMILY_PATH.get(family)
    if path is None or not __import__("os").path.exists(path):
        path = _SYS_MSYHBD if bold else _SYS_MSYH
    f = None
    for p in (path, _SYS_MSYHBD if bold else _SYS_MSYH, _SYS_MSYH):
        try:
            f = ImageFont.truetype(p, size_px, index=0)
            break
        except Exception:
            continue
    if f is None:
        f = ImageFont.load_default()
    if len(_FONT_CACHE) > 240:
        _FONT_CACHE.clear()
    _FONT_CACHE[key] = f
    return f


# ------------------------------------------------------------------ 字形回退
# PIL 不做字体回退：艺术字体（Google Fonts 的 Ma Shan Zheng 等）缺字形时
# 会渲染成方框（例如「·」U+00B7 在毛笔楷书里就没有）。这里用「私有区字符
# 必然落到 notdef 方框」的特性做覆盖率探测，缺字形就改用回退字体渲染，
# 从而在保留艺术字体的同时杜绝方框。
_NOTDEF_CH = "\uE000"
_NOTDEF_CACHE: dict = {}


def _notdef_box(font):
    """返回该字体 notdef（缺字形方框）的包围盒，作为覆盖率参照。"""
    key = id(font)
    ref = _NOTDEF_CACHE.get(key)
    if ref is None:
        try:
            d = ImageDraw.Draw(Image.new("L", (8, 8)))
            ref = d.textbbox((0, 0), _NOTDEF_CH, font=font)
        except Exception:
            ref = None
        if len(_NOTDEF_CACHE) > 400:
            _NOTDEF_CACHE.clear()
        _NOTDEF_CACHE[key] = ref
    return ref


def has_glyph(font, ch, ref=None):
    """判断字体是否含 ch 的真实字形（缺字形会与 notdef 方框尺寸一致）。"""
    try:
        d = ImageDraw.Draw(Image.new("L", (8, 8)))
        bb = d.textbbox((0, 0), ch, font=font)
    except Exception:
        return True
    if ref is None:
        ref = _notdef_box(font)
    return ref is None or bb != ref


def split_runs(text, font, fallback, icons=()):
    """把 text 切成 [(kind, seg, font), ...]。

    kind = "t"（文字）/ "i"（矢量图标）。逐个字符判断字形覆盖：艺术字体
    缺字形时该字符单独改用 fallback 字体，其余仍用艺术字体，保证既美观
    又不会出现方框。
    """
    ref_a = _notdef_box(font)
    ref_b = _notdef_box(fallback) if fallback is not font else ref_a
    runs = []
    for ch in text:
        if ch in icons:
            kind, fnt = "i", None
        else:
            kind = "t"
            fnt = font if has_glyph(font, ch, ref_a) else fallback
            if fnt is None:
                fnt = font
        if runs and runs[-1][0] == kind and runs[-1][2] is fnt:
            runs[-1][1] += ch
        else:
            runs.append([kind, ch, fnt])
    return [(k, s, f) for k, s, f in runs]


# ------------------------------------------------------------------ 主渲染
def render_button(w, h, base, fg, text, font,
                  hover=False, pressed=False, enabled=True,
                  radius=None, scale=1.0):
    """返回一枚玻璃质感按钮的 RGBA 图像（已降采样到 w×h）。"""
    if not _PIL_OK:
        return None
    w, h = int(w), int(h)
    if w <= 2 or h <= 2:
        return None

    S = SS
    W, H = w * S, h * S

    # 阴影/发光所需的四周留白；小按钮适当收紧
    if min(w, h) < 30:
        pad = int(round(2 * S))
    elif min(w, h) < 42:
        pad = int(round(3 * S))
    else:
        pad = int(round(4 * S))
    sink = int(round(2 * S))                      # 立体厚度（侧壁高度）
    fo = sink if pressed else 0                   # 按下时棋面整体下沉

    wall_box = (pad, pad, W - pad, H - pad)       # 侧壁（永远占满按钮区域）
    face_box = (pad, pad + fo, W - pad, H - pad - sink + fo)
    fx0, fy0, fx1, fy1 = face_box
    fw, fh = fx1 - fx0, fy1 - fy0
    if fw <= 2 or fh <= 2:
        return None

    if radius is None:
        r_final = min(12, max(2, int(h / 2.2)))
    else:
        r_final = int(radius)
    r = float(r_final * S)
    r = max(1.0, min(r, fw / 2.0, fh / 2.0))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ---- 禁用态：扁平、去饱和、无阴影无发光 ----
    if not enabled:
        flat = mix(base, "#2B3040", 0.62)
        face_m = _shape((W, H), face_box, r)
        g = _grad_rgba((W, H), face_box,
                       [(0.0, mix(flat, "#FFFFFF", 0.10)),
                        (1.0, shade(flat, 0.88))])
        g.putalpha(_mul(g.split()[3], face_m))
        canvas = _over(canvas, g)
        # 禁用态描边
        bd = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(bd).rounded_rectangle(
            [fx0 + 0.5 * S, fy0 + 0.5 * S, fx1 - 0.5 * S, fy1 - 0.5 * S],
            radius=r, outline=_parse(mix(flat, "#FFFFFF", 0.20)) + (150,),
            width=max(1, int(S)))
        canvas = _over(canvas, bd)
        fgc = mix(fg, flat, 0.45)
        _draw_text(canvas, text, font, fgc, (fx0 + fx1) / 2.0,
                   (fy0 + fy1) / 2.0, scale, shadow_alpha=0.0)
        return canvas.resize((w, h), Image.LANCZOS)

    # ---------- 1) 环境阴影（大而柔） ----------
    amb = _shape((W, H), (fx0 + 0.5 * S, fy0 + 1.5 * S, fx1 - 0.5 * S, fy1 + 1.5 * S), r)
    canvas = _over(canvas, _tint(amb, "#000000", alpha=118, blur=3.2 * S))

    # ---------- 2) 投射阴影（贴合、更实） ----------
    if pressed:
        d_off, d_blur, d_alpha = 0.6 * S, 1.2 * S, 96
    else:
        d_off, d_blur, d_alpha = 1.8 * S, 2.0 * S, 150
    drp = _shape((W, H), (fx0 + 0.5 * S, fy0 + d_off, fx1 - 0.5 * S, fy1 + d_off), r)
    canvas = _over(canvas, _tint(drp, "#000000", alpha=d_alpha, blur=d_blur))

    # ---------- 3) 悬停 / 按下外发光 ----------
    if hover or pressed:
        gcol = mix(base, "#FFFFFF", 0.55)
        ga = 205 if pressed else 150
        grow = (2.2 * S) if pressed else (1.6 * S)
        gm = _shape((W, H), (fx0 - grow, fy0 - grow, fx1 + grow, fy1 + grow), r + grow)
        canvas = _over(canvas, _tint(gm, gcol, alpha=ga, blur=2.6 * S))

    # ---------- 4) 立体侧壁（按下时在上面露出内阴影） ----------
    wall_c = shade(base, 0.46) if not pressed else shade(base, 0.40)
    wm = _shape((W, H), wall_box, r)
    wl = Image.new("RGBA", (W, H), _parse(wall_c) + (0,))
    wl.putalpha(wm)
    canvas = _over(canvas, wl)

    # ---------- 5) 主体渐变 ----------
    if pressed:
        stops = [(0.00, shade(base, 0.74)),
                 (0.38, shade(base, 0.86)),
                 (1.00, mix(base, "#FFFFFF", 0.05))]
    elif hover:
        stops = [(0.00, mix(base, "#FFFFFF", 0.30)),
                 (0.46, mix(base, "#FFFFFF", 0.10)),
                 (1.00, mix(base, "#000000", 0.07))]
    else:
        stops = [(0.00, mix(base, "#FFFFFF", 0.22)),
                 (0.46, base),
                 (1.00, shade(base, 0.86))]
    face_m = _shape((W, H), face_box, r)
    g = _grad_rgba((W, H), face_box, stops)
    g.putalpha(_mul(g.split()[3], face_m))
    canvas = _over(canvas, g)

    # ---------- 6) 玻璃 sheen（上半部高光，通透感关键） ----------
    sheen_h = max(int(fh * 0.54), int(2 * S))
    sheen_box = (fx0 + 1.2 * S, fy0 + 1.2 * S,
                 fx1 - 1.2 * S, fy0 + sheen_h)
    sheen_m = _shape((W, H), sheen_box, r - 1.2 * S)
    grad = _grad_l((W, H), (0, int(fy0 + 1.2 * S), W, int(fy0 + sheen_h)),
                   [(0.0, 255), (0.55, 96), (1.0, 8)])
    sheen_a = _mul(sheen_m, grad)
    sheen_a = sheen_a.point(lambda v: int(v * (0.30 if not pressed else 0.20)))
    sl = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    sl.putalpha(sheen_a)
    canvas = _over(canvas, sl)

    # ---------- 7) 底部内缘透光（玻璃下沿的折射亮边） ----------
    rim_h = max(int(fh * 0.26), int(2 * S))
    rim_box = (fx0 + 1.2 * S, fy1 - rim_h, fx1 - 1.2 * S, fy1 - 1.2 * S)
    rim_m = _shape((W, H), rim_box, r - 1.2 * S)
    rgrad = _grad_l((W, H), (0, int(fy1 - rim_h), W, int(fy1 - 1.2 * S)),
                    [(0.0, 0), (0.72, 26), (1.0, 150)])
    rim_a = _mul(rim_m, rgrad).point(lambda v: int(v * 0.62))
    rl = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    rl.putalpha(rim_a.filter(ImageFilter.GaussianBlur(0.7 * S)))
    canvas = _over(canvas, rl)

    # ---------- 8) 镜面反光斑（左上柔光） ----------
    if not pressed:
        gloss = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gx0 = fx0 + fw * 0.10
        gy0 = fy0 + fh * 0.06
        gx1 = fx0 + fw * 0.72
        gy1 = fy0 + fh * 0.52
        ImageDraw.Draw(gloss).ellipse(
            [gx0, gy0, gx1, gy1], fill=(255, 255, 255, 46))
        gloss = gloss.filter(ImageFilter.GaussianBlur(2.4 * S))
        gloss.putalpha(_mul(gloss.split()[3], face_m))
        canvas = _over(canvas, gloss)

    # ---------- 9) 内斜角环（上缘亮 / 两侧中性 / 下缘微亮） ----------
    ring_out = face_m
    ring_in = _shape((W, H), face_box, r, inset=1.15 * S)
    ring = ImageChops.subtract(ring_out, ring_in)
    bg_grad = _grad_l((W, H), face_box,
                      [(0.00, 255), (0.16, 132), (0.48, 18),
                       (0.78, 30), (1.00, 96)])
    bevel_a = _mul(ring, bg_grad)
    bevel = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    bevel.putalpha(bevel_a.point(lambda v: int(v * 0.72)))
    canvas = _over(canvas, bevel)

    # ---------- 10) 按下内阴影（顶部压暗，强化"陷下去"） ----------
    if pressed:
        top_m = _shape((W, H), (fx0, fy0, fx1, fy0 + max(int(fh * 0.34), int(2 * S))), r)
        tg = _grad_l((W, H), (0, int(fy0), W,
                              int(fy0 + max(int(fh * 0.34), int(2 * S)))),
                     [(0.0, 210), (1.0, 0)])
        ta = _mul(_mul(ring_out, top_m), tg)
        tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tl.putalpha(ta.filter(ImageFilter.GaussianBlur(0.8 * S)))
        canvas = _over(canvas, tl)

    # ---------- 11) 清晰描边（1px，锐利边界） ----------
    bd_col = mix(base, "#FFFFFF", 0.46) if not pressed else mix(base, "#FFFFFF", 0.24)
    bd = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(bd).rounded_rectangle(
        [fx0 + 0.5 * S, fy0 + 0.5 * S, fx1 - 0.5 * S, fy1 - 0.5 * S],
        radius=r, outline=_parse(bd_col) + (218,), width=max(1, int(S)))
    canvas = _over(canvas, bd)

    # ---------- 12) 文字（限制在立体面高度内，小按钮不溢出） ----------
    fgc = mix(fg, "#000000", 0.10) if pressed else fg
    _draw_text(canvas, text, font, fgc,
               (fx0 + fx1) / 2.0, (fy0 + fy1) / 2.0, scale,
               shadow_alpha=(0.34 if not pressed else 0.18),
               max_px=(fh / S) * 0.78)

    return canvas.resize((w, h), Image.LANCZOS)


def _draw_text(canvas, text, font, fg, cx, cy, scale, shadow_alpha=0.30,
               max_px=None):
    """渲染按钮文字（支持「图标 + 中文」混排）。

    媒体符号（▶ ◀ ⏸ ⏮ ⏭ ⏹）在 msyh 等中文字体里缺字形（PIL 又不做字体
    回退，会渲染成方框），因此改为**矢量绘制**——比字体符号更锐利、更精致；
    其余文字用真字体渲染，并按文字明暗自动选择深色/浅色描影提升清晰度。
    max_px 为文字（含图标）允许的最大像素字号（普通坐标），用于小按钮防溢出。
    """
    if not text:
        return
    try:
        S = SS
        if isinstance(font, (tuple, list)):
            family = str(font[0])
            size_pt = float(font[1]) if len(font) > 1 else 12.0
            bold = (len(font) > 2 and str(font[2]).lower() == "bold")
        else:
            family, size_pt, bold = "Microsoft YaHei UI", 12.0, True
        size_px = max(6.0, size_pt * float(scale or 1.0) * S)
        if max_px:
            size_px = min(size_px, float(max_px) * S)
    except Exception:
        return

    # 拆成 图标段 / 文字段；文字段再按字形覆盖切成「艺术字体 / 回退字体」
    d = ImageDraw.Draw(canvas)
    try:
        f_all = _get_font(family, size_px, bold)
        # 回退字体（雅黑）保证任何字符都有字形，避免方框
        f_fb = _get_font(_FALLBACK_TTF, size_px, bold) if family != _FALLBACK_TTF else f_all
        runs = split_runs(text, f_all, f_fb, icons=_ICON_GLYPHS)
        widths = []
        for kind, seg, fnt in runs:
            if kind == "t":
                widths.append(d.textlength(seg, font=fnt))
            else:
                widths.append(size_px * 0.74 * len(seg))
        total = sum(widths)
    except Exception:
        # 彻底兜底：整串直接用字体画
        try:
            d.text((cx, cy), text, font=_get_font(family, size_px, bold),
                   anchor="mm", fill=_parse(fg) + (255,))
        except Exception:
            pass
        return

    x = cx - total / 2.0
    sh_off = 0.9 * S
    sc = "#FFFFFF" if _lum(fg) < 110 else "#000000"
    sh_col = _parse(sc) + (int(255 * shadow_alpha),)
    main_col = _parse(fg) + (255,)
    for (kind, seg, fnt), wd in zip(runs, widths):
        if kind == "t":
            try:
                if shadow_alpha > 0:
                    d.text((x, cy + sh_off), seg, font=fnt, anchor="lm",
                           fill=sh_col)
                d.text((x, cy), seg, font=fnt, anchor="lm", fill=main_col)
            except Exception:
                pass
        else:
            for k, ch in enumerate(seg):
                _draw_icon(d, ch, x + wd / len(seg) * (k + 0.5), cy,
                           size_px, main_col, sh_col, sh_off if shadow_alpha > 0 else 0)
        x += wd


# 媒体图标：一律矢量绘制（字体缺字形会渲染成方框，且风格不统一）。
# ♪ 也纳入：即便某处仍使用音符文字，也会走矢量分支而非方框。
_ICON_GLYPHS = set("▶◀▲▼⏸⏮⏭⏹■●♪")


def _poly(d, pts, col, sh_col, sh_off):
    if sh_off:
        d.polygon([(px, py + sh_off) for px, py in pts], fill=sh_col)
    d.polygon(pts, fill=col)


def _draw_icon(d, ch, cx, cy, u, col, sh_col, sh_off):
    """矢量绘制单个媒体图标。u 为字号（超采样像素），图标约 0.62u 高。"""
    uw = u * 0.60
    uh = u * 0.56
    if ch == "▶":
        _poly(d, [(cx - uw * 0.38, cy - uh / 2), (cx - uw * 0.38, cy + uh / 2),
                  (cx + uw * 0.62, cy)], col, sh_col, sh_off)
    elif ch == "◀":
        _poly(d, [(cx + uw * 0.38, cy - uh / 2), (cx + uw * 0.38, cy + uh / 2),
                  (cx - uw * 0.62, cy)], col, sh_col, sh_off)
    elif ch == "▲":
        _poly(d, [(cx - uw / 2, cy + uh * 0.42), (cx + uw / 2, cy + uh * 0.42),
                  (cx, cy - uh * 0.58)], col, sh_col, sh_off)
    elif ch == "▼":
        _poly(d, [(cx - uw / 2, cy - uh * 0.42), (cx + uw / 2, cy - uh * 0.42),
                  (cx, cy + uh * 0.58)], col, sh_col, sh_off)
    elif ch == "⏸":
        bw = uw * 0.26
        gap = uw * 0.24
        h = uh
        for x0 in (cx - gap / 2 - bw, cx + gap / 2):
            if sh_off:
                d.rounded_rectangle([x0, cy - h / 2 + sh_off, x0 + bw, cy + h / 2 + sh_off],
                                    radius=bw * 0.4, fill=sh_col)
            d.rounded_rectangle([x0, cy - h / 2, x0 + bw, cy + h / 2],
                                radius=bw * 0.4, fill=col)
    elif ch == "⏮":
        # 上一首：竖杠在左，三角尖朝左（标准"跳到开头"方向）
        bw = uw * 0.20
        x0 = cx - uw / 2
        apex_x = x0 + bw + uw * 0.07
        base_x = cx + uw * 0.42
        tri = [(apex_x, cy), (base_x, cy - uh * 0.48), (base_x, cy + uh * 0.48)]
        if sh_off:
            d.rounded_rectangle([x0, cy - uh / 2 + sh_off, x0 + bw, cy + uh / 2 + sh_off],
                                radius=bw * 0.38, fill=sh_col)
            _poly(d, [(px, py + sh_off) for px, py in tri], sh_col, sh_col, 0)
        d.rounded_rectangle([x0, cy - uh / 2, x0 + bw, cy + uh / 2],
                            radius=bw * 0.38, fill=col)
        _poly(d, tri, col, col, 0)
    elif ch == "⏭":
        # 下一首：竖杠在右，三角尖朝右（标准"跳到结尾"方向）
        bw = uw * 0.20
        x1 = cx + uw / 2
        apex_x = x1 - bw - uw * 0.07
        base_x = cx - uw * 0.42
        tri = [(apex_x, cy), (base_x, cy - uh * 0.48), (base_x, cy + uh * 0.48)]
        if sh_off:
            d.rounded_rectangle([x1 - bw, cy - uh / 2 + sh_off, x1, cy + uh / 2 + sh_off],
                                radius=bw * 0.38, fill=sh_col)
            _poly(d, [(px, py + sh_off) for px, py in tri], sh_col, sh_col, 0)
        d.rounded_rectangle([x1 - bw, cy - uh / 2, x1, cy + uh / 2],
                            radius=bw * 0.38, fill=col)
        _poly(d, tri, col, col, 0)
    elif ch in ("⏹", "■"):
        s = uw * 0.72
        if sh_off:
            d.rounded_rectangle([cx - s / 2, cy - s / 2 + sh_off,
                                 cx + s / 2, cy + s / 2 + sh_off],
                                radius=s * 0.18, fill=sh_col)
        d.rounded_rectangle([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2],
                            radius=s * 0.18, fill=col)
    elif ch == "●":
        r = uw * 0.42
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    elif ch == "♪":
        # 八分音符（矢量）：音符头 + 音符干 + 右扬符尾。
        # 雅黑等中文字体不含 U+266A 字形（PIL 又不做字体回退），
        # 直接用字体渲染会得到乱码方框，故矢量绘制保证风格统一。
        rx, ry = uw * 0.17, uh * 0.15          # 音符头（椭圆）半径
        hx = cx - uw * 0.13
        hy = cy + uh * 0.26
        sx = hx + rx * 0.78                    # 音符干 x（贴头右缘）
        sw = max(1.2, uw * 0.075)              # 干宽
        top = cy - uh * 0.54                   # 干顶
        stem = [sx, top, sx + sw, hy + ry * 0.2]
        flag = [(sx + sw, top),
                (sx + sw + uw * 0.24, top + uh * 0.20),
                (sx + sw + uw * 0.10, top + uh * 0.40),
                (sx + sw, top + uh * 0.26)]
        if sh_off:
            d.ellipse([hx - rx, hy - ry + sh_off, hx + rx, hy + ry + sh_off],
                      fill=sh_col)
            d.rounded_rectangle([stem[0], stem[1] + sh_off, stem[2], stem[3] + sh_off],
                                radius=sw * 0.4, fill=sh_col)
            d.polygon([(px, py + sh_off) for px, py in flag], fill=sh_col)
        d.ellipse([hx - rx, hy - ry, hx + rx, hy + ry], fill=col)
        d.rounded_rectangle(stem, radius=sw * 0.4, fill=col)
        d.polygon(flag, fill=col)


# ------------------------------------------------------------------ Tk 接口
def _tk_scale(c):
    if _TK_SCALE[0] is None:
        v = 1.0
        try:
            v = float(c.tk.call("tk", "scaling"))
        except Exception:
            v = 1.0
        _TK_SCALE[0] = max(0.8, min(2.5, v))
    return _TK_SCALE[0]


def get_button_photo(c, w, h, base, fg, text, font,
                     hover=False, pressed=False, enabled=True, radius=None):
    """取得（或生成并缓存）按钮的 PhotoImage。"""
    if not (_PIL_OK and _TK_OK):
        return None
    try:
        key = (int(w), int(h), str(base), str(fg), str(text),
               tuple(font) if isinstance(font, (tuple, list)) else str(font),
               bool(hover), bool(pressed), bool(enabled),
               None if radius is None else int(radius))
    except Exception:
        return None
    ph = _CACHE.get(key)
    if ph is not None:
        return ph
    img = render_button(w, h, base, fg, text, font,
                        hover=hover, pressed=pressed, enabled=enabled,
                        radius=radius, scale=_tk_scale(c))
    if img is None:
        return None
    try:
        ph = ImageTk.PhotoImage(img)
    except Exception:
        return None
    if len(_CACHE) > _MAX_CACHE:
        _CACHE.clear()
    _CACHE[key] = ph
    return ph


def available():
    return _PIL_OK and _TK_OK
