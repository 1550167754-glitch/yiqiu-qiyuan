# -*- coding: utf-8 -*-
"""
styled_dialog.py —— 游戏内"带花纹"自绘弹窗（替代系统 messagebox）

设计动机：
    系统原生 messagebox 在深色程序里显得突兀，也无法自定义。这里提供一个
    全自绘的 Toplevel：以 canvas 绘制深色底 + 金色回纹边框 + 四角卷草纹 +
    顶部祥云角花，观感统一、精致，适合"对战结束""数据库询问"等游戏内提示。

使用方式：
    dlg = OrnateDialog(master, title="对局结束", width=460, height=340)
    dlg.add_text(...)            # 可选：主内容文字
    dlg.add_button("复盘", cb, accent=True)
    dlg.add_button("重新开始", cb)
    ...                          # 按钮会在底部一行排开
    dlg.open()                   # 置顶显示
    dlg.close()                  # 销毁（回调里调用）

配色沿用主程序深色现代风格：主底 #1F2430 / 金 #E8B34B。
"""
from __future__ import annotations

import tkinter as tk

# 主程序通用深色调
DG_BG = "#1F2430"
DG_BG2 = "#171B24"
DG_PANEL = "#262C3A"
DG_BORDER = "#353D4F"
DG_TEXT = "#EDEFF4"
DG_DIM = "#9AA3B2"
DG_GOLD = "#E8B34B"
DG_GOLD_D = "#C9972F"
DG_CONFIRM = "#3EBB6B"
FONT_FAMILY = "Microsoft YaHei UI"

from .roundrect import draw_3d_button


def _blend(c1: str, c2: str, ratio: float) -> str:
    r = int(int(c1[1:3], 16) + (int(c2[1:3], 16) - int(c1[1:3], 16)) * ratio)
    g = int(int(c1[3:5], 16) + (int(c2[3:5], 16) - int(c1[3:5], 16)) * ratio)
    b = int(int(c1[5:7], 16) + (int(c2[5:7], 16) - int(c1[5:7], 16)) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


def _shade(color: str, factor: float) -> str:
    c = color.lstrip("#")
    r = int(int(c[0:2], 16) * factor)
    g = int(int(c[2:4], 16) * factor)
    b = int(int(c[4:6], 16) * factor)
    return f"#{max(0,min(255,r)):02X}{max(0,min(255,g)):02X}{max(0,min(255,b)):02X}"


# ------------------------------------------------------------------ 状态徽章
_BADGE_COLORS = {
    "ok":   ("#58C08A", "#7FE0AC"),     # 就绪：绿
    "warn": ("#E8B34B", "#F5D48A"),     # 需处理：琥珀
    "db":   ("#7E8AA0", "#B8C2D4"),     # 未安装：石板蓝
    "info": ("#E8B34B", "#F5D48A"),     # 一般提示：金
}


def _parse_hex(c):
    c = (c or "#000000").lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _render_badge(kind: str, size: int):
    """渲染圆形状态徽章（4× 超采样 + LANCZOS 降采样，真抗锯齿边缘）。

    kind：ok（对勾）/ warn（感叹号）/ db（数据库圆柱）/ info（i）。
    """
    from PIL import Image, ImageDraw, ImageFilter
    S = 4
    W = int(size) * S
    R = W // 2
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    cx = cy = W / 2.0
    ring, sym = _BADGE_COLORS.get(kind, _BADGE_COLORS["info"])
    ring_rgb, sym_rgb = _parse_hex(ring), _parse_hex(sym)

    d = ImageDraw.Draw(img)
    # 1) 底盘（深色内芯，带 1px 内收，为柔光晕留出溢出空间）
    d.ellipse([cx - R * 0.82, cy - R * 0.82, cx + R * 0.82, cy + R * 0.82],
              fill=(35, 41, 54, 255))
    # 2) 主环 + 外圈柔光（两层：亮环 + 暗金细环）
    d.ellipse([cx - R * 0.82, cy - R * 0.82, cx + R * 0.82, cy + R * 0.82],
              outline=ring_rgb + (255,), width=max(2, int(R * 0.085)))
    d.ellipse([cx - R * 0.68, cy - R * 0.68, cx + R * 0.68, cy + R * 0.68],
              outline=_parse_hex(_shade(ring, 0.55)) + (200,),
              width=max(1, int(R * 0.03)))
    # 3) 符号
    lw = max(3, int(R * 0.15))
    if kind == "ok":
        pts = [(cx - R * 0.30, cy + 0.03 * R), (cx - R * 0.09, cy + 0.25 * R),
               (cx + R * 0.34, cy - R * 0.22)]
        d.line(pts, fill=sym_rgb + (255,), width=lw, joint="curve")
        for p in (pts[0], pts[-1]):
            r2 = lw / 2
            d.ellipse([p[0] - r2, p[1] - r2, p[0] + r2, p[1] + r2],
                      fill=sym_rgb + (255,))
    elif kind == "warn":
        bw = R * 0.17
        d.rounded_rectangle([cx - bw / 2, cy - R * 0.34,
                             cx + bw / 2, cy + R * 0.12],
                            radius=bw / 2, fill=sym_rgb + (255,))
        r2 = R * 0.10
        d.ellipse([cx - r2, cy + R * 0.24 - r2, cx + r2, cy + R * 0.24 + r2],
                  fill=sym_rgb + (255,))
    elif kind == "db":
        # 数据库圆柱：顶椭圆 + 两侧壁 + 底弧 + 中部束带
        ry = R * 0.16
        rx = R * 0.34
        top = cy - R * 0.30
        bot = cy + R * 0.34
        d.ellipse([cx - rx, top - ry, cx + rx, top + ry],
                  outline=sym_rgb + (255,), width=lw)
        d.line([(cx - rx, top), (cx - rx, bot)], fill=sym_rgb + (255,), width=lw)
        d.line([(cx + rx, top), (cx + rx, bot)], fill=sym_rgb + (255,), width=lw)
        d.arc([cx - rx, bot - ry, cx + rx, bot + ry], start=0, end=180,
              fill=sym_rgb + (255,), width=lw)
        mid = (top + bot) / 2
        d.arc([cx - rx, mid - ry, cx + rx, mid + ry], start=0, end=180,
              fill=_parse_hex(_shade(sym, 0.7)) + (255,), width=max(2, lw - 2))
    else:  # info
        r2 = R * 0.09
        d.ellipse([cx - r2, cy - R * 0.34 - r2, cx + r2, cy - R * 0.34 + r2],
                  fill=sym_rgb + (255,))
        bw = R * 0.16
        d.rounded_rectangle([cx - bw / 2, cy - R * 0.14,
                             cx + bw / 2, cy + R * 0.34],
                            radius=bw / 2, fill=sym_rgb + (255,))

    # 4) 外柔光晕（最后叠加，发光感）
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [cx - R * 0.88, cy - R * 0.88, cx + R * 0.88, cy + R * 0.88],
        outline=ring_rgb + (110,), width=max(3, int(R * 0.10)))
    glow = glow.filter(ImageFilter.GaussianBlur(R * 0.14))
    img = Image.alpha_composite(glow, img)

    return img.resize((int(size), int(size)), Image.LANCZOS)


class OrnateDialog(tk.Toplevel):
    """带花纹边框的自绘弹窗基类。"""

    def __init__(self, master=None, title: str = "提示",
                 width: int = 460, height: int = 340,
                 subtitle: str = "", body_bg: str | None = None):
        super().__init__(master)
        # 先移到屏幕外隐藏，布局完成再由 open() 居中显示，避免闪现在角落
        self.title(title)
        self.configure(bg=DG_BG)
        self.resizable(False, False)
        self._title_text = title
        self._subtitle = subtitle
        # 注意：不要用 self._w 命名宽度——tkinter 内部用 self._w 存窗口 Tcl 路径名，
        # 覆写它会导致后续 wm geometry / destroy 等报 "bad window path name"。
        # ---- DPI 自适应：字体随系统缩放，而像素框不会——若不按同比放大框体，
        # 高分屏下文字必然被裁剪。调用方传入的 width/height 均按 96 DPI 设计，
        # 这里乘以实际缩放系数（tk scaling / 1.3333）。 ----
        try:
            s = float(self.tk.call("tk", "scaling")) / 1.3333
        except Exception:
            s = 1.0
        s = max(1.0, min(s, 2.4))
        self._dpi_s = s
        self._dlg_w = int(width * s)
        self._dlg_h = int(height * s)
        # 主体区背景固定为内衬面板色（与花纹外的内衬一致），保证文字不与花纹重叠
        self._body_bg = body_bg or DG_PANEL
        # 标题带底部位置（y）：margin(14) + 标题(40) + 双线(24) + 副标题(44) + 留白(6) = 128
        # 即正文区从 y=128 开始，必然避开所有花纹（随 DPI 同比放大）
        self._title_band_h = int(128 * s)
        # 底部按钮区高度（按钮 40 + 上下 pad 各 12 = 64，再加 4 底边距 = 68）
        self._button_band_h = int(68 * s)
        # 正文区可用高度
        self._content_h = max(80, self._dlg_h - self._title_band_h - self._button_band_h)
        self.geometry(f"+{-32000}+{-32000}")   # 屏外占位（withdraw 会引发 Tk path 异常）
        self._buttons: list[tk.Widget] = []
        # 内部 content row 框架（用于放正文+按钮，grid 布局）
        self._content_frame: tk.Frame | None = None

        # 自绘画布
        self.canvas = tk.Canvas(self, width=width, height=height,
                                bg=DG_BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # 主体内容容器（place 到画布内，供子类放置控件/按钮）
        # 主体 Frame 的 bg 设为面板色，与花纹外的内衬一致 → 文字底色与花纹清晰区分
        self.body = tk.Frame(self.canvas, bg=self._body_bg)
        self._body_id = None

        # 鼠标拖动窗口
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)

        # 模态（阻塞父窗口交互，但不阻塞主循环）
        # 重要：grab 必须挪到 open() 中、窗口真正可见后再设置（见 open()）。
        # 若在 __init__ 就 grab，一旦构造/显示阶段抛异常，grab 会泄漏，
        # 主窗口被"看不见的弹窗"冻结（点不动、关不掉），且看门狗无法察觉
        # —— grab 不阻塞 Tk 事件循环，主线程仍显示 idle。
        try:
            self.transient(master)
        except Exception:
            pass
        # 兜底：窗口销毁时无论如何释放 grab，防止泄漏冻结主窗口
        try:
            self.bind("<Destroy>", lambda _e=None: self._safe_release_grab())
        except Exception:
            pass

    # ---- 窗口拖动 ----
    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        try:
            self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")
        except Exception:
            pass

    # ---- 几何 ----
    def _center(self):
        """相对主窗口居中（多屏/高分屏下也保证落在可见区域）。
        回退：主窗口不可用时再退到屏幕中心；再不行退到左上可见区。
        关键：定位后强制夹紧到屏幕可见范围内，杜绝任何"屏外弹窗"。"""
        try:
            m = self.master
            if m is not None and hasattr(m, "winfo_rootx"):
                mx = m.winfo_rootx(); my = m.winfo_rooty()
                mw = m.winfo_width(); mh = m.winfo_height()
                x = mx + (mw - self._dlg_w) // 2
                y = my + (mh - self._dlg_h) // 2
            else:
                sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
                if sw <= 0 or sh <= 0:
                    raise ValueError("invalid screen size")
                x = (sw - self._dlg_w) // 2
                y = (sh - self._dlg_h) // 2
            # 下界保护：绝不出现负坐标（多屏/异常定位），也不允许留在屏外。
            # 不做上界夹紧——若主窗口在副屏，弹窗应落在副屏（用户正看着处）。
            try:
                x = max(0, int(x)); y = max(0, int(y))
            except Exception:
                x = max(0, int(x)); y = max(0, int(y))
            self.geometry(f"{self._dlg_w}x{self._dlg_h}+{x}+{y}")
        except Exception:
            # 兜底：放到左上可见区域，绝不留在屏外 (+{-32000})，
            # 否则窗口不可见却仍 grab，会冻结主窗口。
            try:
                self.geometry(f"{self._dlg_w}x{self._dlg_h}+80+80")
            except Exception:
                pass

    # ---- 花纹装饰 ----
    def _ornate_border(self):
        """绘制整体装饰背景：渐变 + 双线回纹边框 + 四角卷草 + 标题带。
        花纹全部位于"标题带"（顶部 ~110px）内，主体正文区与按钮区为纯色面板，
        保证文字与花纹不重叠。"""
        c = self.canvas
        w, h = self._dlg_w, self._dlg_h
        c.delete("all")

        # 背景渐变（深蓝灰 → 更暗）
        steps = 20
        for i in range(steps):
            y0 = int(h * i / steps); y1 = int(h * (i + 1) / steps) + 1
            c.create_rectangle(0, y0, w, y1,
                               fill=_blend(DG_BG, DG_BG2, i / (steps - 1)),
                               outline="")
        # 内衬面板（覆盖整个画布，作为花纹下方的底色）
        margin = 14
        c.create_rectangle(margin, margin, w - margin, h - margin,
                           fill=DG_PANEL, outline="")
        # 主体正文区：纯色面板（与花纹带分隔，避免文字与花纹重叠）
        body_y0 = self._title_band_h - 4   # 标题带底部再下移 4px
        body_y1 = h - self._button_band_h + 4
        c.create_rectangle(margin, body_y0, w - margin, body_y1,
                           fill=DG_PANEL, outline="")
        # 正文区上沿装饰：一条暗金细线作为正文与标题带的柔和分界
        c.create_line(margin + 8, body_y0, w - margin - 8, body_y0,
                      fill=DG_BORDER, width=1)
        c.create_line(margin + 8, body_y1, w - margin - 8, body_y1,
                      fill=DG_BORDER, width=1)
        # 主金框（双线）—— 围绕整个对话框
        m2 = margin + 6
        c.create_rectangle(m2, m2, w - m2, h - m2,
                           outline=DG_GOLD, width=1)
        c.create_rectangle(m2 + 3, m2 + 3, w - m2 - 3, h - m2 - 3,
                           outline=DG_GOLD_D, width=1)
        # 四角卷草纹（顶部两角 + 底部对称两角，远离正文与按钮文字）
        self._corner_scroll(m2 + 2, m2 + 2, +1, +1)
        self._corner_scroll(w - m2 - 2, m2 + 2, -1, +1)
        self._corner_scroll(m2 + 2, h - m2 - 2, +1, -1)
        self._corner_scroll(w - m2 - 2, h - m2 - 2, -1, -1)
        # 顶/底部回纹短线带（左右两段对称）—— 仅画在标题带与按钮带，远离正文
        y_top = m2 + 18
        for cx0 in (m2 + 26, w - m2 - 26):
            sign = 1 if cx0 < w / 2 else -1
            x = cx0
            for _k in range(6):
                c.create_line(x, y_top, x + sign * 8, y_top, fill=DG_GOLD_D)
                c.create_line(x + sign * 8, y_top, x + sign * 8,
                              y_top - 6, fill=DG_GOLD_D)
                x += sign * 16
        # 标题与副题
        ty = margin + 40
        c.create_text(w / 2, ty, text=self._title_text,
                      fill=DG_GOLD, font=(FONT_FAMILY, 18, "bold"))
        # 标题下双线装饰 + 中央菱形徽饰
        lw = min(120, int(w * 0.28))
        c.create_line(w / 2 - lw, ty + 20, w / 2 - 12, ty + 20,
                      fill=DG_GOLD_D, width=1)
        c.create_line(w / 2 + 12, ty + 20, w / 2 + lw, ty + 20,
                      fill=DG_GOLD_D, width=1)
        c.create_line(w / 2 - lw + 10, ty + 24, w / 2 - 12, ty + 24,
                      fill=DG_BORDER, width=1)
        c.create_line(w / 2 + 12, ty + 24, w / 2 + lw - 10, ty + 24,
                      fill=DG_BORDER, width=1)
        md = 5      # 中央小菱形 + 两侧点
        c.create_polygon(w / 2, ty + 16, w / 2 + md, ty + 22, w / 2, ty + 28,
                         w / 2 - md, ty + 22, fill=DG_GOLD, outline="")
        c.create_oval(w / 2 - md - 7, ty + 21, w / 2 - md - 3, ty + 25,
                      fill=DG_GOLD_D, outline="")
        c.create_oval(w / 2 + md + 3, ty + 21, w / 2 + md + 7, ty + 25,
                      fill=DG_GOLD_D, outline="")
        if self._subtitle:
            c.create_text(w / 2, ty + 44, text=self._subtitle,
                          fill=DG_DIM, font=(FONT_FAMILY, 11))

    def _corner_scroll(self, cx, cy, sx, sy):
        """在角点画一小段卷草纹（两条小弧），sx/sy 决定朝向。"""
        c = self.canvas
        col = DG_GOLD
        # 外卷
        c.create_arc(cx - 14 * sx, cy - 14 * sy, cx + 4 * sx, cy + 4 * sy,
                     start=0, extent=260 if sx * sy > 0 else 200,
                     style="arc", outline=col, width=2)
        # 内点卷
        c.create_arc(cx - 6 * sx, cy - 6 * sy, cx + 2 * sx, cy + 2 * sy,
                     start=90, extent=240,
                     style="arc", outline=_blend(col, DG_BG, 0.3), width=2)
        c.create_oval(cx - 1, cy - 1, cx + 1, cy + 1,
                      fill=col, outline="")

    def place_body(self, x: int | None = None, y: int | None = None,
                   width: int | None = None, height: int | None = None):
        """在画布上放置主体内容 frame。
        使用 grid 布局：正文区(row0, 可扩展) + 按钮区(row1, 固定高度)，
        无论正文多长都不会挤压按钮，保证按钮始终可见。"""
        self._ornate_border()
        # 清除旧 body window
        try:
            if self._body_id is not None:
                self.canvas.delete(self._body_id)
        except Exception:
            pass
        # 默认位置：正文区
        if x is None:
            x = 24
        if y is None:
            y = self._title_band_h + 4
        if width is None:
            width = self._dlg_w - 48
        if height is None:
            height = self._content_h - 8
        # 主体 Frame：bg 与花纹外的面板色一致
        self.body = tk.Frame(self.canvas, bg=self._body_bg)
        self._body_id = self.canvas.create_window(x, y, anchor="nw",
                                                  window=self.body,
                                                  width=width, height=height)
        # 内部 content_frame 用 grid：row0=正文(可扩展)，row1=按钮(固定)
        self._content_frame = tk.Frame(self.body, bg=self._body_bg)
        self._content_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self._content_frame.grid_rowconfigure(0, weight=1)   # 正文行可扩展
        self._content_frame.grid_rowconfigure(1, weight=0)   # 按钮行固定
        self._content_frame.grid_columnconfigure(0, weight=1)
        # 正文容器（add_text 打到这里）。
        # 行布局：row0 = 顶部弹性空白(weight=1)，随后徽章/文字依次入行，
        # 每次追加后把"下一行"设为底部弹性空白(weight=1)——内容组整体垂直居中。
        self._text_frame = tk.Frame(self._content_frame, bg=self._body_bg)
        self._text_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=(6, 4))
        self._text_frame.grid_rowconfigure(0, weight=1)
        self._text_frame.grid_columnconfigure(0, weight=1)
        self._text_row = 1                       # 下一个可用行
        self._text_frame.grid_rowconfigure(1, weight=1)   # 底部弹性空白

    def add_text(self, text: str, parent=None, fg: str = DG_TEXT,
                 size: int = 12, wraplength: int | None = None,
                 pady: int | tuple = 6, mono: bool = False):
        """在 body 中添加一段文字。文字打到正文容器（grid row0），
        与按钮区(row1)物理分隔。wraplength 为 96 DPI 设计值，随 DPI 放大。
        mono=True 用等宽字体并左对齐（成绩/战绩表格对齐用）。"""
        parent = parent or self._text_frame
        # wraplength 必须不超过标签实际可用宽度（_dlg_w - 84：边距24*2 +
        # body padx 4*2 + label padx 10*2 再留余量），否则会被迫二次换行，
        # 行数超出高度预算 -> 文字被裁剪（这正是 PG 弹窗裁字的根因）。
        maxw = max(120, self._dlg_w - 84)
        if wraplength is not None:
            wraplength = max(80, min(int(wraplength * self._dpi_s), maxw))
        else:
            wraplength = maxw
        fam = "Consolas" if mono else FONT_FAMILY
        lb = tk.Label(parent, text=text, bg=self._body_bg, fg=fg,
                      font=(fam, size),
                      justify="left" if mono else "center",
                      anchor="w" if mono else "center",
                      wraplength=wraplength)
        if parent is self._text_frame:
            # 注意：不要绑定 <Configure> 动态改 wraplength——布局初期宽度是
            # 1px，会把 wraplength 钳到极小值导致文字爆行数、正文被裁。
            # 静态上限（_dlg_w - 84）已保证不二次换行。
            pady = pady if isinstance(pady, tuple) else (pady, pady)
            self._grid_text_row(lb, sticky="ew", pady=pady)
        else:
            lb.grid(sticky="ew", padx=10, pady=pady)
        return lb

    # ---- 状态徽章（PIL 渲染的圆形徽标，提升弹窗精致度） ----
    def _grid_text_row(self, widget, sticky, pady):
        """把正文组件放入下一个可用行，并维护底部弹性空白（内容组居中）。"""
        widget.grid(row=self._text_row, column=0, sticky=sticky, padx=10,
                    pady=pady)
        self._text_row += 1
        self._text_frame.grid_rowconfigure(self._text_row, weight=1)
        # 清掉旧行的弹性权重（避免多个行同时 expand）
        for r in range(1, self._text_row):
            self._text_frame.grid_rowconfigure(r, weight=0)

    def add_status_icon(self, kind: str = "info", size: int = 58):
        """在正文区顶部居中添加一枚状态徽章。

        kind：ok（绿色对勾，就绪）/ warn（琥珀感叹号，需处理）/
              db（数据库圆柱，未安装）/ info（金色 i，一般提示）。
        无 PIL 环境时静默跳过（弹窗仍可用）。
        """
        ph = self._badge_photo(kind, max(40, int(size * self._dpi_s)))
        if ph is None:
            return None
        cv = tk.Canvas(self._text_frame, width=ph.width(), height=ph.height(),
                       bg=self._body_bg, highlightthickness=0, bd=0)
        cv.create_image(0, 0, anchor="nw", image=ph)
        cv._badge_img = ph            # 防 GC
        self._grid_text_row(cv, sticky="n", pady=(8, 0))
        return cv

    @staticmethod
    def _badge_photo(kind, size):
        """渲染徽章并返回 PhotoImage；失败返回 None。"""
        try:
            from . import buttonfx as _bf
            if not _bf._PIL_OK:
                return None
            from PIL import Image, ImageDraw, ImageFilter
        except Exception:
            return None
        key = ("badge", kind, size)
        cached = getattr(_bf, "_CACHE", {}).get(key)
        if cached is not None:
            return cached
        try:
            ph = _bf.ImageTk.PhotoImage(_render_badge(kind, size))
        except Exception:
            return None
        try:
            _bf._CACHE[key] = ph
        except Exception:
            pass
        return ph

    def add_button(self, text: str, command=None, accent: bool = False,
                   width: int = 120, height: int = 38, parent=None):
        """在弹窗底部排布按钮；返回按钮控件。尺寸随 DPI 放大。"""
        parent = parent or self.body
        s = getattr(self, "_dpi_s", 1.0)
        width = max(72, int(width * s))
        height = max(30, int(height * s))
        bg = DG_GOLD if accent else "#3A4256"
        fg = "#1F2430" if accent else DG_TEXT
        return self._mk_button(parent, text, command, width, height, bg, fg)

    def _mk_button(self, parent, text, command, width, height, bg, fg):
        # 画布底色必须用父容器底色（而非按钮色）：PIL 渲染的四角是透明的，
        # 若底色=按钮色，圆角外会露出按钮色方块，圆角就"破"了。
        try:
            pbg = parent.cget("bg")
        except Exception:
            pbg = self._body_bg
        b = tk.Canvas(parent, width=width, height=height, bg=pbg,
                      highlightthickness=0, bd=0, cursor="hand2")
        b._pressed = False
        b._hover = False
        b._text = text
        b._command = command
        b._mybg = bg
        b._myfg = fg
        b._myw = width
        b._myh = height
        b._sync_job = None

        def _alive():
            try:
                return bool(b.winfo_exists())
            except Exception:
                return False

        def _draw():
            # 弹窗可能已关闭 → 画布 Tcl 路径失效，跳过绘制
            if not _alive():
                return
            # 统一走全局玻璃质感渲染器（PIL 超采样：真抗锯齿边缘 +
            # 半透明玻璃高光 + 悬停光晕 + 按下内陷）
            draw_3d_button(b, b._myw, b._myh,
                           base=b._mybg, fg=b._myfg, text=b._text,
                           font=(FONT_FAMILY, 12, "bold"),
                           hover=b._hover, pressed=b._pressed,
                           enabled=True, radius=min(10, b._myh // 3))

        def _press(_e):
            b._pressed = True; _draw()

        def _sync():
            # 命令可能弹出新弹窗抢 grab，指针移出后收不到 <Leave> → 悬停态
            # 卡住不复位。空闲时按指针真实位置对账复位。
            b._sync_job = None
            if not _alive():
                return
            b._pressed = False
            try:
                b._hover = (b.winfo_containing(b.winfo_pointerx(),
                                               b.winfo_pointery()) is b)
            except Exception:
                b._hover = False
            _draw()

        def _release(_e):
            b._pressed = False; _draw()
            if b._command:
                b._command()
            try:
                if b._sync_job is not None:
                    b.after_cancel(b._sync_job)
            except Exception:
                pass
            try:
                b._sync_job = b.after_idle(_sync)
            except Exception:
                b._sync_job = None

        def _enter(_e):
            if not b._pressed:
                b._hover = True; _draw()

        def _leave(_e):
            b._hover = False; b._pressed = False; _draw()

        def _destroy(_e):
            if getattr(_e, "widget", None) is not b:
                return
            try:
                if b._sync_job is not None:
                    b.after_cancel(b._sync_job)
            except Exception:
                pass
            b._sync_job = None

        b.bind("<Button-1>", _press)
        b.bind("<ButtonRelease-1>", _release)
        b.bind("<Enter>", _enter)
        b.bind("<Leave>", _leave)
        b.bind("<Destroy>", _destroy)
        b._draw = _draw
        _draw()
        self._buttons.append(b)
        return b

    def button_row(self, buttons, pad: int = 8):
        """把 buttons 横向排成一行，放在按钮区（grid row1 固定行）。
        按钮行使用独立 Frame，保证无论正文多长按钮都固定在底部并可见。
        注意：按钮与正文同在 body 窗口内共享高度，因此 _fit_content 计算
        预算时必须把按钮行高度计入，否则正文行会被挤扁（文字被裁）。"""
        if self._content_frame is None:
            # 兼容未调 place_body 的情况：退化到旧版 pack 到 body 底部
            row = tk.Frame(self.body, bg=self._body_bg)
            row.pack(side="bottom", pady=(10, 12))
            for b in buttons:
                b.pack(in_=row, side="left", padx=pad)
            return row
        # 正常路径：放到 content_frame 的 row1（固定高度，不被正文挤压）
        row = tk.Frame(self._content_frame, bg=self._body_bg)
        row.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 8))
        row.grid_columnconfigure(0, weight=1)
        # 用一个内部 Frame 居中放置按钮
        inner = tk.Frame(row, bg=self._body_bg)
        inner.grid(row=0, column=0)
        for b in buttons:
            b.pack(in_=inner, side="left", padx=pad)
        try:
            row.update_idletasks()
        except Exception:
            pass
        return row

    def _redraw_buttons(self):
        """在 open() 后重绘所有按钮，避免在屏外构造时绘制丢失。"""
        for b in self._buttons:
            try:
                if hasattr(b, "_draw"):
                    b._draw()
            except Exception:
                pass
        try:
            self.canvas.update_idletasks()
        except Exception:
            pass

    def _fit_content(self):
        """按正文 + 按钮行的实际请求高度自动加高弹窗（只增不减）。

        按钮与正文同在 body 窗口内共享高度：若预算只算文字，正文行会被
        按钮行挤扁导致文字被裁。这里把两者一并计入，不足则整体加高弹窗
        并同步重画花纹、加大正文窗口——从机制上杜绝任何 DPI 下的裁剪。
        """
        try:
            if self._content_frame is None or self._body_id is None:
                return
            need = 10                      # text_frame 上下 pady 余量
            for ch in self._text_frame.winfo_children():
                need += int(ch.winfo_reqheight())
                info = ch.grid_info() or {}
                py = info.get("pady", 0)
                if isinstance(py, (int, float)):
                    py = (py, py)
                try:
                    need += sum(int(v) for v in py)
                except Exception:
                    pass
            # 按钮行（content_frame row1）：取最高按钮 + 行 pady
            btn_h = 0
            for b in getattr(self, "_buttons", []):
                try:
                    btn_h = max(btn_h, int(b.winfo_reqheight()))
                except Exception:
                    pass
            need += btn_h + 12             # row1 pady(4,8)
            avail = self._content_h - 8
            if need > avail:
                add = need - avail + 12
                self._dlg_h += add
                self._content_h += add
                self.canvas.configure(height=self._dlg_h)
                self._ornate_border()      # 花纹按新高度重画
                # 注意：_ornate_border 的 delete("all") 会连带删掉 body 的
                # canvas window 项，必须重新挂载（坐标与 place_body 一致），
                # 否则正文 Frame 失去画布承载、整块消失。
                try:
                    self._body_id = self.canvas.create_window(
                        24, self._title_band_h + 4, window=self.body,
                        anchor="nw", width=self._dlg_w - 48,
                        height=self._content_h - 8)
                except Exception:
                    pass
        except Exception:
            pass

    def open(self):
        self._fit_content()                # 先按内容定稿尺寸，再定位显示
        self._center()
        # 先显示、刷新、强制置顶，确保弹窗真正画出来并盖在主窗口之上，
        # 杜绝"看不见的弹窗"导致用户以为没有弹出。
        try:
            self.deiconify()
        except Exception:
            pass
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        try:
            self.update_idletasks()
        except Exception:
            pass
        # 屏外兜底（相对主窗口居中失败时）
        try:
            if "-32000" in self.geometry():
                self.geometry(f"{self._dlg_w}x{self._dlg_h}+80+80")
        except Exception:
            pass
        # 弹窗就位后刷新按钮（屏外构造时按钮绘制可能丢失），保证按钮可见可点
        try:
            self._redraw_buttons()
        except Exception:
            pass
        # 窗口已可见、按钮已绘制后，再加模态 grab；并绑定自身关闭协议，
        # 保证用户点弹窗右上角 X 也能释放 grab（否则主窗口 X 会被 grab 抢走、
        # 表现为"关不掉"）。
        try:
            self.protocol("WM_DELETE_WINDOW", self.close)
            self.grab_set()
            self.update_idletasks()
        except Exception:
            pass
        # 保持置顶：模态结束弹窗应始终盖在主窗口之上，避免被盖住"看不见"。

    def close(self):
        self._safe_release_grab()
        try:
            self.destroy()
        except Exception:
            pass

    def _safe_release_grab(self):
        """幂等释放本窗口的模态 grab（防止泄漏冻结主窗口）。"""
        try:
            self.grab_release()
        except Exception:
            pass


def confirm_dialog(master, title: str, message: str, ok_text: str = "确定",
                   cancel_text: str | None = "取消",
                   ok_cb=None, cancel_cb=None,
                   accent_ok: bool = True, width: int = 420, height: int = 260,
                   subtitle: str = ""):
    """通用确认弹窗：返回是否点了 OK（阻塞式由调用方决定）。
    非阻塞：OK/取消分别回调 ok_cb / cancel_cb。"""
    dlg = OrnateDialog(master, title=title, width=width, height=height,
                       subtitle=subtitle)
    # 使用默认 place_body：正文区位于标题带下方、按钮带上方，完全避开花纹
    dlg.place_body()
    dlg.add_text(message, size=13, wraplength=width - 120, pady=4)

    def _ok():
        dlg.close()
        if ok_cb:
            ok_cb()

    def _cancel():
        dlg.close()
        if cancel_cb:
            cancel_cb()

    if cancel_text:
        btns = [dlg.add_button(cancel_text, _cancel, accent=False),
                dlg.add_button(ok_text, _ok, accent=accent_ok)]
    else:
        btns = [dlg.add_button(ok_text, _ok, accent=accent_ok)]
    dlg.button_row(btns)
    dlg.open()
    return dlg
