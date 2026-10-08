# -*- coding: utf-8 -*-
"""
stonefx.py —— 棋子渲染器（PIL 超采样 + 真球面光影）。

为什么需要它
------------
用 Tk 的 create_oval / create_arc 画棋子有两个硬伤：

  * **没有抗锯齿**：圆形边缘是阶梯锯齿，放大后尤其明显；
  * **画不出渐变**：只能贴"亮色上半圆 + 一个白点"，结果就是一个生硬的
    「两色半月」——这正是黑棋显得廉价丑陋的根源。

方案
----
用 PIL 在 4× 超采样画布上合成真正的球面光影：

    1  环境投影（大而柔）      2  接触投影（贴合、更实）
    3  球面渐变（光源在左上，径向衰减）
    4  边缘环境遮蔽（暗边，勾出球感）
    5  底部回光（右下缘反弹光 —— 玉/黑曜石通透感的关键）
    6  左上大面积柔光
    7  镜面高光（柔核 + 锐核）

最后 LANCZOS 降采样，得到真正的抗锯齿圆边与真实的球面明暗过渡。
同半径同色的棋子只渲染一次并缓存为 PhotoImage，棋盘重绘零开销。
"""

from __future__ import annotations

from . import buttonfx as _bf

_PIL_OK = _bf._PIL_OK
_TK_OK = _bf._TK_OK

if _PIL_OK:
    from PIL import Image, ImageDraw, ImageChops

try:
    from PIL import ImageTk
except Exception:                                            # pragma: no cover
    ImageTk = None

SS = 4
_CACHE: dict = {}
_MAX_CACHE = 400

# 棋子配色（黑=黑曜石 / 云子，白=暖玉白）
#
# ⚠ 白棋立体感的关键：浅色球体的明暗差在视觉上会被压缩（高光区"糊成一片"），
# 因此白棋必须比黑棋有**更大**的亮度落差与更强的边缘遮蔽，否则一眼就"扁平"。
# 早期白棋 lo=#BDB6A6（与 hi 仅差 ~66）且无背光侧压暗 → 看起来像一枚白片。
# 现在：加深背光侧渐变 + 单独一层"背光侧压暗" + 加重边缘遮蔽/接触投影，
# 并把镜面高光做成"柔核 + 锐核"双层，质感与黑棋一致。
#
# 字段：hi/lo 球面渐变高/低色，rim 外缘描边，spec 镜面高光，bounce 右下回光；
#       ao 边缘环境遮蔽不透明度，soft 左上柔光不透明度，
#       spec1/spec2 柔核/锐核高光不透明度，bounce_a 回光不透明度，
#       side/side_col 背光侧压暗的不透明度与颜色。
_PALETTE = {
    "black": dict(hi="#4E5A6B", lo="#07090C", rim="#000000",
                  spec="#E6EEF8", bounce="#7A8AA0",
                  ao=125, soft=62, spec1=190, spec2=245, bounce_a=165,
                  side=116, side_col="#04060A", rim_a=190),
    "white": dict(hi="#FFFDF6", lo="#9A9182", rim="#5E5847",
                  spec="#FFFFFF", bounce="#FFF6E2",
                  ao=172, soft=74, spec1=205, spec2=255, bounce_a=205,
                  side=150, side_col="#6A6252", rim_a=215),
}


def _ell_mask(size, cx, cy, rx, ry):
    """L 模式椭圆遮罩（超采样坐标系）。"""
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    return m


def render_stone(r, col, ss=None):
    """渲染一枚棋子，返回 RGBA 图像（含投影留白，视觉半径 = r）。"""
    if not _PIL_OK:
        return None
    S = int(ss or SS)
    r = float(r)
    R = r * S
    if R < 2:
        return None

    # 投影模糊半径：投影越紧致越自然；模糊过大会被图片矩形边界裁切，
    # 在棋子周围形成明显的"正方形阴影光环"（这正是此前光环的根因）。
    blur_env = R * 0.22          # 环境投影：柔和但克制
    blur_con = R * 0.12          # 接触投影：贴合棋底、清晰
    # 留白必须包住"模糊后的投影"：椭圆半径 + 偏移 + 约 3×模糊半径，
    # 否则高斯模糊会在图片矩形边界被截断 → 形成方形光环。
    shadow_extent = R * 1.04 + R * 0.14 + 3 * max(blur_env, blur_con)
    pad = int(round(shadow_extent + 6 * S))
    size = int(2 * R + 2 * pad) + 2
    cx = cy = size / 2.0

    # ---- 球面光影贴图：径向渐变，光源置于左上 ----
    gsz = int(2.9 * R) + 1
    g = Image.radial_gradient("L").resize((gsz, gsz), Image.BILINEAR)
    g = ImageChops.invert(g)                    # 中心亮、边缘暗
    lx, ly = cx - R * 0.34, cy - R * 0.36       # 光源点（左上）
    offx = int(round(gsz / 2.0 - lx))
    offy = int(round(gsz / 2.0 - ly))
    shade = g.crop((offx, offy, offx + size, offy + size))

    pal = _PALETTE["black" if str(col).lower().startswith("b") or col == 1
                   else "white"]
    hi, lo = pal["hi"], pal["lo"]

    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # ---------- 1) 环境投影（柔和、范围小、克制，避免方形光环） ----------
    base = _bf._over(base, _bf._tint(
        _ell_mask((size, size), cx, cy + R * 0.10, R * 0.98, R * 0.96),
        "#000000", alpha=64, blur=blur_env))
    # ---------- 2) 接触投影（贴合棋底、更实，形成真实"棋子坐于盘面"的立体感） ----------
    base = _bf._over(base, _bf._tint(
        _ell_mask((size, size), cx, cy + R * 0.14, R * 0.92, R * 0.90),
        "#000000", alpha=150, blur=blur_con))

    # ---- 棋子本体单独成层，最后按圆形裁掉溢出部分 ----
    stone = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    circle = _ell_mask((size, size), cx, cy, R, R)

    # ---------- 3) 球面渐变（径向衰减） ----------
    body = Image.composite(
        Image.new("RGB", (size, size), _bf._parse(hi)),
        Image.new("RGB", (size, size), _bf._parse(lo)),
        shade).convert("RGBA")
    body.putalpha(circle)
    stone = _bf._over(stone, body)

    # ---------- 4) 边缘环境遮蔽（外圈压暗，勾出球感） ----------
    inner = _ell_mask((size, size), cx, cy, R * 0.88, R * 0.88)
    ao = ImageChops.subtract(circle, inner)
    stone = _bf._over(stone, _bf._tint(ao, "#000000",
                                       alpha=pal["ao"], blur=R * 0.10))

    # ---------- 4b) 背光侧压暗（右下"背光月牙" —— 浅色棋子立体感的核心） ----------
    # 只压在光线的反方向（乘上 shade 的反相遮罩），越靠右下越暗，
    # 于是球面出现明确的明暗交界（terminator），不再是"一片白"。
    if pal.get("side", 0) > 0:
        side_m = _ell_mask((size, size), cx + R * 0.40, cy + R * 0.46,
                           R * 0.98, R * 0.98)
        side_m = _bf._mul(_bf._mul(side_m, circle),
                          ImageChops.invert(shade))
        stone = _bf._over(stone, _bf._tint(side_m, pal.get("side_col", "#000000"),
                                           alpha=pal["side"], blur=R * 0.26))

    # ---------- 5) 底部回光（右下缘反弹光，通透感关键） ----------
    ring = ImageChops.subtract(circle, _ell_mask((size, size), cx, cy,
                                                 R * 0.92, R * 0.92))
    bounce_a = _bf._mul(ring, ImageChops.invert(shade))
    stone = _bf._over(stone, _bf._tint(bounce_a, pal["bounce"],
                                       alpha=pal["bounce_a"], blur=R * 0.09))

    # ---------- 6) 左上大面积柔光 ----------
    stone = _bf._over(stone, _bf._tint(
        _ell_mask((size, size), cx - R * 0.28, cy - R * 0.32, R * 0.50, R * 0.40),
        "#FFFFFF", alpha=pal["soft"], blur=R * 0.22))

    # ---------- 7) 镜面高光：柔核 + 锐核（白棋靠它"点亮"顶部，形成体积感） ----------
    stone = _bf._over(stone, _bf._tint(
        _ell_mask((size, size), cx - R * 0.33, cy - R * 0.38, R * 0.27, R * 0.19),
        pal["spec"], alpha=pal["spec1"], blur=R * 0.08))
    stone = _bf._over(stone, _bf._tint(
        _ell_mask((size, size), cx - R * 0.37, cy - R * 0.43, R * 0.105, R * 0.068),
        pal["spec"], alpha=pal["spec2"], blur=R * 0.025))

    # 裁成圆形（抗锯齿边缘在此产生）
    stone.putalpha(_bf._mul(stone.split()[3], circle))
    base = _bf._over(base, stone)

    # ---------- 8) 清晰外缘描边（1px，强化轮廓） ----------
    outer = _ell_mask((size, size), cx, cy, R - 0.5 * S, R - 0.5 * S)
    outer_in = _ell_mask((size, size), cx, cy, R - 1.5 * S, R - 1.5 * S)
    rim = ImageChops.subtract(outer, outer_in)
    rim = _bf._mul(rim, circle)
    base = _bf._over(base, _bf._tint(rim, pal["rim"], alpha=pal["rim_a"]))

    return base.resize((int(size / S) + 1, int(size / S) + 1), Image.LANCZOS)


def get_stone_photo(canvas, r, col):
    """取得（或生成并缓存）棋子 PhotoImage。半径量化取整，避免尺寸抖动。"""
    if not (_PIL_OK and _TK_OK):
        return None
    rq = max(2, int(round(float(r))))
    ck = ("black" if str(col).lower().startswith("b") or col == 1 else "white")
    key = (rq, ck)
    ph = _CACHE.get(key)
    if ph is not None:
        return ph
    img = render_stone(rq, ck)
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
    return bool(_PIL_OK and _TK_OK)
