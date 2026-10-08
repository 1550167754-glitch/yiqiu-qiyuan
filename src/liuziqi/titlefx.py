# -*- coding: utf-8 -*-
"""
titlefx.py —— 艺术字标题渲染器（PIL 超采样 + 真 Alpha 合成）。

为什么需要它
------------
Tk Canvas 的 create_text 只有单色填充，做不出「鎏金艺术字」的金属质感；
直接叠多层色块又会浑浊发糊（Tk 无抗锯齿、无半透明合成）。

方案（与 buttonfx 同源）：在 SS 倍超采样画布上以真 Alpha 逐层合成——

    1  柔和外辉光（色彩光晕，向外渐隐到全透明）
    2  柔和投影（下移 + 高斯模糊）
    3  深色描边（PIL stroke_width，勾勒轮廓）
    4  金属垂直渐变填充（按字形高度铺满，顶亮底深）
    5  顶部金属高光 sheen（上半区提亮，反光感）
    6  底部内缘暗化（厚度感）

最后 LANCZOS 降采样，得到锐利且通透的艺术字。无 PIL 时由调用方走
Tk 多层文字的矢量回退（见 gui._draw_art_text）。

⚠ 历史缺陷（已修）
------------------
早期版本用 `Image.paste(RGB)` 把整幅渐变条贴进 RGBA 图层——paste 不带 mask
时会把该区域的 alpha 一并写成 255，于是"渐变层"变成**整块不透明**，
标题背后出现一块突兀的矩形色块。现在渐变一律用文字遮罩抠 alpha
（`putalpha(_mul(layer_alpha, body))`），块外像素严格透明。

配色方案
--------
    gold      —— 鎏金（主标题）
    platinum  —— 铂金/银白（副标题）
"""
from __future__ import annotations

from .buttonfx import (_PIL_OK, _TK_OK, SS, _get_font, _parse, mix,
                       _mul, _over, _tint, split_runs, _FALLBACK_TTF)

if _PIL_OK:
    from PIL import Image, ImageDraw, ImageFilter
else:                                    # pragma: no cover
    Image = ImageDraw = ImageFilter = None
if _TK_OK:
    from PIL import ImageTk
else:                                    # pragma: no cover
    ImageTk = None

_MAX_CACHE = 160
_CACHE: dict = {}
# 标题块 RGBA 底图缓存（帧动画/多尺寸复用，避免重复渲染）
_BLOCK_CACHE: dict = {}
_MAX_BLOCK_CACHE = 24

# 配色方案：正文渐变色标 → (stops, 描边色, 辉光色)
_SCHEMES = {
    "gold": (
        [(0.00, "#FFF7DE"), (0.26, "#FFEBAD"), (0.50, "#F4C451"),
         (0.76, "#D9982A"), (1.00, "#B3761A")],
        "#3A2A0C", "#FFC94F",
    ),
    "platinum": (
        [(0.00, "#FFFFFF"), (0.28, "#E9F1FB"), (0.62, "#C2CEDF"),
         (1.00, "#8FA0B8")],
        "#1B2233", "#9FC4F5",
    ),
}
_DEFAULT_SCHEME = "gold"
_OUTLINE_FALLBACK = "#3A2A0C"


def _scheme(name):
    return _SCHEMES.get(str(name), _SCHEMES[_DEFAULT_SCHEME])


def _grad_strip(w, h, stops):
    """按色标生成 w×h 的垂直渐变 RGB 图（顶 → 底）。"""
    w = max(1, int(w)); h = max(1, int(h))
    vals = []
    for i in range(h):
        t = i / (h - 1) if h > 1 else 0.0
        col = stops[0][1]
        for k in range(len(stops) - 1):
            p0, c0 = stops[k]
            p1, c1 = stops[k + 1]
            if t <= p1 or k == len(stops) - 2:
                r = 0.0 if p1 <= p0 else max(0.0, min(1.0, (t - p0) / (p1 - p0)))
                col = mix(c0, c1, r)
                break
        vals.append(_parse(col))
    strip = Image.new("RGB", (1, h))
    strip.putdata(vals)
    return strip.resize((w, h), Image.NEAREST)


def _norm_entries(entries):
    """统一成 [(text, height, scheme), ...]。"""
    out = []
    for e in entries or ():
        try:
            text = str(e[0])
            height = max(12, int(e[1]))
        except Exception:
            continue
        scheme = str(e[2]) if len(e) > 2 else _DEFAULT_SCHEME
        if text:
            out.append((text, height, scheme))
    return out


def render_title_block(entries, family=None, glow=1.0, gap_ratio=0.30,
                       bold=True):
    """渲染「多行艺术字标题块」，返回 RGBA 图（含柔和辉光，四周全透明）。

    entries = [(text, height, scheme), ...] 自上而下；height 为**输出像素高度**
    （字形约占 72%，其余为描边/辉光留白）。glow∈[0,1] 控制辉光强度，
    glow=0 时无辉光、留白收紧。失败返回 None。

    关键：所有图层的 alpha 都由文字遮罩抠出，图片四角严格透明——
    因此可以直接叠在任意背景上而不会出现矩形底块。
    """
    if not (_PIL_OK and entries):
        return None
    norm = _norm_entries(entries)
    if not norm:
        return None
    try:
        glow = max(0.0, min(1.0, float(glow)))
    except Exception:
        glow = 0.0
    S = SS

    fam = family or _FALLBACK_TTF
    items = []
    for text, height, scheme in norm:
        H = int(height) * S
        glyph_px = int(H * 0.72)
        font = _get_font(fam, glyph_px, bold)
        # 艺术字体缺字形（如毛笔楷书没有「·」）→ 该字改用雅黑，避免方框
        fb = _get_font(_FALLBACK_TTF, glyph_px, bold) if fam != _FALLBACK_TTF else font
        stroke = max(2, int(H * 0.035))
        try:
            runs = split_runs(text, font, fb)
        except Exception:
            runs = [("t", text, font)]
        try:
            meas = ImageDraw.Draw(Image.new("L", (8, 8)))
            widths, offs = [], []
            left = top = right = bottom = None
            xoff = 0.0
            for _k, seg, f in runs:
                wd = meas.textlength(seg, font=f)
                bb1 = meas.textbbox((0, 0), seg, font=f, stroke_width=stroke)
                offs.append(xoff); widths.append(wd)
                left = bb1[0] + xoff if left is None else min(left, bb1[0] + xoff)
                top = bb1[1] if top is None else min(top, bb1[1])
                right = bb1[2] + xoff if right is None else max(right, bb1[2] + xoff)
                bottom = bb1[3] if bottom is None else max(bottom, bb1[3])
                xoff += wd
            bb = (left, top, right, bottom)
        except Exception:
            bb = (0, 0, int(len(text) * glyph_px), glyph_px + stroke * 2)
            offs, widths = [0.0], [0.0]
        tw = max(4, int(round(bb[2] - bb[0])))
        th = max(4, int(round(bb[3] - bb[1])))
        items.append(dict(text=text, runs=runs, offs=offs, stroke=stroke, bb=bb,
                          tw=tw, th=th, H=H, scheme=scheme))

    max_H = max(it["H"] for it in items)
    gap = max(2, int(round(max_H * gap_ratio * 0.32)))
    gblur = max(2.0, max_H * 0.075 * glow)
    # 留白必须包住「描边 + 辉光模糊」——否则高斯模糊在图片矩形边界被裁，
    # 会在标题周围形成方形硬边（与 old titlefx 的同源陷阱）。
    pad = int(max(it["stroke"] * 2 + it["H"] * 0.10 for it in items)
              + 3.2 * gblur + 3 * S)
    Wc = max(it["tw"] for it in items) + pad * 2
    Hc = sum(it["th"] for it in items) + gap * (len(items) - 1) + pad * 2

    canvas = Image.new("RGBA", (Wc, Hc), (0, 0, 0, 0))

    # ---- 逐行生成遮罩与落点（水平居中、垂直依次堆叠） ----
    laid = []
    y = float(pad)
    for it in items:
        ox = int(round(pad + (Wc - 2 * pad - it["tw"]) / 2.0 - it["bb"][0]))
        oy = int(round(y - it["bb"][1]))
        body = Image.new("L", (Wc, Hc), 0)
        full = Image.new("L", (Wc, Hc), 0)
        db = ImageDraw.Draw(body)
        df = ImageDraw.Draw(full)
        for (_k, seg, f), xo in zip(it["runs"], it["offs"]):
            px = ox + int(round(xo))
            db.text((px, oy), seg, font=f, fill=255)
            df.text((px, oy), seg, font=f, fill=255,
                    stroke_width=it["stroke"], stroke_fill=255)
        laid.append(dict(it=it, body=body, full=full, y=y))
        y += it["th"] + gap

    # ---- A) 辉光 + 投影：先全部铺底，避免后一行字形遮住前一行的光 ----
    if glow > 0:
        for L in laid:
            _stops, _ol, glow_c = _scheme(L["it"]["scheme"])
            halo = L["full"].filter(
                ImageFilter.GaussianBlur(max(1.5, gblur * 2.4)))
            canvas = _over(canvas, _tint(halo, glow_c,
                                         alpha=int(74 * glow)))
            core = L["full"].filter(
                ImageFilter.GaussianBlur(max(1.0, gblur)))
            canvas = _over(canvas, _tint(core, glow_c,
                                         alpha=int(152 * glow)))
    for L in laid:
        off = max(2, int(L["it"]["H"] * 0.045))
        sh = Image.new("L", (Wc, Hc), 0)
        sh.paste(L["full"], (0, off))
        canvas = _over(canvas, _tint(
            sh.filter(ImageFilter.GaussianBlur(max(1.5, L["it"]["H"] * 0.035))),
            "#000000", alpha=150))

    # ---- B) 描边 + 金属渐变 + 顶部高光 + 底缘暗化 ----
    for L in laid:
        it = L["it"]
        th = it["th"]
        y0 = int(round(L["y"]))
        stops, outline_c, _glow_c = _scheme(it["scheme"])
        if not outline_c:
            outline_c = _OUTLINE_FALLBACK
        # 描边
        canvas = _over(canvas, _tint(L["full"], outline_c))
        # 金属垂直渐变（按本行字形高度铺，alpha 由 body 遮罩抠出 → 块外透明）
        band = Image.new("RGBA", (Wc, Hc), (0, 0, 0, 0))
        band.paste(_grad_strip(Wc, th, stops), (0, y0))
        band.putalpha(_mul(band.split()[3], L["body"]))
        canvas = _over(canvas, band)
        # 顶部金属高光 sheen
        sheen_h = max(2, int(th * 0.46))
        sg = Image.new("L", (Wc, Hc), 0)
        strip = Image.new("L", (1, sheen_h))
        strip.putdata([int(122 * (1 - i / max(1, sheen_h - 1)))
                       for i in range(sheen_h)])
        sg.paste(strip.resize((Wc, sheen_h), Image.NEAREST), (0, y0))
        sg = _mul(sg, L["body"])
        canvas = _over(canvas, _tint(sg, "#FFFFFF"))
        # 底部内缘暗化（厚度感）
        dk_h = max(2, int(th * 0.30))
        dg = Image.new("L", (Wc, Hc), 0)
        strip2 = Image.new("L", (1, dk_h))
        strip2.putdata([int(64 * (i / max(1, dk_h - 1))) for i in range(dk_h)])
        dg.paste(strip2.resize((Wc, dk_h), Image.NEAREST),
                 (0, max(0, y0 + th - dk_h)))
        dg = _mul(dg, L["body"])
        canvas = _over(canvas, _tint(dg, "#000000"))

    return canvas.resize((max(1, Wc // S), max(1, Hc // S)), Image.LANCZOS)


# ------------------------------------------------------------------ 缓存
def _block_image(entries, family, glow, bold):
    """取得（或生成并缓存）标题块 RGBA 底图。"""
    try:
        key = (tuple(entries), str(family), round(float(glow), 3), bool(bold))
    except Exception:
        return None
    img = _BLOCK_CACHE.get(key)
    if img is not None:
        return img
    img = render_title_block(entries, family=family, glow=glow, bold=bold)
    if img is None:
        return None
    if len(_BLOCK_CACHE) > _MAX_BLOCK_CACHE:
        _BLOCK_CACHE.clear()
    _BLOCK_CACHE[key] = img
    return img


def get_title_block_photo(canvas, entries, family=None, glow=1.0, bold=True):
    """取得（或生成并缓存）标题块的 PhotoImage；无 PIL/Tk 返回 None。

    调用方需持有返回值引用防 GC（与 buttonfx 约定一致）。
    """
    if not (_PIL_OK and _TK_OK):
        return None
    norm = _norm_entries(entries)
    if not norm:
        return None
    try:
        key = ("blk", tuple(norm), str(family), round(float(glow), 3), bool(bold))
    except Exception:
        return None
    ph = _CACHE.get(key)
    if ph is not None:
        return ph
    img = _block_image(norm, family, glow, bold)
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


def get_title_block_frames(canvas, entries, family=None, glow=1.0,
                           alphas=(0.0, 0.22, 0.42, 0.60, 0.74, 0.85, 0.93,
                                   0.98, 1.0),
                           bold=True):
    """返回按 alphas 逐帧降低整体不透明度的 PhotoImage 列表（入场淡入动画用）。

    只渲染一次底图，其余帧仅缩放 alpha 通道，开销极小；调用方需持有
    返回值列表引用防 GC。
    """
    if not (_PIL_OK and _TK_OK):
        return []
    norm = _norm_entries(entries)
    if not norm:
        return []
    img = _block_image(norm, family, glow, bold)
    if img is None:
        return []
    out = []
    try:
        for a in alphas:
            try:
                a = max(0.0, min(1.0, float(a)))
            except Exception:
                a = 1.0
            if a >= 0.999:
                frame = img
            else:
                frame = img.copy()
                frame.putalpha(
                    frame.split()[3].point(lambda v, _a=a: int(v * _a)))
            out.append(ImageTk.PhotoImage(frame))
    except Exception:
        return []
    return out


def available():
    return _PIL_OK and _TK_OK
