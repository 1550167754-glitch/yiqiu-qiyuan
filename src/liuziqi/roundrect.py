# -*- coding: utf-8 -*-
"""
roundrect.py —— 像素级锐利的圆角矩形绘制工具 + 统一 3D 立体按钮渲染器。

设计要点（针对「按钮边缘模糊、无立体通透感」问题）：
- 圆角用**足够密集的弧点 + 直线段**拟合（smooth=False），而不是 Tk 的
  smooth=True 贝塞尔样条。smooth=True 会把顶点当作样条控制点，产生圆角处
  "发糊/锯齿状"的软边；直线段拟合在整数像素上是锐利、清晰的。
- 3D 立体感用「下滑 depth 的暗色基座 + 顶部受光 sheen 半区 + 1px 清晰描边
  + 顶部高光高光线」实现：露出基座底部作为按钮侧壁，呈现真正凸起的厚度，
  而非半透明阴影那种发糊的观感。
"""

import math

from . import buttonfx


def _clamp_channel(v):
    return max(0, min(255, int(round(v))))


def _hex(color):
    c = color.lstrip("#")
    if len(c) == 3:
        c = c[0] * 2 + c[1] * 2 + c[2] * 2
    return c[0:2], c[2:4], c[4:6]


def _parse(color):
    r, g, b = _hex(color)
    return int(r, 16), int(g, 16), int(b, 16)


def _to_hex(rgb):
    r, g, b = rgb
    return "#%02X%02X%02X" % (_clamp_channel(r), _clamp_channel(g), _clamp_channel(b))


def _mix(c1, c2, ratio):
    """线性混合两颜色，ratio=0 取 c1，=1 取 c2。"""
    r1, g1, b1 = _parse(c1)
    r2, g2, b2 = _parse(c2)
    return _to_hex((r1 + (r2 - r1) * ratio,
                    g1 + (g2 - g1) * ratio,
                    b1 + (b2 - b1) * ratio))


def _shade(color, factor):
    """按 factor 压暗(<1)/提亮(>1)。"""
    r, g, b = _parse(color)
    return _to_hex((r * factor, g * factor, b * factor))


def rounded_rect_points(x0, y0, x1, y1, r, steps=9):
    """返回圆角矩形顶点列表（顺时针），用于 create_polygon。

    r 可为标量（四角同半径）或 (tl, tr, br, bl) 四元组（分别控制四角）。
    弧用 steps 段直线拟合，smooth=False 时边缘像素级锐利。
    """
    if isinstance(r, (list, tuple)):
        tl, tr, br, bl = r
    else:
        tl = tr = br = bl = r
    max_r = min(max(0.0, (x1 - x0) / 2.0), max(0.0, (y1 - y0) / 2.0))

    def _c(v):
        return max(0.0, min(float(v), max_r))

    tl, tr, br, bl = _c(tl), _c(tr), _c(br), _c(bl)
    pts = []
    # 起点：上边左侧
    pts.append(x0 + tl); pts.append(y0)
    # 右上角：中心 (x1-tr, y0+tr)，角度 -90°→0°
    cx, cy = x1 - tr, y0 + tr
    for i in range(steps + 1):
        a = -math.pi / 2 + (math.pi / 2) * (i / steps)
        pts.append(cx + tr * math.cos(a)); pts.append(cy + tr * math.sin(a))
    # 右下角：中心 (x1-br, y1-br)，角度 0°→90°
    cx, cy = x1 - br, y1 - br
    for i in range(steps + 1):
        a = 0 + (math.pi / 2) * (i / steps)
        pts.append(cx + br * math.cos(a)); pts.append(cy + br * math.sin(a))
    # 左下角：中心 (x0+bl, y1-bl)，角度 90°→180°
    cx, cy = x0 + bl, y1 - bl
    for i in range(steps + 1):
        a = math.pi / 2 + (math.pi / 2) * (i / steps)
        pts.append(cx + bl * math.cos(a)); pts.append(cy + bl * math.sin(a))
    # 左上角：中心 (x0+tl, y0+tl)，角度 180°→270°
    cx, cy = x0 + tl, y0 + tl
    for i in range(steps + 1):
        a = math.pi + (math.pi / 2) * (i / steps)
        pts.append(cx + tl * math.cos(a)); pts.append(cy + tl * math.sin(a))
    return pts


def draw_3d_button(c, w, h, *, base, fg, text, font,
                  hover=False, pressed=False, enabled=True,
                  radius=None):
    """在画布 c 上绘制一枚立体通透的光影按钮。

    首选路径：PIL 超采样 + 真 Alpha 合成（buttonfx）。Tk Canvas 不支持
    抗锯齿与半透明，create_polygon 画的圆角必然带阶梯毛边；PIL 路径用
    4× 超采样渲染出真正的平滑边缘与半透明玻璃高光，是「锐利 + 通透」的
    根本解。PIL 不可用时回退到内置矢量绘制。
    """
    # 关键防御：延迟回调（按钮释放后的 after_idle 指针对账）可能在控件
    # 被销毁之后才执行。此时该控件的 Tcl 路径已失效，任何 cget/delete
    # 都会抛 TclError（invalid command name）。这里统一拦截，作为最后一道
    # 防线，保护所有调用方（GlowButton / 弹窗按钮 / MediaButton）。
    try:
        if not c.winfo_exists():
            return
    except Exception:
        return
    c.delete("all")
    try:
        w = int(w); h = int(h)
    except Exception:
        return
    if w <= 0 or h <= 0:
        return
    if buttonfx.available():
        try:
            photo = buttonfx.get_button_photo(
                c, w, h, base, fg, text, font,
                hover=hover, pressed=pressed, enabled=enabled, radius=radius)
        except Exception:
            photo = None
        if photo is not None:
            # 持有引用防止 PhotoImage 被垃圾回收
            c._btnfx_photo = photo
            c.create_image(0, 0, anchor="nw", image=photo)
            return
    _draw_3d_button_vector(c, w, h, base=base, fg=fg, text=text, font=font,
                           hover=hover, pressed=pressed, enabled=enabled,
                           radius=radius)


def _draw_3d_button_vector(c, w, h, *, base, fg, text, font,
                           hover=False, pressed=False, enabled=True,
                           radius=None):
    """矢量回退路径（无 PIL 环境）：密集弧点 + 直线段拟合，整数像素锐利。

    层次（从下到上）：
        1) 3D 厚度基座（下滑 depth 的暗色实体，露出底部作侧壁）
        2) 悬停/按下外发光细环（清晰 1px+1px，不糊）
        3) 棋面主体（下暗色）
        4) 顶部受光 sheen 半区（仅上圆角，玻璃通透感）
        5) 1px 清晰描边
        6) 顶部高光高光线
        7) 按下内阴影（内陷触感）
        8) 居中文字（按下时下沉 2px + 略压暗）
    """
    c.delete("all")
    try:
        w = int(w); h = int(h)
    except Exception:
        return
    if w <= 0 or h <= 0:
        return
    if radius is None:
        radius = min(12, max(2, int(h / 2.2)))
    r = radius
    depth = 0 if (not enabled) else 3

    if not enabled:
        face = base
        face_top = _mix(face, "#FFFFFF", 0.05)
        border = _mix(face, "#000000", 0.20)
        face_off = 0
        glow = False
    elif pressed:
        face = _shade(base, 0.82)
        face_top = _mix(face, "#FFFFFF", 0.05)
        border = _mix(base, "#FFFFFF", 0.28)
        face_off = depth
        glow = True
    elif hover:
        face = _mix(base, "#FFFFFF", 0.13)
        face_top = _mix(face, "#FFFFFF", 0.17)
        border = _mix(base, "#FFFFFF", 0.42)
        face_off = 0
        glow = True
    else:
        face = base
        face_top = _mix(face, "#FFFFFF", 0.12)
        border = _mix(base, "#FFFFFF", 0.24)
        face_off = 0
        glow = False

    # 1) 3D 厚度基座（暗色下滑实体，露出底部作为侧壁）
    if depth > 0:
        c.create_polygon(
            rounded_rect_points(1, 1 + depth, w - 1, h - 1 + depth, r),
            fill=_shade(base, 0.6), outline="", width=0)
    # 2) 悬停/按下外发光细环（清晰，不溢出画布）
    if glow:
        gc = (_mix(border, "#FFFFFF", 0.5) if pressed
              else _mix(border, "#FFFFFF", 0.40))
        c.create_polygon(
            rounded_rect_points(1, 1 + face_off, w - 1, h - 1 + face_off, r),
            fill="", outline=gc, width=2)
    # 3) 棋面主体（下暗色）
    fy0 = 1 + face_off
    fy1 = h - 1 + face_off
    c.create_polygon(rounded_rect_points(1, fy0, w - 1, fy1, r),
                     fill=face, outline="", width=0)
    # 4) 顶部受光 sheen 半区（仅上圆角，玻璃通透感）
    sheen_h = max(4, int((fy1 - fy0) * 0.5))
    c.create_polygon(
        rounded_rect_points(2, fy0 + 1, w - 2, fy0 + sheen_h,
                            (max(1, r - 1), max(1, r - 1), 0, 0)),
        fill=face_top, outline="", width=0)
    # 5) 清晰 1px 描边
    c.create_polygon(rounded_rect_points(1, fy0, w - 1, fy1, r),
                     fill="", outline=border, width=1)
    # 6) 顶部高光高光线
    c.create_line(r + 2, fy0 + 1.5, w - r - 2, fy0 + 1.5,
                  fill=_mix(face_top, "#FFFFFF", 0.7), width=1)
    # 7) 按下内阴影（内陷触感）
    if pressed and enabled:
        c.create_polygon(
            rounded_rect_points(4, fy0 + 3, w - 4, fy1 - 3, max(1, r - 3)),
            fill="", outline=_shade(face, 0.62), width=1)
    # 8) 文字（按下时下沉 + 略压暗）
    ty = h / 2 + face_off
    fgc = _mix(fg, "#000000", 0.12) if (pressed and enabled) else fg
    c.create_text(w / 2, ty, text=text, fill=fgc, font=font, anchor="center")
