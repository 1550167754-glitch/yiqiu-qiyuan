# -*- coding: utf-8 -*-
"""
gui.py —— 六子棋（Connect6）图形界面

本版本在原版基础上的改进：
    1. 清晰渲染（高分屏适配）：Windows 下启用进程级 DPI 感知，
       并按当前显示器实际 DPI 设置 tkinter 缩放，文字/图形不模糊；
    2. 两步落子交互：先点击棋盘"选中目标位置"（虚线框预览），
       再点击右侧栏"确认落子"按钮正式落子，交互明确、状态反馈清晰；
    3. 右侧栏胜率曲线：以"黑方胜率"走势实时折线图呈现，
       横轴=手数、纵轴=0~100%，并标注当前黑/白胜率百分比；
    4. 棋盘窗口缩放：按 min(可用宽,可用高) 等比居中重绘，始终完整显示；
    5. 光影按钮 GlowButton：悬停高亮、按下内陷 + 光晕；
    6. 音乐播放器：切歌前释放 MCI 设备，避免界面错乱。

依赖：仅标准库 + tkinter；PostgreSQL / 大模型等均为可选，自动降级。
"""
from __future__ import annotations

import os
import sys
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .board import Board, BLACK, WHITE, COLOR_NAMES
from .game import Game, Player, MODE_HUMAN_AI, MODE_HUMAN_HUMAN, MODE_AI_AI
from .sounds import SoundManager
from .theme_boards import THEME_NAMES, get_theme, blend
from .fonts import FontManager, FALLBACK_FAMILY
from .music import MusicPlayer, MODE_LOOP, MODE_SINGLE, MODE_SHUFFLE, MODE_NAMES
from .paths import resource, logs_dir, data_dir
from .roundrect import draw_3d_button, rounded_rect_points
from . import stonefx
from . import titlefx

# ---------- 可选模块（未就绪时优雅降级，不影响启动/对弈） ----------
try:
    from .database import Database
except Exception:  # psycopg 缺失 / 无服务
    Database = None

try:
    from .replay import ReplayWindow
except Exception:
    ReplayWindow = None

try:
    from .winrate import winrate_black, winrate_white
except Exception:
    winrate_black = winrate_white = None

# 6 阶段胜率引擎（主实现，见 winrate_engine.py）；失败则回退到 winrate.py 静态评估
try:
    from . import winrate_engine as winrate2
    _HAVE_WR2 = True
except Exception:
    winrate2 = None
    _HAVE_WR2 = False

try:
    from .pgcheck import (check_status, start_service, first_service,
                          generate_install_bat, STATUS_RUNNING, STATUS_STOPPED)
except Exception:
    check_status = start_service = first_service = generate_install_bat = None

# 游戏内带花纹弹窗（自绘 Toplevel）；导入失败则回退到系统 messagebox
try:
    from .styled_dialog import OrnateDialog
except Exception:
    OrnateDialog = None

# ---------- 配色（深色现代风格） ----------
C_MAIN = "#1F2430"
# 产品名（启动页艺术字 / 窗口标题 / 弹窗统一使用）
APP_NAME = "弈趣棋苑"
C_MAIN_DARK = "#171B24"
C_ACCENT = "#E8B34B"
C_ACCENT_DARK = "#C9972F"
C_PANEL_BG = "#262C3A"
C_PANEL_BORDER = "#353D4F"
C_TEXT = "#EDEFF4"
C_TEXT_DIM = "#9AA3B2"
C_GLOW = "#FFD98A"
C_CONFIRM = "#3EBB6B"     # 确认落子（绿）
C_CANCEL = "#3A4256"

BOARD_MARGIN = 34  # 棋盘在画布内的外边距：四周留白(画布到棋盘外框)，观感优雅且给坐标留位

# ---------- 启动页设计尺寸（scale=1.0 时的垂直预算，单位 px） ----------
# 布局按「设计总高」等比缩放并垂直居中：窗口越大越大气，窗口小则整体收缩不溢出。
APP_SUBTITLE = "六子棋 · 五子棋 · 中国象棋 · 经典对弈"
_MENU_K_TITLE = 176.0   # 艺术字标题块视觉高度（主标题 + 副标题）
_MENU_K_DIV = 26.0      # 标题块 → 分隔线
_MENU_K_HEAD = 44.0     # 分区头 → 其下按钮的距离（含分区头本身的占位）
_MENU_K_B1 = 70.0       # 游戏入口按钮高
_MENU_K_CAP = 26.0      # 按钮下方说明文字带
_MENU_K_B2 = 50.0       # 功能按钮高
_MENU_DESIGN_H = (_MENU_K_TITLE + _MENU_K_DIV + _MENU_K_HEAD + _MENU_K_B1
                  + _MENU_K_CAP + _MENU_K_HEAD + _MENU_K_B2)
_MENU_K_STEP = 0.02     # 缩放量化步长（避免拖拽缩放时反复触发重渲染）

# ---------- 背景色方案（菜单页 + 游戏页容器） ----------
# 设计原则：与现有面板/棋子/金色按钮颜色和谐不冲突，整体低饱和。
# 每套 = 主色 + 主色加深(渐变底色)
BG_PRESETS = [
    ("默认深蓝灰", "#1F2430", "#171B24"),
    ("墨绿",       "#1E2A26", "#161E1B"),
    ("深紫",       "#231E2D", "#181420"),
    ("暗棕红",     "#2A1F1D", "#1C1413"),
    ("深青蓝",     "#1B2530", "#121A22"),
]
BG_PRESET_MAP = {nm: (ca, cb) for nm, ca, cb in BG_PRESETS}
DIFFICULTY_CN = {"easy": "简单", "medium": "中等", "hard": "困难"}
DIFFICULTY_ORDER = [("简单", "easy"), ("中等", "medium"), ("困难", "hard")]


def _enable_dpi_awareness():
    """Windows 下启用进程级 DPI 感知，避免高分屏被系统放大而模糊。

    关键：必须在创建任何 Tk 窗口之前调用（run() 里先于 Connect6GUI()）。
    优先用上下文级 API（可在进程已声明 DPI 模式后再调用且最可靠），
    失败再逐级降级到 shcore / user32。
    """
    if os.name != "nt" or sys.platform != "win32":
        return
    try:
        import ctypes
        # 1) 上下文级 per-monitor v2（DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4）
        #    最可靠：即便 Tk 已设过 DPI 模式也能生效，且按显示器分别适配。
        try:
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(-4):
                return
        except Exception:
            pass
        # 2) 进程级 per-monitor v2
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        # 3) 进程级 per-monitor v1
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return
        except Exception:
            pass
        # 4) 系统级 DPI 感知（兜底，至少不被系统拉伸糊化）
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


class GlowButton(tk.Canvas):
    """自绘光影按钮：立体投影 + 渐变棋体 + 顶部高光；
    悬停时整体提亮并浮现光晕环，按下时下沉 2px 并出现内阴影，交互反馈强烈。

    用法：gb = GlowButton(parent, text="开始", command=cb, width=180, height=46)
    支持 set_enabled(False) 置灰禁用。
    """

    def __init__(self, master, text: str, command=None,
                 width: int = 180, height: int = 46,
                 bg: str = C_ACCENT, fg: str = "#1F2430",
                 font=None, radius: int = 12):
        super().__init__(master, width=width, height=height,
                         bg=master["bg"] if master.cget("bg") else C_MAIN,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self._bg = bg
        self._fg = fg
        self._font = font or (FALLBACK_FAMILY, 13, "bold")
        self._radius = radius
        self._pressed = False
        self._hover = False
        self._glow = 0.0
        self._enabled = True
        self._sync_job = None          # 释放后对账复位的延迟任务 id
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        # 控件销毁（如所属弹窗关闭）时取消挂起的对账任务，避免其在控件
        # 失效后执行 → TclError（invalid command name）。
        self.bind("<Destroy>", self._on_destroy)
        self._draw()

    def _shade(self, color: str, factor: float) -> str:
        """把颜色按 factor(0..1) 压暗/提亮，factor<1 压暗，>1 提亮。"""
        c = color.lstrip("#")
        r = int(c[0:2], 16); g = int(c[2:4], 16); b = int(c[4:6], 16)
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return f"#{r:02X}{g:02X}{b:02X}"

    def _set_hover(self, v: bool):
        self._hover = v
        if not v:
            # 指针离开必然意味着"不再按下"（否则会卡在按下态的外发光上）
            self._pressed = False
        self._draw()

    def set_enabled(self, on: bool):
        if self._enabled == bool(on):
            self._draw()
            return
        self._enabled = bool(on)
        self.config(cursor="hand2" if self._enabled else "arrow")
        self._draw()

    def _on_press(self, _e):
        if not self._enabled:
            return
        self._pressed = True
        self._draw()

    def _on_release(self, _e):
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self._enabled and self.command:
            self.command()
            # 关键：command 常常会弹出模态弹窗并 grab_set() 抢走输入，
            # 此后指针移出按钮也收不到 <Leave>，pressed/hover 会永远停在
            # 按下态（按钮"卡住不复位"）。这里在事件循环空闲时按指针真实
            # 位置对账复位，保证按下→释放动画完整结束。
            self._schedule_sync()

    def _alive(self):
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _schedule_sync(self):
        """安排一次空闲对账（可重复调用，旧的自动取消）。"""
        try:
            if self._sync_job is not None:
                self.after_cancel(self._sync_job)
        except Exception:
            pass
        try:
            self._sync_job = self.after_idle(self._sync_pointer_state)
        except Exception:
            self._sync_job = None

    def _on_destroy(self, e=None):
        """控件销毁：取消挂起的对账任务（避免在失效控件上绘制）。"""
        if e is not None and getattr(e, "widget", None) is not self:
            return
        try:
            if self._sync_job is not None:
                self.after_cancel(self._sync_job)
        except Exception:
            pass
        self._sync_job = None

    def _sync_pointer_state(self):
        """与指针真实位置对账，复位 pressed/hover（弹窗抢 grab 后必需）。"""
        self._sync_job = None
        if not self._alive():
            return
        self._pressed = False
        try:
            self._hover = (self.winfo_containing(self.winfo_pointerx(),
                                                self.winfo_pointery()) is self)
        except Exception:
            self._hover = False
        self._draw()

    def set_text(self, text: str):
        self.text = text
        self._draw()

    def _draw(self):
        # 控件可能已被销毁（所属弹窗关闭）→ 直接跳过，避免 cget TclError
        if not self._alive():
            return
        try:
            w = int(self["width"]); h = int(self["height"])
        except Exception:
            return
        if not self._enabled:
            base = self._shade(C_MAIN_DARK, 1.05)
            fg = self._shade(self._fg, 0.45)
            draw_3d_button(self, w, h, base=base, fg=fg, text=self.text,
                           font=self._font, enabled=False, radius=self._radius)
            return
        draw_3d_button(self, w, h, base=self._bg, fg=self._fg, text=self.text,
                       font=self._font, hover=self._hover, pressed=self._pressed,
                       enabled=True, radius=self._radius)


# ---------------------------------------------------------------
#  媒体控制按钮（圆角 + 渐变 + 悬停高亮 + 按下内陷，更精致）
# ---------------------------------------------------------------
class MediaButton(tk.Canvas):
    """音乐播放器的紧凑控制按钮（上一首/播放/下一首/模式）。
    视觉细节：
        - 圆角矩形（与 GlowButton 风格一致但更精致）
        - 上下渐变填充，模拟金属/玻璃质感
        - 悬停时顶部高光变亮 + 边框变金
        - 按下时整体下沉 2px + 渐变反向
        - 图标使用 Unicode 媒体符号，缩放自适
    """

    def __init__(self, master, text: str = "▶", command=None,
                 width: int = 38, height: int = 30,
                 accent: bool = False):
        # 选中父容器的 bg 作为底色，确保与侧栏融合
        try:
            parent_bg = master.cget("bg")
        except Exception:
            parent_bg = "#171B24"
        super().__init__(master, width=width, height=height,
                         bg=parent_bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.text = text
        self.command = command
        # 注意：不能把尺寸存进 self._w / self._h —— tkinter 内部用 self._w
        # 存 widget 的 Tcl 路径名(如 ".!frame.!canvas")，覆写会使 pack/geometry
        # 报 bad window path name。尺寸一律在 _draw() 里读 self["width"/"height"]。
        self._accent = accent
        # 配色：accent 用金色，常规用深灰
        if accent:
            self._c_top = "#F0C265"
            self._c_bot = "#C9972F"
            self._c_border = "#E8B34B"
            self._c_text = "#1F2430"
        else:
            self._c_top = "#4A5266"
            self._c_bot = "#2E3445"
            self._c_border = "#5A6378"
            self._c_text = "#EDEFF4"
        self._hover = False
        self._pressed = False
        self._sync_job = None
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", self._on_leave)
        self.bind("<Destroy>", self._on_destroy)
        self._draw()

    @staticmethod
    def _shade(color, factor):
        c = color.lstrip("#")
        r = int(c[0:2], 16) * factor
        g = int(c[2:4], 16) * factor
        b = int(c[4:6], 16) * factor
        return f"#{max(0,min(255,int(r))):02X}{max(0,min(255,int(g))):02X}{max(0,min(255,int(b))):02X}"

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _on_press(self, _e):
        self._pressed = True
        self._draw()

    def _on_release(self, _e):
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self.command:
            self.command()
            # command 可能弹出模态窗抢 grab，指针移出后收不到 <Leave>，
            # 需在空闲时对账复位，避免按钮卡在悬停/按下态。
            self._schedule_sync()

    def _alive(self):
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _schedule_sync(self):
        try:
            if self._sync_job is not None:
                self.after_cancel(self._sync_job)
        except Exception:
            pass
        try:
            self._sync_job = self.after_idle(self._sync_pointer_state)
        except Exception:
            self._sync_job = None

    def _on_destroy(self, e=None):
        if e is not None and getattr(e, "widget", None) is not self:
            return
        try:
            if self._sync_job is not None:
                self.after_cancel(self._sync_job)
        except Exception:
            pass
        self._sync_job = None

    def _on_leave(self, _e):
        self._hover = False
        self._pressed = False
        self._draw()

    def _sync_pointer_state(self):
        """与指针真实位置对账，复位 pressed/hover。"""
        self._sync_job = None
        if not self._alive():
            return
        self._pressed = False
        try:
            self._hover = (self.winfo_containing(self.winfo_pointerx(),
                                                self.winfo_pointery()) is self)
        except Exception:
            self._hover = False
        self._draw()

    def _draw(self):
        if not self._alive():
            return
        try:
            w = int(self["width"]); h = int(self["height"])
        except Exception:
            w = 38; h = 30
        base = self._c_bot
        fg = self._c_text
        fs = 14 if (self._accent or w >= 40) else 13
        draw_3d_button(self, w, h, base=base, fg=fg, text=self.text,
                       font=(FALLBACK_FAMILY, fs, "bold"),
                       hover=self._hover, pressed=self._pressed,
                       enabled=True, radius=min(9, h // 3))

    def set_text(self, text: str):
        """切换按钮文字（如 ▶ ↔ ⏸）并重绘。"""
        self.text = text
        self._draw()


# ---------------------------------------------------------------
#  音量滑杆（自绘，更精致）
# ---------------------------------------------------------------
class VolumeSlider(tk.Canvas):
    """自绘音量滑杆：轨道 + 填充段（金色进度）+ 圆形滑块。
    比 ttk.Scale 更精致，可与 MusicButton 风格统一。"""

    def __init__(self, master, from_: int = 0, to: int = 100,
                 value: int = 50, length: int = 120, height: int = 22,
                 command=None):
        try:
            parent_bg = master.cget("bg")
        except Exception:
            parent_bg = "#171B24"
        super().__init__(master, width=length, height=height,
                         bg=parent_bg, highlightthickness=0, bd=0)
        self._parent_bg = parent_bg
        self._from = from_; self._to = to
        self._value = max(from_, min(to, value))
        self._length = length; self._height = height
        self._command = command
        self._dragging = False
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    @staticmethod
    def _shade(color, factor):
        """把颜色按 factor(0..1) 压暗/提亮，factor<1 压暗，>1 提亮。"""
        c = (color or "#171B24").lstrip("#")
        if len(c) != 6:
            return "#171B24"
        r = max(0, min(255, int(int(c[0:2], 16) * factor)))
        g = max(0, min(255, int(int(c[2:4], 16) * factor)))
        b = max(0, min(255, int(int(c[4:6], 16) * factor)))
        return f"#{r:02X}{g:02X}{b:02X}"

    def recolor(self, bg: str):
        """背景主色变更时同步底色，并把轨道压暗/提亮到与底色和谐。"""
        self._parent_bg = bg
        try:
            self.configure(bg=bg)
        except Exception:
            pass
        self._draw()

    def _value_to_x(self):
        span = self._to - self._from
        if span <= 0: return 6
        ratio = (self._value - self._from) / span
        return int(6 + ratio * (self._length - 12))

    def _x_to_value(self, x):
        span = self._to - self._from
        usable = self._length - 12
        if usable <= 0: return self._from
        ratio = max(0.0, min(1.0, (x - 6) / usable))
        return int(self._from + ratio * span)

    def _on_click(self, e):
        self._dragging = True
        self._value = self._x_to_value(e.x)
        self._draw()
        if self._command:
            self._command(self._value)

    def _on_drag(self, e):
        if not self._dragging: return
        self._value = self._x_to_value(e.x)
        self._draw()
        if self._command:
            self._command(self._value)

    def _on_release(self, e):
        self._dragging = False

    def get(self):
        return self._value

    def set(self, v):
        self._value = max(self._from, min(self._to, int(v)))
        self._draw()

    def _draw(self):
        c = self; w = self._length; h = self._height
        c.delete("all")
        cy = h // 2
        # 轨道色从父容器底色派生（压暗得到轨道、提亮得到边框），保证与背景和谐
        track = self._shade(self._parent_bg, 0.9)
        track_bd = self._shade(self._parent_bg, 1.7)
        # 轨道（深色）
        c.create_rectangle(6, cy - 2, w - 6, cy + 2,
                           fill=track, outline=track_bd, width=1)
        # 填充段（金色进度）
        x = self._value_to_x()
        c.create_rectangle(6, cy - 2, x, cy + 2,
                           fill="#C9972F", outline="")
        # 滑块（圆 + 高光）
        c.create_oval(x - 6, cy - 6, x + 6, cy + 6,
                      fill="#E8B34B", outline="#1F2430", width=1)
        c.create_oval(x - 3, cy - 4, x + 1, cy - 2,
                      fill="#F5D27A", outline="")


# ---------------------------------------------------------------
#  细长自绘滚动条（侧栏滚动，明显可见、可拖动）
# ---------------------------------------------------------------
class ThinScrollbar(tk.Canvas):
    """深色主题下的细长金色滚动条。

    为什么不用 ttk.Scrollbar：默认 ttk 主题在高分屏 / 深色背景上会渲染成
    一条几乎看不见的浅灰槽，用户会以为「没有滚动条、内容显示不全」。这里
    自绘：暗色细轨 + 金色圆角滑块，悬停/拖动提亮，明确指示「可以滚动」。
    支持拖动滑块、点击轨道跳转；通过 set() 对接 Canvas.yview。
    """

    def __init__(self, master, command=None, width: int = 12,
                 bg: str = "#171B24"):
        super().__init__(master, width=width, height=90, bg=bg,
                         highlightthickness=0, bd=0)
        self._cmd = command
        self._bg = bg
        self._first, self._last = 0.0, 1.0
        self._drag = False
        self._drag_dy = 0.0
        self._hover = False
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Configure>", lambda e: self._draw())

    # ---- 对外接口 ----
    def set(self, first, last):
        """对接 Canvas 的 yscrollcommand（回调 first/last 归一化位置）。"""
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(0.0, min(1.0, float(last)))
        except Exception:
            return
        self._draw()

    def recolor(self, bg: str):
        """背景主色变更时同步底色并重绘。"""
        self._bg = bg
        try:
            self.configure(bg=bg)
        except Exception:
            pass
        self._draw()

    # ---- 内部 ----
    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _metrics(self):
        h = max(1, self.winfo_height())
        w = max(1, self.winfo_width())
        pad = 2.0
        span = max(1.0, h - 2 * pad)
        th = (self._last - self._first) * span
        th = max(26.0, min(span, th))
        y0 = pad + self._first * span
        y1 = min(h - pad, y0 + th)
        return w, h, pad, y0, y1

    def _draw(self):
        try:
            self.delete("all")
        except Exception:
            return
        w, h, pad, y0, y1 = self._metrics()
        if self._last - self._first >= 0.999:
            return                            # 内容未超出：整条隐去
        # 轨道（暗色细条）
        self.create_rectangle(w / 2 - 2, pad, w / 2 + 2, h - pad,
                              fill=blend(self._bg, "#FFFFFF", 0.13),
                              outline="")
        # 滑块（金色圆角，悬停/拖动提亮）
        col = C_ACCENT if (self._hover or self._drag) else C_ACCENT_DARK
        r = min(4.0, (w - 4) / 2.0, (y1 - y0) / 2.0)
        pts = rounded_rect_points(2, y0, w - 2, y1, r)
        self.create_polygon(pts, fill=col, outline="")
        # 滑块中缝高光（金属质感）
        if y1 - y0 > 18:
            self.create_line(w / 2, y0 + 6, w / 2, y1 - 6,
                             fill=blend(col, "#FFFFFF", 0.45), width=1)

    def _scroll_to(self, frac):
        if not self._cmd:
            return
        try:
            self._cmd("moveto", max(0.0, min(1.0, float(frac))))
        except Exception:
            pass

    def _on_press(self, e):
        w, h, pad, y0, y1 = self._metrics()
        if y0 - 1 <= e.y <= y1 + 1:
            self._drag = True
            self._drag_dy = e.y - y0
        else:
            span = max(1.0, h - 2 * pad)
            self._scroll_to((e.y - pad) / span)
        self._draw()

    def _on_drag(self, e):
        if not self._drag:
            return
        w, h, pad, y0, y1 = self._metrics()
        span = max(1.0, h - 2 * pad)
        self._scroll_to((e.y - self._drag_dy - pad) / span)
        self._draw()

    def _on_release(self, _e):
        self._drag = False
        self._draw()


# ---------------------------------------------------------------
#  主窗口
# ---------------------------------------------------------------
def _lower_thread_priority():
    """把当前线程降为低优先级（Windows）。

    AI 搜索/胜率蒙特卡洛是纯 CPU 计算，若与音频设备线程、UI 线程同优先级
    竞争，会间接拖慢 MCI 命令（音频设备内部锁的持有线程被饿死，实测
    音乐按钮在 AI 思考时卡 1~2 秒）。降优先级后 UI/音频优先获得 CPU。
    """
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetThreadPriority(k32.GetCurrentThread(), -2)  # THREAD_PRIORITY_LOWEST
    except Exception:
        pass


class Connect6GUI(tk.Tk):
    def __init__(self, root=None):
        _enable_dpi_awareness()
        # GIL 切换间隔调小：AI 搜索/胜率 MC 等纯计算后台线程持有 GIL 的
        # 单次时长从 5ms 降到 1ms，对局中界面（含音乐按钮）显著更顺滑
        try:
            sys.setswitchinterval(0.001)
        except Exception:
            pass
        tk.Tk.__init__(self)
        self.title(APP_NAME)
        try:
            self.iconbitmap(resource("assets", "icon.ico"))
        except Exception:
            pass
        # 自适应窗口：完整限制在屏幕内，避免窗口高于屏幕导致底部被裁（画面显示不完全）。
        # 关键：屏幕尺寸与 geometry 同坐标系（均来自 winfo），且最小尺寸随屏幕收敛，
        # 绝不允许窗口被强行拉到超过可用高度。
        d_w, d_h = self._desktop_size()
        avail_w, avail_h = max(320, d_w - 8), max(240, d_h - 56)
        win_w = min(1240, avail_w)
        win_h = min(820, avail_h)
        # 理想最小尺寸（640×520），但不得超过可用屏幕，否则小屏/高 DPI 下会被裁
        min_w = min(640, d_w)
        min_h = min(520, avail_h)
        win_w = max(win_w, min_w)
        win_h = max(win_h, min_h)
        # 最终兜底：绝不超过可用区域
        win_w = min(win_w, avail_w)
        win_h = min(win_h, avail_h)
        win_w = max(win_w, 360); win_h = max(win_h, 380)
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(min_w, min_h)
        self._win_w, self._win_h = win_w, win_h

        # 高 DPI：按当前显示器真实 DPI 设置 tk 缩放（保证清晰）
        try:
            self._dpi = self._system_scale()
            self.tk.call("tk", "scaling", self._dpi)
        except Exception:
            self._dpi = 1.0

        # 字体 & 音效 & 音乐
        self.fm = FontManager()
        self.fm.set_current(self.fm.labels()[0] if self.fm.labels() else FALLBACK_FAMILY)
        self.sound = SoundManager()
        self.music = MusicPlayer()

        # 对局状态
        self.game: Game | None = None
        self.theme_name = THEME_NAMES[0]
        self.theme = get_theme(self.theme_name)
        self.human_side = BLACK
        self.difficulty = "medium"
        self.selected: list[tuple[int, int]] = []   # 玩家已选的待落子点（连续选择，最多 2 个）
        self.variant = "connect6"                    # 当前棋种：connect6（六子棋）/ gomoku（五子棋）
        self.thinking = False
        self.timer_on = False       # 默认不限时（休闲对弈）
        self.flash_items = []
        self._timer_job = None
        self._music_job = None
        # 后台线程 → 主线程 的结果队列：AI 回调、胜率 MC 回调都经此中转，
        # 由 _drain_bg_queue 在主线程消费（跨线程调用 tkinter after 不可靠）
        self._bg_queue: "queue.Queue" = queue.Queue()
        self._bg_job = self.after(100, self._drain_bg_queue)
        # PostgreSQL 启动检测（每程序只做一次，不打扰后续对局）
        self._pg_checked = False
        self._pg_prompt_shown = False
        self._pg_queue: "queue.Queue" = queue.Queue()
        self._pg_wait_job = None
        # 轻提示（Toast）：非模态、自动消失的浮层，用于“已就绪”等无需打断的反馈
        self._toast_win = None
        self._toast_jobs: list = []
        # 启动页标题艺术字：入场淡入动画 + 尺寸防抖重排
        self._menu_title_id = None
        self._menu_title_photo = None
        self._menu_title_frames = None
        self._menu_anim_job = None
        self._menu_anim_i = 0
        self._menu_redraw_job = None
        self._menu_last_size = None
        self._menu_intro_pending = False    # 入场动画待播（等画布拿到真实尺寸）

        # 胜率曲线数据：每子一点，self._wr_y=黑方胜率(%)（与棋盘手数一一对应）
        self._wr_y: list[float] = []
        self._wr_board: Board | None = None   # 影子棋盘，用于增量评估
        # 6 阶段引擎异步状态（内存安全：单工作线程 + 复用棋盘，不复制海量快照）
        self._wr_mc_worker_running = False   # 蒙特卡洛后台线程是否在跑
        self._wr_mc_refined: set[int] = set()  # 已被异步(M C/搜索)精化过的曲线下标
        self._search_refresh_every = 5          # 每几步用搜索分值校正一次曲线
        self._wr_gen = 0                        # 对局代数，防止旧后台结果写回新局

        # 容器：两页堆叠
        self.container = tk.Frame(self, bg=C_MAIN)
        self.container.pack(fill="both", expand=True)

        self.menu_page = tk.Frame(self.container, bg=C_MAIN)
        self.game_page = tk.Frame(self.container, bg=C_MAIN)

        self._build_menu_page()
        self._build_game_page()
        self._show_menu()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Return>", self._on_enter_confirm)
        self.bind_all("<Escape>", self._on_escape_clear)
        # 窗口尺寸变化 → 动态重绘棋盘/启动页，保证棋盘始终填满、完整显示
        self._last_geom = ""
        self.bind("<Configure>", self._on_root_resize)
        self._poll_music()
        self._timer_tick()
        # 启动后先检测 PostgreSQL（后台），并根据状态用游戏内弹窗询问
        self.after(600, self._maybe_pg_prompt)

    def _on_root_resize(self, _ev=None):
        """窗口 resize 兜底：确保画布尺寸变化后重绘，棋盘随窗口动态缩放。

        画布自身已绑定 <Configure>，此处作为兜底保证窗口整体变化(如拖动、最大化、
        屏幕切换)后棋盘一定跟随更新。用 after_idle 让重绘发生在布局完全落定之后，
        避免用"中途几何"绘制导致棋盘缩放错位/抖动。
        """
        try:
            geom = self.geometry()
            if geom == self._last_geom:
                return                       # 尺寸/位置未变，跳过
            self._last_geom = geom
            # after_idle：等 pack 布局完成后，以最终画布尺寸重绘（保证缩放正确）
            if self.game_page.winfo_ismapped():
                self.after_idle(self._redraw)
            elif self.menu_page.winfo_ismapped():
                # 启动页重绘含艺术字重渲染（PIL），拖拽缩放时做小幅防抖，
                # 拖完再整体重排一次即可（观感平滑且不浪费 CPU）。
                self._schedule_menu_redraw()
        except Exception:
            pass

    # ---- DPI ----
    def _system_scale(self) -> float:
        """返回系统 DPI 缩放系数（如 150% -> 1.5）。"""
        try:
            if sys.platform == "win32":
                import ctypes
                dpi = ctypes.windll.user32.GetDpiForSystem()
                return max(1.0, dpi / 96.0)
        except Exception:
            pass
        return 1.0

    def _desktop_size(self):
        """返回当前窗口所在显示器的屏幕尺寸 (w, h)。

        使用 Tk 的 winfo_screen*，其单位与 wm geometry 完全一致（均受 tk scaling
        影响），避免 GetSystemMetrics 物理像素与 geometry 逻辑像素混用导致的
        “窗口比屏幕高、底部被裁” 问题。调用方据此 clamp 窗口尺寸即可保证完整可见。
        """
        try:
            return max(320, int(self.winfo_screenwidth())), max(240, int(self.winfo_screenheight()))
        except Exception:
            return 1240, 820

    # ---- 页面切换 ----
    def _show_menu(self):
        self.game_page.pack_forget()
        self.menu_page.pack(fill="both", expand=True)
        self.menu_page.update_idletasks()
        # 进入启动页：播放一次艺术字标题的入场淡入（渐变过渡，自然融入背景）
        self._menu_intro_pending = True
        self._redraw_menu(animate=True)

    def _ensure_on_screen(self):
        """兜底：若窗口尺寸超出屏幕工作区，自动收缩回屏内，确保棋盘完整可见。

        收缩后的最小尺寸同样随屏幕收敛（不再硬性 640×520），避免小屏/高 DPI 下
        窗口被强行拉到超过可用高度而底部被裁。
        """
        try:
            sw, sh = self._desktop_size()
            cur_w = self.winfo_width()
            cur_h = self.winfo_height()
            new_w = min(cur_w, sw - 8)
            new_h = min(cur_h, sh - 56)
            min_w = min(640, sw)
            min_h = min(520, sh - 56)
            new_w = max(new_w, min_w)
            new_h = max(new_h, min_h)
            new_w = min(new_w, sw - 8)
            new_h = min(new_h, sh - 56)
            new_w = max(new_w, 360); new_h = max(new_h, 380)
            if new_w != cur_w or new_h != cur_h:
                # 把窗口移回屏幕内（默认位置可能被 WM 放到屏外/贴边）
                x = self.winfo_x(); y = self.winfo_y()
                if x + new_w > sw:
                    x = max(0, sw - new_w)
                if y + new_h > sh:
                    y = max(0, sh - new_h)
                self.geometry(f"{new_w}x{new_h}+{x}+{y}")
                self.update_idletasks()
        except Exception:
            pass

    def _show_game(self):
        self._menu_anim_stop()
        self.menu_page.pack_forget()
        self.game_page.pack(fill="both", expand=True)
        self.game_page.update_idletasks()
        self._ensure_on_screen()
        # after_idle：等布局完全落定后以最终画布尺寸重绘，避免首帧棋盘缩放错位
        self.after_idle(self._redraw)

    # =========================================================
    #  启动页（背景静态、单一标题、无多余图片）
    # =========================================================
    def _build_menu_page(self):
        self.menu_canvas = tk.Canvas(self.menu_page, bg=C_MAIN,
                                     highlightthickness=0, bd=0)
        self.menu_canvas.pack(fill="both", expand=True)
        # 画布尺寸变化 → 防抖重排（避免拖拽缩放时反复重渲染艺术字）
        self.menu_canvas.bind("<Configure>", lambda e: self._schedule_menu_redraw())

        # 按钮用 place 定位（由 _redraw_menu 维护），仅一次创建；实际尺寸/字号
        # 每次重排时由 _sync_button 按缩放同步（GlowButton 以“创建尺寸”绘制，
        # 尺寸与 place 不一致会错位/被裁，必须同步 configure）。
        # 两个游戏入口完全同款：同色（亮金）、同尺寸、同字号——只靠位置与
        # 下方说明文字区分棋种，不再使用异色。
        self.btn_start = GlowButton(
            self.menu_canvas, "六子棋", command=self._on_new_game_click,
            width=214, height=70, bg=C_ACCENT, fg="#1F2430",
            font=(FALLBACK_FAMILY, 17, "bold"))
        self.btn_gomoku = GlowButton(
            self.menu_canvas, "五子棋", command=lambda: self._on_new_game_click(variant="gomoku"),
            width=214, height=70, bg=C_ACCENT, fg="#1F2430",
            font=(FALLBACK_FAMILY, 17, "bold"))
        self.btn_xiangqi = GlowButton(
            self.menu_canvas, "中国象棋", command=self._on_xiangqi_click,
            width=214, height=70, bg=C_ACCENT, fg="#1F2430",
            font=(FALLBACK_FAMILY, 17, "bold"))
        self.btn_stats = GlowButton(
            self.menu_canvas, "战绩查询", command=self._show_stats,
            width=180, height=50, bg="#3A4256", fg=C_TEXT,
            font=(FALLBACK_FAMILY, 14, "bold"))
        self.btn_tutor = GlowButton(
            self.menu_canvas, "规则说明", command=self._open_tutorial,
            width=180, height=50, bg="#3A4256", fg=C_TEXT,
            font=(FALLBACK_FAMILY, 14, "bold"))
        self.btn_about = GlowButton(
            self.menu_canvas, "关于", command=self._open_about,
            width=180, height=50, bg="#3A4256", fg=C_TEXT,
            font=(FALLBACK_FAMILY, 14, "bold"))

        # 音乐栏（复用精简版：上一首/播放/下一首/模式/音量/曲名）
        self._build_menu_music_bar()

    def _build_menu_music_bar(self):
        """启动页底部音乐栏：精致媒体按钮 + 自绘音量滑杆 + 曲名 + 模式。
        视觉细节：圆角渐变按钮、悬停高亮、按下内陷、轨道/滑块分层。"""
        self.music_frame = tk.Frame(self.menu_canvas, bg=C_MAIN_DARK, bd=0,
                                    highlightthickness=0)
        # 曲名（左）
        self.music_label = tk.Label(
            self.music_frame, text="未播放", bg=C_MAIN_DARK, fg=C_TEXT_DIM,
            font=(FALLBACK_FAMILY, 11), anchor="w")
        self.music_label.pack(side="left", padx=(12, 6))
        # 模式按钮（右）
        self.music_mode_btn = MediaButton(
            self.music_frame, MODE_NAMES[self.music.mode],
            command=self._music_mode,
            width=78, height=28, accent=False)
        self.music_mode_btn.pack(side="right", padx=(4, 8))
        # 下一首
        self.music_next_btn = MediaButton(
            self.music_frame, "⏭", command=self._music_next,
            width=36, height=28, accent=False)
        self.music_next_btn.pack(side="right", padx=2)
        # 播放/暂停（高亮）
        self.music_toggle_btn = MediaButton(
            self.music_frame, "▶", command=self._music_toggle,
            width=42, height=28, accent=True)
        self.music_toggle_btn.pack(side="right", padx=2)
        # 上一首
        self.music_prev_btn = MediaButton(
            self.music_frame, "⏮", command=self._music_prev,
            width=36, height=28, accent=False)
        self.music_prev_btn.pack(side="right", padx=2)
        # 歌单（启动页入口：开局前即可挑选背景音乐）
        # 注意：按钮文字不再带「♪」音符——该符号在艺术字体里缺字形，渲染成方框。
        self.music_playlist_btn = MediaButton(
            self.music_frame, "歌单", command=self._open_playlist,
            width=72, height=28, accent=False)
        self.music_playlist_btn.pack(side="right", padx=(2, 4))
        # 音量滑杆（自绘，精致）
        self.music_vol = VolumeSlider(
            self.music_frame, value=self.music.volume,
            length=120, height=22,
            command=lambda v: self.music.set_volume(int(v)))
        self.music_vol.pack(side="right", padx=(4, 6))

    def _build_game_music_bar(self):
        """下棋界面侧栏内置音乐播放器：紧凑圆角面板 + 媒体控制 + 音量滑杆。
        使用升级后的 MediaButton（悬停发光）/ VolumeSlider（金色滑块），风格统一精致。"""
        f = tk.Frame(self.side_inner, bg=C_MAIN_DARK, bd=0, highlightthickness=0)
        f.pack(fill="x", padx=10, pady=(2, 8))
        self.game_music_frame = f

        # 标题行：背景音乐 + 模式按钮（右侧）
        # （不再使用「♪」音符图标：艺术字体缺该字形会渲染成方框）
        hdr = tk.Frame(f, bg=C_MAIN_DARK)
        hdr.pack(fill="x", pady=(0, 1))
        tk.Label(hdr, text="背景音乐", bg=C_MAIN_DARK, fg=C_ACCENT,
                 font=(FALLBACK_FAMILY, 10, "bold")).pack(side="left", padx=(2, 0))
        self.gm_mode_btn = MediaButton(
            hdr, MODE_NAMES[self.music.mode], command=self._music_mode,
            width=74, height=24, accent=False)
        self.gm_mode_btn.pack(side="right", padx=(4, 0))
        # 歌单（与启动页一致的入口，对局中也能随时挑选背景音乐）
        self.gm_playlist_btn = MediaButton(
            hdr, "歌单", command=self._open_playlist,
            width=72, height=24, accent=False)
        self.gm_playlist_btn.pack(side="right", padx=(4, 0))

        # 曲名（单行，省略过长）
        self.gm_label = tk.Label(f, text="未播放", bg=C_MAIN_DARK,
                                 fg=C_TEXT_DIM, font=(FALLBACK_FAMILY, 10),
                                 anchor="w")
        self.gm_label.pack(fill="x", padx=(2, 0), pady=(1, 4))

        # 控制行：上一首 / 播放(更大、金色) / 下一首 + 音量滑杆
        row2 = tk.Frame(f, bg=C_MAIN_DARK)
        row2.pack(fill="x")
        self.gm_prev_btn = MediaButton(
            row2, "⏮", command=self._music_prev,
            width=34, height=30, accent=False)
        self.gm_prev_btn.pack(side="left", padx=(2, 2))
        self.gm_play_btn = MediaButton(
            row2, "▶", command=self._music_toggle,
            width=46, height=32, accent=True)
        self.gm_play_btn.pack(side="left", padx=2)
        self.gm_next_btn = MediaButton(
            row2, "⏭", command=self._music_next,
            width=34, height=30, accent=False)
        self.gm_next_btn.pack(side="left", padx=2)
        # 自绘音量滑杆
        self.gm_vol = VolumeSlider(
            row2, value=self.music.volume,
            length=132, height=24,
            command=lambda v: self.music.set_volume(int(v)))
        self.gm_vol.pack(side="left", padx=(10, 2), expand=True)

    def _schedule_menu_redraw(self, delay=70):
        """启动页重排防抖：拖拽缩放时只在停稳后重排一次（艺术字重渲染不便宜）。"""
        try:
            if self._menu_redraw_job is not None:
                self.after_cancel(self._menu_redraw_job)
        except Exception:
            pass
        try:
            self._menu_redraw_job = self.after(delay, self._menu_redraw_now)
        except Exception:
            self._menu_redraw_job = None

    def _menu_redraw_now(self):
        self._menu_redraw_job = None
        if not self.menu_page.winfo_ismapped():
            return
        try:
            c = self.menu_canvas
            size = (c.winfo_width(), c.winfo_height())
        except Exception:
            return
        if size == getattr(self, "_menu_last_size", None):
            return          # 尺寸未变：不重排（避免刚进页面就打断入场动画）
        # 若入场动画还没播（窗口首次映射前画布只有 1×1，尺寸不对），
        # 这次重排就带上动画，保证「渐变过渡」一定在正确尺寸下完整播放。
        self._redraw_menu(animate=self._menu_intro_pending)

    def _menu_anim_stop(self):
        """停止标题入场动画（切换页面/窗口关闭时调用，避免悬挂 after）。"""
        j = getattr(self, "_menu_anim_job", None)
        if j is not None:
            try:
                self.after_cancel(j)
            except Exception:
                pass
        self._menu_anim_job = None

    def _menu_anim_step(self):
        """入场动画帧：逐帧提升标题块不透明度 → 平滑的「渐变过渡」融入背景。"""
        self._menu_anim_job = None
        frames = self._menu_title_frames
        i = self._menu_anim_i
        if not frames or i >= len(frames) or self._menu_title_id is None:
            return
        try:
            if self.menu_page.winfo_ismapped():
                self.menu_canvas.itemconfigure(self._menu_title_id,
                                               image=frames[i])
                self._menu_title_photo = frames[i]   # 持引用防 GC
        except Exception:
            return
        self._menu_anim_i = i + 1
        if self._menu_anim_i < len(frames):
            try:
                self._menu_anim_job = self.after(34, self._menu_anim_step)
            except Exception:
                self._menu_anim_job = None

    def _sync_button(self, btn, x, y, w, h, font_size=None):
        """同步 GlowButton 的尺寸/字号后再 place。

        GlowButton 以 `self["width"/"height"]`（创建尺寸）绘制，若 place 的
        尺寸与之不同，按钮图像与控件框就会错位/被裁 —— 因此尺寸必须一起 configure。
        """
        w = max(24, int(round(w)))
        h = max(18, int(round(h)))
        try:
            if int(btn.cget("width")) != w:
                btn.configure(width=w)
            if int(btn.cget("height")) != h:
                btn.configure(height=h)
            if font_size is not None:
                fam = getattr(self.fm, "current_family", FALLBACK_FAMILY)
                want = (fam, max(9, int(round(font_size))), "bold")
                if tuple(btn._font) != want:
                    btn._font = want
        except Exception:
            pass
        btn.place(x=int(round(x)), y=int(round(y)), width=w, height=h)
        btn._draw()

    def _redraw_menu(self, animate=False):
        """启动页：静态渐变背景 + 艺术字标题块 + 自适应大气布局。

        布局按「设计总高」等比缩放（k）并垂直居中，窗口越大越大气；标题与
        副标题合并为一个艺术字标题块（含柔和辉光，四周透明 → 自然融入背景）。
        animate=True 时播放一次入场淡入（渐变过渡）。
        """
        c = self.menu_canvas
        # 入场动画进行中：本次重排（多因窗口尺寸刚稳定）必须继续带动画，
        # 否则动画会被"非动画重排"打断、标题闪一下定住（启动首帧的经典问题）。
        inflight = bool(self._menu_anim_job is not None
                        or (self._menu_title_frames
                            and self._menu_anim_i < len(self._menu_title_frames)))
        self._menu_anim_stop()
        c.delete("all")
        self._menu_title_id = None
        w = max(c.winfo_width(), 1)
        h = max(c.winfo_height(), 1)

        # ---------- 静态渐变背景（深色星空质感） ----------
        steps = 24
        for i in range(steps):
            y0 = int(h * i / steps); y1 = int(h * (i + 1) / steps) + 1
            col = blend(C_MAIN, C_MAIN_DARK, i / (steps - 1))
            c.create_rectangle(0, y0, w, y1, fill=col, outline="")
        # 装饰：淡圆点（模拟星辰，纯色块，无图片）
        import random
        rng = random.Random(7)
        for _ in range(60):
            x = rng.randrange(0, w); y = rng.randrange(0, h)
            rad = rng.choice([1, 1, 1, 2])
            alpha = rng.choice(["#3A4256", "#4A5466", "#46506A"])
            c.create_oval(x - rad, y - rad, x + rad, y + rad, fill=alpha, outline="")

        # ---------- 音乐栏几何（自适应宽度，绝不出画布） ----------
        mb_h = 56
        music_y = max(0, h - mb_h - 30)
        mb_w = min(660, max(320, w - 24))
        self.music_frame.place(x=(w - mb_w) / 2, y=music_y,
                               width=mb_w, height=mb_h)

        # ---------- 内容区（音乐栏之上）与自适应缩放 ----------
        top = max(8, int(h * 0.028))
        avail = max(170.0, music_y - 14 - top)
        k = min(avail / _MENU_DESIGN_H, w / 880.0, 1.34)
        k = max(0.50, round(k / _MENU_K_STEP) * _MENU_K_STEP)
        cur = top + max(0.0, (avail - _MENU_DESIGN_H * k) / 2.0)

        # ---------- 艺术字标题块（主标题鎏金 + 副标题铂金，含柔和辉光） ----------
        fam = getattr(self.fm, "current_family", FALLBACK_FAMILY)
        entries = [(APP_NAME, max(30, int(round(104 * k))), "gold"),
                   (APP_SUBTITLE, max(15, int(round(38 * k))), "platinum")]
        title_cy = cur + _MENU_K_TITLE * k / 2.0
        # 画布尚未拿到真实尺寸（首帧常见 1×1）时不做动画，留待尺寸稳定后播放，
        # 否则动画会在错误尺寸下渲染、随即被重排打断。
        want_anim = ((bool(animate) or inflight) and w > 80 and h > 80
                     and titlefx.available())
        frames = (titlefx.get_title_block_frames(c, entries, family=fam, glow=1.0)
                  if want_anim else [])
        if frames:
            self._menu_intro_pending = False
            self._menu_title_frames = frames
            self._menu_title_id = c.create_image(w / 2, title_cy,
                                                 image=frames[0])
            self._menu_title_photo = frames[0]
            self._menu_anim_i = 0
            self._menu_anim_step()          # 播放入场淡入（渐变过渡）
        else:
            self._menu_title_frames = None
            ph = titlefx.get_title_block_photo(c, entries, family=fam, glow=1.0)
            if ph is not None:
                self._menu_title_photo = ph          # 持引用防 GC
                self._menu_title_id = c.create_image(w / 2, title_cy, image=ph)
            else:
                # 无 PIL 的矢量回退：主标题 + 副标题分层绘制
                self._draw_art_text(c, w / 2, title_cy - 16 * k, APP_NAME,
                                    max(24, int(46 * k)))
                c.create_text(w / 2, title_cy + 30 * k, text=APP_SUBTITLE,
                              fill=C_ACCENT,
                              font=(FALLBACK_FAMILY, max(11, int(15 * k))))
        cur += _MENU_K_TITLE * k

        # ---------- 分隔线（中点缀菱形） ----------
        cur += _MENU_K_DIV * k
        div_y = cur
        lw = int(min(w * 0.30, 420))
        c.create_line(w / 2 - lw, div_y, w / 2 + lw, div_y,
                      fill=C_PANEL_BORDER, width=1)
        self._draw_diamond(c, w / 2, div_y, max(3, int(4 * k)), C_ACCENT_DARK)

        # ---------- 「选择游戏」分区：六子棋 / 五子棋 / 中国象棋 三栏 ----------
        cur += _MENU_K_HEAD * k
        self._ornament_header(c, w / 2, cur - _MENU_K_HEAD * k * 0.50,
                              "选择游戏", scale=k)
        gh = _MENU_K_B1 * k
        ggap = max(12, 20 * k)
        gw = min(196 * k, (w - 80 - 2 * ggap) / 3.0)
        gx = w / 2 - (gw * 3 + ggap * 2) / 2.0
        game_btns = (self.btn_start, self.btn_gomoku, self.btn_xiangqi)
        caps = ("19×19 · 连六", "15×15 · 连五", "9×10 · 中国象棋")
        for i, b in enumerate(game_btns):
            self._sync_button(b, gx + i * (gw + ggap), cur, gw, gh,
                              font_size=16 * k)
        cur += _MENU_K_B1 * k
        # 卡片说明文字（区分棋种，按钮本体保持同款）
        cap_y = cur + _MENU_K_CAP * k * 0.55
        cfont = (FALLBACK_FAMILY, max(9, int(12 * k)))
        for i, cap in enumerate(caps):
            c.create_text(gx + i * (gw + ggap) + gw / 2, cap_y, text=cap,
                          fill=C_TEXT_DIM, font=cfont)
        cur += _MENU_K_CAP * k

        # ---------- 「更多功能」分区：战绩 / 规则 / 关于 并排 ----------
        cur += _MENU_K_HEAD * k
        self._ornament_header(c, w / 2, cur - _MENU_K_HEAD * k * 0.50,
                              "更多功能", scale=k)
        bh2 = _MENU_K_B2 * k
        bgap = max(10, 22 * k)
        bw = min(180 * k, (w - 80 - 2 * bgap) / 3.0)
        bx = w / 2 - (bw * 3 + bgap * 2) / 2.0
        for i, b in enumerate((self.btn_stats, self.btn_tutor, self.btn_about)):
            self._sync_button(b, bx + i * (bw + bgap), cur, bw, bh2,
                              font_size=14 * k)

        # 记录本次渲染的尺寸：尺寸未变时的 Configure 事件不再触发重排
        self._menu_last_size = (w, h)

    # ---- 启动页装饰元素 ----
    def _draw_art_text(self, c, x, y, text, size):
        """艺术字矢量回退（无 PIL）：阴影 + 8 向描边 + 金色主字。"""
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2),
                       (-2, -2), (2, -2), (-2, 2), (2, 2)):
            c.create_text(x + dx, y + dy, text=text, fill="#3A2A0C",
                          font=(self.fm.current_family, size, "bold"))
        c.create_text(x + 3, y + 4, text=text, fill="#000000",
                      font=(self.fm.current_family, size, "bold"))
        c.create_text(x, y, text=text, fill="#F4C451",
                      font=(self.fm.current_family, size, "bold"))

    def _draw_diamond(self, c, x, y, r, color):
        """小菱形装饰点。"""
        c.create_polygon(x, y - r, x + r, y, x, y + r, x - r, y,
                         fill=color, outline="")

    def _ornament_header(self, c, cx, cy, text, scale=1.0):
        """分区标题：文字两侧饰线 + 菱形收尾，替代孤零零的纯文字。

        scale 随启动页整体缩放，分区头随之放大（保持整体比例与大气感）。
        """
        fs = max(10, int(round(13 * scale)))
        f = (FALLBACK_FAMILY, fs, "bold")
        tmp = c.create_text(0, -100, text=text, font=f)   # 仅量宽
        tw = c.bbox(tmp)[2] - c.bbox(tmp)[0]
        c.delete(tmp)
        # 文字用暖金调（比正文暗一档），与鎏金标题呼应
        c.create_text(cx, cy, text=text, fill="#C9AE72", font=f)
        gap = tw / 2 + max(12, 16 * scale)
        seg = max(30, min(160 * scale, int(tw * 1.1)))
        for sgn in (-1, 1):
            x1 = cx + sgn * gap
            x2 = cx + sgn * (gap + seg)
            c.create_line(min(x1, x2), cy, max(x1, x2), cy,
                          fill=C_PANEL_BORDER, width=1)
            self._draw_diamond(c, x2 + sgn * max(4, 5 * scale), cy,
                               max(2, int(3 * scale)), C_ACCENT_DARK)

    # =========================================================
    #  对战页
    # =========================================================
    def _build_game_page(self):
        # 左侧棋盘
        self.board_frame = tk.Frame(self.game_page, bg=C_MAIN)
        self.board_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.board_canvas = tk.Canvas(self.board_frame, bg=C_MAIN,
                                      highlightthickness=0, bd=0)
        self.board_canvas.pack(fill="both", expand=True)
        self.board_canvas.bind("<Configure>", lambda e: self._redraw())
        self.board_canvas.bind("<Button-1>", self._on_click)

        # 右侧侧栏
        self._build_sidebar()

    def _build_sidebar(self):
        # 外层固定宽度容器（336）
        self.sidebar = tk.Frame(self.game_page, bg=C_MAIN_DARK, width=336)
        self.sidebar.pack(side="right", fill="y")
        self.sidebar.pack_propagate(False)

        # 滚动容器：窗口过矮时侧栏内容可滚动，确保底部按钮不被裁切
        # yscrollincrement=1：像素级精确滚动（配合滚轮动画，滚动丝滑不跳变）
        self.side_canvas = tk.Canvas(self.sidebar, bg=C_MAIN_DARK,
                                     highlightthickness=0, bd=0,
                                     yscrollincrement=1)
        self.side_canvas.pack(side="left", fill="both", expand=True)
        # 滚动条以"叠加"方式贴在右侧，不挤压内容宽度（避免按钮被右侧裁切）。
        # 用自绘 ThinScrollbar：深色主题下金色滑块清晰可见，且支持拖动/点轨，
        # 解决「小窗时侧栏内容显示不全、又找不到滚动条」的问题。
        self.side_vsb = ThinScrollbar(self.sidebar,
                                      command=self.side_canvas.yview,
                                      width=12, bg=C_MAIN_DARK)
        self.side_vsb.place(relx=1.0, rely=0.0, relheight=1.0, width=12,
                            anchor="ne")
        self.side_canvas.configure(yscrollcommand=self.side_vsb.set)

        # 内容内层：所有侧栏控件挂在这里，随窗口高度滚动
        self.side_inner = tk.Frame(self.side_canvas, bg=C_MAIN_DARK)
        self._side_win = self.side_canvas.create_window(
            (0, 0), window=self.side_inner, anchor="nw")
        self.side_inner.bind("<Configure>", lambda e: self._side_update_scroll())
        self.side_canvas.bind("<Configure>", lambda e: self._side_update_scroll())
        self.side_canvas.bind("<MouseWheel>", self._side_on_wheel)
        # bind_all 兜底：滚轮悬停在侧栏内的按钮/滑杆/画布等子控件上时也能滚动
        # （GlowButton/MediaButton 是无滚轮绑定的 Canvas，类绑定会吞掉事件）
        self._side_wheel_remain = 0
        self._side_wheel_after = None
        self._side_vsb_shown = True
        self._side_last_sr = None
        self.bind_all("<MouseWheel>", self._side_on_wheel_all)

        inner = self.side_inner

        self.side_title = tk.Label(
            inner, text="对局控制", bg=C_MAIN_DARK, fg=C_TEXT,
            font=(FALLBACK_FAMILY, 15, "bold"))
        self.side_title.pack(pady=(12, 2))

        # 下棋界面内置音乐播放器
        self._build_game_music_bar()

        # 双方信息
        self.lbl_black = tk.Label(
            inner, text="黑方：—", bg=C_MAIN_DARK, fg=C_TEXT,
            font=(FALLBACK_FAMILY, 12), anchor="w")
        self.lbl_black.pack(fill="x", padx=18, pady=2)
        self.lbl_white = tk.Label(
            inner, text="白方：—", bg=C_MAIN_DARK, fg=C_TEXT,
            font=(FALLBACK_FAMILY, 12), anchor="w")
        self.lbl_white.pack(fill="x", padx=18, pady=2)
        self.lbl_status = tk.Label(
            inner, text="准备对局", bg=C_MAIN_DARK, fg=C_ACCENT,
            font=(FALLBACK_FAMILY, 12, "bold"), anchor="w", wraplength=300)
        self.lbl_status.pack(fill="x", padx=18, pady=(4, 1))
        self.lbl_time = tk.Label(
            inner, text="", bg=C_MAIN_DARK, fg=C_TEXT_DIM,
            font=(FALLBACK_FAMILY, 11), anchor="w")
        self.lbl_time.pack(fill="x", padx=18, pady=1)

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)

        # 落子操作（两步：先选位 → 再确认）
        step_bar = tk.Frame(inner, bg=C_MAIN_DARK)
        step_bar.pack(fill="x", padx=14, pady=2)
        self.btn_confirm = GlowButton(
            step_bar, "确认落子", command=self._confirm_stone,
            width=148, height=46, bg=C_CONFIRM, fg="#FFFFFF",
            font=(FALLBACK_FAMILY, 14, "bold"))
        self.btn_confirm.pack(side="left", expand=True)
        self.btn_confirm.set_enabled(False)
        self.btn_clear = GlowButton(
            step_bar, "取消", command=self._clear_selection,
            width=88, height=46, bg=C_CANCEL, fg=C_TEXT,
            font=(FALLBACK_FAMILY, 13, "bold"))
        self.btn_clear.pack(side="left", padx=(8, 0))
        self.btn_clear.set_enabled(False)
        self.lbl_sel = tk.Label(
            inner, text="操作提示：点击棋盘选位（最多 2 个），选满自动落子；按 Esc 取消选择",
            bg=C_MAIN_DARK, fg=C_TEXT_DIM, anchor="w", wraplength=300,
            font=(FALLBACK_FAMILY, 11))
        self.lbl_sel.pack(fill="x", padx=18, pady=(2, 2))

        # 胜率曲线
        self._build_winrate()

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)

        # 设置区
        self._combo_row(inner, "AI难度", DIFFICULTY_ORDER, "medium",
                        self._on_difficulty_change)
        self._combo_row(inner, "棋盘主题",
                        [(n, n) for n in THEME_NAMES], THEME_NAMES[0],
                        self._on_theme_change)
        self._combo_row(inner, "背景色",
                        [(n, n) for n, _, _ in BG_PRESETS], BG_PRESETS[0][0],
                        self._on_bg_change)

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)

        # 操作按钮
        self.btn_pass = GlowButton(inner, "结束本回合（只下 1 子）", command=self._on_pass,
                                   width=296, height=42, bg="#3A4256", fg=C_TEXT,
                                   font=(FALLBACK_FAMILY, 13, "bold"))
        self.btn_pass.pack(pady=4)
        self.btn_undo = GlowButton(inner, "悔棋（撤销整轮）", command=self._on_undo,
                                   width=296, height=42, bg="#3A4256", fg=C_TEXT,
                                   font=(FALLBACK_FAMILY, 13, "bold"))
        self.btn_undo.pack(pady=4)
        self.btn_restart = GlowButton(inner, "重新开始", command=self._confirm_restart,
                                      width=296, height=42, bg="#3A4256", fg=C_TEXT,
                                      font=(FALLBACK_FAMILY, 13, "bold"))
        self.btn_restart.pack(pady=4)
        self.btn_back = GlowButton(inner, "返回主菜单", command=self._back_to_menu,
                                   width=296, height=42, bg="#3A4256", fg=C_TEXT,
                                   font=(FALLBACK_FAMILY, 13, "bold"))
        self.btn_back.pack(pady=4)

    def _side_update_scroll(self):
        """同步滚动区与滚动条显隐，并锁定内层宽度避免按钮被裁。

        稳定性要点（消除侧栏"持续晃动"）：
        - 绝不在 Configure 事件里调 update_idletasks()（重入式重排是抖动根源）；
        - 内层宽度、scrollregion、滚动条显隐均做**变化检测**，值未变不重设，
          状态/计时文本每秒刷新不再引发任何多余的布局动作。
        """
        try:
            cw = self.side_canvas.winfo_width()
            if cw > 1:
                try:
                    cur_w = int(float(self.side_canvas.itemcget(self._side_win,
                                                                "width")))
                except Exception:
                    cur_w = -1
                if cur_w != cw:
                    self.side_canvas.itemconfig(self._side_win, width=cw)
            bbox = self.side_canvas.bbox("all")
            if bbox and bbox != self._side_last_sr:
                self._side_last_sr = bbox
                self.side_canvas.configure(scrollregion=bbox)
            inner_h = self.side_inner.winfo_reqheight()
            canvas_h = self.side_canvas.winfo_height()
            need = inner_h > canvas_h + 2
            if need != self._side_vsb_shown:
                self._side_vsb_shown = need
                if need:
                    self.side_vsb.place(relx=1.0, rely=0.0, relheight=1.0,
                                        width=12, anchor="ne")
                else:
                    self.side_vsb.place_forget()
        except Exception:
            pass

    def _side_on_wheel(self, e):
        """滚轮 → 平滑动画滚动。

        不再按"unit"大步跳变（默认一格≈1/10 窗口高，观感一卡一卡），
        而是把滚动量累加进动画队列，由 _side_wheel_step 按小步长逐帧推进，
        得到连续顺滑的滚动轨迹。快速连滚时目标量自然累加、不丢帧。
        """
        try:
            delta = int(e.delta)
        except Exception:
            delta = 120
        self._side_wheel_remain += -delta
        if self._side_wheel_after is None:
            self._side_wheel_after = self.after(12, self._side_wheel_step)
        return "break"

    def _side_wheel_step(self):
        """滚动动画帧：每 12ms 推进一小段（≤36px），到目标后停止。"""
        self._side_wheel_after = None
        if not self._side_wheel_remain:
            return
        step = max(-36, min(36, self._side_wheel_remain))
        try:
            self.side_canvas.yview_scroll(step, "pixels")
        except Exception:
            self._side_wheel_remain = 0
            return
        self._side_wheel_remain -= step
        if self._side_wheel_remain:
            self._side_wheel_after = self.after(12, self._side_wheel_step)

    def _side_on_wheel_all(self, e):
        """全局滚轮兜底：仅当指针位于侧栏内时接管滚动，其余区域放行默认行为。"""
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        while w is not None:
            if w is self.side_canvas:
                return self._side_on_wheel(e)
            try:
                parent = w.winfo_parent()
            except Exception:
                parent = ""
            w = self.nametowidget(parent) if parent else None

    def _build_winrate(self):
        """右侧栏胜率曲线：黑方胜率(%)随手数走势。"""
        wr_header = tk.Frame(self.side_inner, bg=C_MAIN_DARK)
        wr_header.pack(fill="x", padx=18, pady=(4, 0))
        tk.Label(wr_header, text="胜率曲线", bg=C_MAIN_DARK, fg=C_TEXT,
                 font=(FALLBACK_FAMILY, 12, "bold")).pack(side="left")
        self.lbl_wr_now = tk.Label(wr_header, text="黑 — · 白 —", bg=C_MAIN_DARK,
                                   fg=C_ACCENT, font=(FALLBACK_FAMILY, 11, "bold"))
        self.lbl_wr_now.pack(side="right")

        self.wr_canvas = tk.Canvas(self.side_inner, bg="#202530", highlightthickness=0,
                                   bd=0, width=300, height=130)
        self.wr_canvas.pack(fill="x", padx=14, pady=4)
        self.wr_canvas.bind("<Configure>", lambda e: self._draw_winrate())

        hint = tk.Label(self.side_inner, text="—— 黑方胜率 / 基线 50%",
                        bg=C_MAIN_DARK, fg=C_TEXT_DIM, anchor="w",
                        font=(FALLBACK_FAMILY, 10))
        hint.pack(fill="x", padx=20)

    def _combo_row(self, parent, label, options, default, cb):
        row = tk.Frame(parent, bg=C_MAIN_DARK)
        row.pack(fill="x", padx=18, pady=4)
        tk.Label(row, text=label, bg=C_MAIN_DARK, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(side="left")
        var = tk.StringVar(value=default)
        cbo = ttk.Combobox(row, textvariable=var, values=[o[0] for o in options],
                           state="readonly", font=(FALLBACK_FAMILY, 11), width=10)
        cbo.pack(side="right")
        cbo.bind("<<ComboboxSelected>>",
                 lambda e, v=var: cb(v.get()))
        setattr(self, f"_var_{label}", var)
        setattr(self, f"_combo_{label}", cbo)

    # ---- 中国象棋入口 ----
    def _on_xiangqi_click(self):
        """从启动器菜单打开中国象棋：先弹「新建对局」（模式/难度/引擎说明），
        交互与视觉与五子棋/六子棋的新建对局窗保持一致。"""
        dlg = tk.Toplevel(self)
        dlg.title("新建对局 · 中国象棋")
        dlg.configure(bg=C_MAIN)
        dlg.resizable(False, False)
        try:
            dlg.transient(self)
        except Exception:
            pass
        self._center_window(dlg, 440, 470)

        tk.Label(dlg, text="对局模式", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=20,
                                                   pady=(16, 2))
        # 与象棋窗口侧栏的 3 种模式一一对应
        modes = [("人机对战（AI 执黑）", "pve"), ("双人对弈", "pvp"),
                 ("机机观战 · 皮卡鱼互弈", "aia")]
        mode_var = tk.StringVar(value=modes[0][0])   # 默认值须与某个选项文本一致
        for label, m in modes:
            tk.Radiobutton(dlg, text=label, value=label, variable=mode_var,
                           bg=C_MAIN, fg=C_TEXT, selectcolor=C_MAIN_DARK,
                           activebackground=C_MAIN, activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=34)

        tk.Label(dlg, text="AI 难度（皮卡鱼 NNUE）", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=20,
                                                   pady=(12, 2))
        diff_var = tk.StringVar(value={v: k for k, v in DIFFICULTY_ORDER}
                                .get(getattr(self, "difficulty", "medium"),
                                     "中等"))
        diff_row = tk.Frame(dlg, bg=C_MAIN)
        diff_row.pack(anchor="w", padx=34)
        for label, _key in DIFFICULTY_ORDER:
            tk.Radiobutton(diff_row, text=label, value=label, variable=diff_var,
                           bg=C_MAIN, fg=C_TEXT, selectcolor=C_MAIN_DARK,
                           activebackground=C_MAIN, activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11)).pack(side="left",
                                                            padx=(0, 10))
        tip = ("象棋「困难」为 Pikafish 深度推理档：\n"
               "Skill Level 20 + 搜索深度 14，NNUE 权重评估；\n"
               "机机观战固定使用「中等」档以保证观战节奏。")
        tk.Label(dlg, text=tip, bg=C_MAIN, fg=C_TEXT_DIM, justify="left",
                 font=(FALLBACK_FAMILY, 9)).pack(anchor="w", padx=34,
                                                  pady=(6, 0))

        def _ok():
            mode = {label: m for label, m in modes}[mode_var.get()]
            difficulty = {k: v for k, v in DIFFICULTY_ORDER}.get(
                diff_var.get(), "medium")
            try:
                self.difficulty = difficulty
            except Exception:
                pass
            dlg.destroy()
            self._launch_xiangqi(mode, difficulty)

        GlowButton(dlg, "开始", command=_ok, width=220, height=48,
                   bg=C_ACCENT, fg="#1F2430",
                   font=(FALLBACK_FAMILY, 15, "bold")).pack(pady=(16, 8))
        GlowButton(dlg, "取消", command=dlg.destroy, width=220, height=40,
                   bg=C_CANCEL, fg=C_TEXT,
                   font=(FALLBACK_FAMILY, 13, "bold")).pack(pady=(0, 14))

        # 按内容实测尺寸并夹紧到屏幕内，保证「开始/取消」始终可见
        try:
            dlg.update_idletasks()
            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
            need_w = max(440, int(dlg.winfo_reqwidth()) + 8)
            need_h = max(470, int(dlg.winfo_reqheight()) + 8)
            need_w = max(320, min(need_w, sw - 40))
            need_h = max(320, min(need_h, sh - 80))
            dlg.geometry("")
            self._center_window(dlg, need_w, need_h)
        except Exception:
            pass

    def _launch_xiangqi(self, mode="pve", difficulty="medium"):
        """真正打开象棋窗口（模块异常时明确提示，不致命）。"""
        try:
            from .xiangqi_gui import XiangqiApp
            XiangqiApp(self, mode=mode, difficulty=difficulty)
        except Exception as exc:  # 模块异常不致命，给出提示
            try:
                from .styled_dialog import OrnateDialog
                dlg = OrnateDialog(self, title="无法启动象棋", width=420, height=240)
                dlg.open()
                tk.Label(dlg.body, text=f"象棋模块加载失败：\n{exc}",
                         bg=dlg._body_bg, fg=C_TEXT, justify="left",
                         font=(FALLBACK_FAMILY, 12)).pack(padx=20, pady=30)
            except Exception:
                import tkinter.messagebox as mb
                mb.showerror("无法启动象棋", f"象棋模块加载失败：{exc}")

    # ---- 对局创建 ----
    def _on_new_game_click(self, variant: str = "connect6"):
        # 选择模式 / 执色 / AI 难度
        self._pending_variant = variant
        is_gomoku = (variant == "gomoku")
        dlg = tk.Toplevel(self)
        dlg.title("新建对局 · " + ("五子棋" if is_gomoku else "六子棋"))
        dlg.configure(bg=C_MAIN)
        dlg.resizable(False, False)
        # 先占位，构建完成后按实测请求高度定尺寸（见末尾），避免固定高度
        # 装不下「五子棋困难」的 3 行引擎说明 → 底部「开始」按钮被窗口裁掉。
        self._center_window(dlg, 400, 470)
        choice = {"mode": MODE_HUMAN_AI, "side": "black",
                  "difficulty": self.difficulty}
        diff_label = {v: k for k, v in DIFFICULTY_ORDER}.get(
            self.difficulty, "中等")

        tk.Label(dlg, text="对局模式", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=20, pady=(16, 2))
        mode_var = tk.StringVar(value="人机对战")
        modes = [("人机对战", MODE_HUMAN_AI), ("人人对战", MODE_HUMAN_HUMAN),
                 ("机机观战", MODE_AI_AI)]
        for label, m in modes:
            tk.Radiobutton(dlg, text=label, value=label, variable=mode_var,
                           bg=C_MAIN, fg=C_TEXT, selectcolor=C_MAIN_DARK,
                           activebackground=C_MAIN, activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=34)

        tk.Label(dlg, text="人机模式下你的执色", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=20, pady=(12, 2))
        side_var = tk.StringVar(value="执黑（先行）")
        for label, s in [("执黑（先行）", "black"), ("执白", "white")]:
            tk.Radiobutton(dlg, text=label, value=label, variable=side_var,
                           bg=C_MAIN, fg=C_TEXT, selectcolor=C_MAIN_DARK,
                           activebackground=C_MAIN, activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=34)

        # AI 难度三档（人机 / 机机生效；两种棋共用同一套难度体系）
        tk.Label(dlg, text="AI 难度", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(anchor="w", padx=20, pady=(12, 2))
        diff_var = tk.StringVar(value=diff_label)
        diff_row = tk.Frame(dlg, bg=C_MAIN)
        diff_row.pack(anchor="w", padx=34)
        for label, _key in DIFFICULTY_ORDER:
            tk.Radiobutton(diff_row, text=label, value=label,
                           variable=diff_var, bg=C_MAIN, fg=C_TEXT,
                           selectcolor=C_MAIN_DARK, activebackground=C_MAIN,
                           activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11)).pack(side="left", padx=(0, 10))
        # 五子棋「困难」的引擎说明（最高难度 = 完整算杀设计）
        tip = ("五子棋「困难」启用完整算杀引擎：\n"
               "根节点 VCF 连续冲四(14层) + VCT 连续威胁(8层)，\n"
               "叶节点算杀截断 + 6 层 Alpha-Beta 全局搜索。"
               if is_gomoku else
               "六子棋「困难」为强搜索档：\n12 层 Alpha-Beta + 威胁空间搜索。")
        tk.Label(dlg, text=tip, bg=C_MAIN, fg=C_TEXT_DIM, justify="left",
                 font=(FALLBACK_FAMILY, 9)).pack(anchor="w", padx=34, pady=(6, 0))

        def _ok():
            # mode_var 保存的是中文标签(如"人机对战")，按 {标签: 模式常量} 映射
            choice["mode"] = {label: m for label, m in modes}[mode_var.get()]
            choice["side"] = side_var.get().startswith("执黑") and "black" or "white"
            choice["difficulty"] = {k: v for k, v in DIFFICULTY_ORDER}.get(
                diff_var.get(), "medium")
            dlg.destroy()
            self._start_game(choice["mode"], choice["side"],
                             choice["difficulty"],
                             variant=self._pending_variant)

        GlowButton(dlg, "开始", command=_ok, width=220, height=48,
                   bg=C_ACCENT, fg="#1F2430",
                   font=(FALLBACK_FAMILY, 15, "bold")).pack(pady=(16, 18))

        # 定尺寸：按内容实测请求尺寸（含全部控件与内边距），并夹紧到屏幕内。
        # 这样无论哪一档难度、说明有几行，「开始」按钮都完整可见。
        try:
            dlg.update_idletasks()
            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
            # 宽度取「内容实测 / 440（保证标题栏不截断）」中的较大者
            need_w = max(440, int(dlg.winfo_reqwidth()) + 8)
            need_h = max(470, int(dlg.winfo_reqheight()) + 8)
            # 夹紧到屏幕可用区（小屏兜底），最后再取 ≥320 的下限
            need_w = max(320, min(need_w, sw - 40))
            need_h = max(320, min(need_h, sh - 80))
            dlg.geometry("")                 # 清除先前占位 geometry
            self._center_window(dlg, need_w, need_h)
        except Exception:
            pass

    def _start_game(self, mode: str, side: str, difficulty: str,
                   variant: str | None = None):
        self.variant = variant or "connect6"
        self.difficulty = difficulty
        self.human_side = BLACK if side == "black" else WHITE
        black_kind = white_kind = None
        if mode == MODE_HUMAN_AI:
            if self.human_side == BLACK:
                black_kind, white_kind = "human", "ai"
            else:
                black_kind, white_kind = "ai", "human"
        elif mode == MODE_HUMAN_HUMAN:
            black_kind = white_kind = "human"
        else:
            black_kind = white_kind = "ai"
        # 棋种决定棋盘尺寸 / 连子数 / 每回合子数：
        #   六子棋 19×19、连六、每轮 1~2 子；五子棋 15×15、连五、每轮 1 子
        if self.variant == "gomoku":
            bsize, bwin, gvar = 15, 5, "gomoku"
        else:
            bsize, bwin, gvar = 19, 6, "connect6"
        self.game = Game(
            black=Player("玩家" if black_kind == "human" else "AI黑",
                         kind=black_kind, difficulty=difficulty),
            white=Player("玩家" if white_kind == "human" else "AI白",
                         kind=white_kind, difficulty=difficulty),
            size=bsize, win_count=bwin, variant=gvar)
        # 默认不限时（休闲对弈）；如需计时对局可在设置中开启
        if not getattr(self, "timer_on", False):
            self.game.configure_timer(0, 0)
        self.selected = []
        self.thinking = False
        self._end_dialog_shown = False          # 新对局：重置终局弹窗标志
        self._reset_winrate()
        self._show_game()
        self._update_info()
        self._reset_step_ui()
        # 棋种相关文案 / 按钮（保持两种棋布局一致、文案自洽）
        try:
            self.side_title.config(
                text=("五子棋" if self.variant == "gomoku" else "六子棋") + f" · {APP_NAME}")
        except Exception:
            pass
        try:
            if self.variant == "gomoku":
                # 五子棋每回合固定 1 子、落子即结束本轮，"结束本回合"无意义，隐藏
                if self.btn_pass.winfo_ismapped():
                    self.btn_pass.pack_forget()
            else:
                if not self.btn_pass.winfo_ismapped():
                    self.btn_pass.pack(before=self.btn_undo, pady=4)
        except Exception:
            pass
        self.sound.play("click")
        # 若黑方为引擎，自动行棋
        self._schedule_ai_turn()

    # ---- 棋盘绘制（缩放核心） ----
    def _to_grid(self, px, py):
        """画布坐标 -> 格子坐标。

        必须与 _compute_geom 使用同一套几何（含自适应边距），否则窗口放大后
        点击位置会与棋盘错位。
        """
        if self.game is None:
            return None
        g = getattr(self, "_geom", None)
        if not g or g.get("cell", 0) <= 0:
            return None
        size = self.game.board.size
        gx = round((px - g["x0"]) / g["cell"])
        gy = round((py - g["y0"]) / g["cell"])
        if 0 <= gx < size and 0 <= gy < size:
            return (gx, gy)
        return None

    # 棋盘绘制缓存：分层 + 增量刷新（性能关键）
    #  - 静态层(底色托边/渐变/边框/网格/星位/坐标) 仅在"尺寸变化/换主题/换背景"时重画；
    #  - 棋子层 + 效果层(预览/高亮/闪烁) 每次落子只局部删除重画，不重建几百条网格线，
    #    落子因此流畅不卡。
    _tag_grid = "grid"
    _tag_stone = "stone"
    _tag_fx = "fx"

    def _compute_geom(self):
        """由当前画布尺寸计算棋盘几何并缓存；尺寸变化返回 True（需重建静态层）。

        关键：边距必须随"坐标文字外偏移"自适应。坐标文字离棋盘的距离
        outer_off ≈ cell*0.5，会随格子变大而增大（五子棋 15×15 的格子最大）。
        窗口最大化 / 大屏时格子变大，若仍用固定 BOARD_MARGIN(34)，坐标文字
        会被推出画布边缘裁掉，棋盘看起来"不完整"。这里迭代求出足够容纳
        「托盘 + 坐标文字」的边距，保证棋盘与坐标始终完整可见。
        """
        c = self.board_canvas
        W = max(c.winfo_width(), 1); H = max(c.winfo_height(), 1)
        changed = (W != getattr(self, "_last_w", -1)
                   or H != getattr(self, "_last_h", -1))
        self._last_w, self._last_h = W, H
        size = self.game.board.size if self.game else 19
        short = float(min(W, H))
        margin = float(BOARD_MARGIN)
        side = short - 2 * margin
        if size > 1:
            for _ in range(4):
                if side < 40:
                    break
                cell = side / (size - 1)
                outer_off = max(3.0, cell * 0.5 - 5)   # 与坐标绘制保持一致
                fsize = max(9.0, cell * 0.30)          # 坐标字号（与坐标绘制一致）
                need = outer_off + fsize * 0.5 + 6     # 文字外沿 + 余量
                margin = max(float(BOARD_MARGIN), need)
                side = short - 2 * margin
        if side < 40:
            return False
        cell = side / (size - 1) if size > 1 else 1.0
        self._geom = {
            "W": W, "H": H, "side": side,
            "x0": (W - side) / 2.0, "y0": (H - side) / 2.0,
            "cell": cell,
            "stone_r": max(3.0, cell * 0.44),
        }
        return changed

    def _redraw(self, force: bool = False):
        """重绘棋盘：尺寸变化/强制时重建静态层+棋子；否则只增量刷新棋子层。"""
        c = self.board_canvas
        if self.game is None:
            return
        # 主题色同步到画布底色 → 四周留白与棋盘同色（见 _redraw_full 底部）
        t = self.theme
        geom_changed = self._compute_geom()
        need_static = force or geom_changed
        try:
            if c.cget("bg") != t["bg_a"]:
                c.configure(bg=t["bg_a"])
        except Exception:
            pass
        if need_static:
            self._redraw_full()
        else:
            self._redraw_pieces()

    def _redraw_full(self):
        """全量重绘：静态层(网格/星位/坐标/边框/托盘) + 棋子层 + 效果层。"""
        c = self.board_canvas
        if self.game is None or not getattr(self, "_geom", None):
            return
        c.delete("all")
        g = self._geom
        W, H = g["W"], g["H"]
        x0, y0, cell = g["x0"], g["y0"], g["cell"]
        x1, y1 = x0 + g["side"], y0 + g["side"]
        t = self.theme

        # ---- 静态层 ----
        # 四周托盘：比棋盘略深的同色留白边，形成"棋盘色延伸一圈"的优雅边界。
        # 托盘约占 2/3 margin，剩余最小边与画布同色(bg_a)。
        pad = max(2.0, BOARD_MARGIN * 0.72)
        tray = blend(t["bg_a"], t["bg_b"], 0.18)
        c.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad,
                           fill=tray, outline="", tags=self._tag_grid)
        # 棋盘内部渐变背景
        for i in range(16):
            yy0 = y0 + (y1 - y0) * i / 16
            yy1 = y0 + (y1 - y0) * (i + 1) / 16 + 1
            col = blend(t["bg_a"], t["bg_b"], i / 15)
            c.create_rectangle(x0, yy0, x1, yy1, fill=col, outline="",
                               tags=self._tag_grid)
        # 木纹质感（随机短线条）已移除：原细短线在视觉上类似"刮痕"，
        # 与"真实自然"的目标相悖。棋盘表面改为纯净渐变，更干净通透；
        # 如需保留木质感，可改用 theme_boards 中低对比度、长向连续的纹理，
        # 切勿使用高频随机短线段（易产生刮痕错觉）。
        # 内边框 + 加粗网格线（更清晰、封边）
        lw = max(1, int(round(cell * 0.045))) or 1
        c.create_rectangle(x0, y0, x1, y1, fill="", outline=t["line"],
                           width=lw + 1, tags=self._tag_grid)
        b = self.game.board
        size = b.size
        for i in range(size):
            p = y0 + i * cell
            c.create_line(x0, p, x1, p, fill=t["line"], width=lw,
                          tags=self._tag_grid)
            p = x0 + i * cell
            c.create_line(p, y0, p, y1, fill=t["line"], width=lw,
                          tags=self._tag_grid)
        # 星位（略大，更醒目）
        stars = [3, size // 2, size - 4]
        sr = max(2.5, cell * 0.075)
        for sy in stars:
            for sx in stars:
                cx = x0 + sx * cell; cy = y0 + sy * cell
                c.create_oval(cx - sr, cy - sr, cx + sr, cy + sr,
                              fill=t["star"], outline="", tags=self._tag_grid)
        # 坐标文字
        fsize = max(9, int(cell * 0.30))
        outer_off = max(3, cell * 0.5 - 5)
        for i in range(size):
            c.create_text(x0 - outer_off, y0 + i * cell,
                          text=str(i + 1), fill=t["coord"],
                          font=(FALLBACK_FAMILY, fsize), tags=self._tag_grid)
            c.create_text(x0 + i * cell, y1 + outer_off,
                          text=chr(ord("A") + i), fill=t["coord"],
                          font=(FALLBACK_FAMILY, fsize), tags=self._tag_grid)

        # 棋子层 + 效果层
        self._draw_all_stones()
        self._redraw_fx()
        # 把静态层压到最底，棋子层盖其上
        c.tag_lower(self._tag_grid)

    def _draw_all_stones(self):
        """按 history 重画全部棋子（增量刷新时对 stone 层整层替换）。"""
        c = self.board_canvas
        c.delete(self._tag_stone)
        if self.game is None:
            return
        b = self.game.board
        if not b.history:
            return
        g = self._geom
        cell = g["cell"]; x0 = g["x0"]; y0 = g["y0"]; r = g["stone_r"]
        for (x, y, col) in b.history:
            self._draw_stone(x, y, col, cell, x0, y0, r)

    def _redraw_fx(self):
        """效果层：最后一手标记 + 待确认预览 + 胜利高亮（不含闪烁，闪烁独立）。"""
        c = self.board_canvas
        c.delete(self._tag_fx)
        c.delete("flash")
        if self.game is None:
            return
        g = self._geom
        cell = g["cell"]; x0 = g["x0"]; y0 = g["y0"]; r = g["stone_r"]
        b = self.game.board
        size = b.size

        # 最后一手标记
        if b.history:
            lx, ly, _ = b.history[-1]
            cx = x0 + lx * cell; cy = y0 + ly * cell
            mk = self.theme.get("coord", C_ACCENT)
            c.create_oval(cx - r * 0.32, cy - r * 0.32, cx + r * 0.32,
                          cy + r * 0.32, outline=mk, width=2, tags=self._tag_fx)

        # 待确认落子预览（连续选择 1~2 个）
        if self.selected and not self.thinking and not self.game.finished:
            for idx, (x, y) in enumerate(self.selected, start=1):
                if not b.is_empty(x, y):
                    continue
                cx = x0 + x * cell; cy = y0 + y * cell
                c.create_oval(cx - r * 0.9, cy - r * 0.9,
                              cx + r * 0.9, cy + r * 0.9,
                              fill=blend(C_GLOW, "#202530", 0.72),
                              outline="", tags=self._tag_fx)
                c.create_oval(cx - r * 0.6, cy - r * 0.6,
                              cx + r * 0.6, cy + r * 0.6,
                              fill="", outline=C_GLOW, width=2,
                              dash=(4, 3), tags=self._tag_fx)
                c.create_text(cx, cy, text=str(idx), fill=C_MAIN,
                              font=(FALLBACK_FAMILY, max(10, int(r)), "bold"),
                              tags=self._tag_fx)

        # 胜利连线高亮
        if self.game.finished and self.game.win_line:
            for (x, y) in self.game.win_line:
                cx = x0 + x * cell; cy = y0 + y * cell
                c.create_oval(cx - r * 0.5, cy - r * 0.5,
                              cx + r * 0.5, cy + r * 0.5,
                              fill="", outline=C_GLOW, width=3,
                              tags=self._tag_fx)

    def _redraw_pieces(self):
        """增量刷新：只重画棋子层与效果层（静态网格不动，性能优）。"""
        if self.game is None or not getattr(self, "_geom", None):
            return
        self._draw_all_stones()
        self._redraw_fx()

    def _draw_stone(self, x, y, col, cell, x0, y0, r):
        """绘制一枚棋子。

        首选：stonefx（PIL 超采样 + 真球面光影）—— 抗锯齿圆边、径向明暗、
        左上柔光、镜面高光、底部回光，黑曜石/玉白质感。
        Tk 的 create_oval/create_arc 无抗锯齿且画不出渐变，此前"亮色上半圆
        + 白点"的两色半月正是黑棋丑陋的根源；该画法仅作无 PIL 时兜底。
        """
        c = self.board_canvas
        cx = x0 + x * cell
        cy = y0 + y * cell
        ph = stonefx.get_stone_photo(c, r, col)
        if ph is not None:
            c.create_image(cx, cy, image=ph, tags=self._tag_stone)
            return
        self._draw_stone_vector(x, y, col, cell, x0, y0, r)

    def _draw_stone_vector(self, x, y, col, cell, x0, y0, r):
        """矢量兜底（无 PIL 环境）：描边 + 实心体 + 受光弧 + 高光点。"""
        c = self.board_canvas
        cx = x0 + x * cell; cy = y0 + y * cell
        if col == BLACK:
            rim = "#05070A"          # 外缘：近黑，清晰勾边
            body = "#20242C"         # 棋体：深灰蓝
            glow = "#46505F"         # 受光面：偏亮
            hi = "#B7C2D2"           # 高光点
        else:
            rim = "#8C887C"          # 外缘：暖灰，清晰勾边
            body = "#F7F4EB"         # 棋体：暖白
            glow = "#FFFFFF"         # 受光面：纯白
            hi = "#FFFFFF"           # 高光点
        # 紧致投影（偏移小、不透明，绝不发糊）
        sh = max(1.0, r * 0.14)
        c.create_oval(cx - r, cy - r + sh, cx + r, cy + r + sh,
                      fill=blend(self.theme["bg_b"], "#000000", 0.50),
                      outline="", tags=self._tag_stone)
        # 外缘描边（定义棋子轮廓）
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill=rim, outline=rim, width=1, tags=self._tag_stone)
        # 棋体（略小，露出 1px 描边，边缘更利落）
        rr = r - max(1.0, r * 0.08)
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                      fill=body, outline="", tags=self._tag_stone)
        # 受光面：顶部半圆更亮（start=200,extent=140 覆盖上方），
        # 形成"光来自上方"的球面立体感，边界锐利不晕。
        c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr,
                     start=200, extent=140,
                     fill=glow, outline="", tags=self._tag_stone)
        # 高光点（小而亮、清晰）
        hx, hy = cx - rr * 0.30, cy - rr * 0.36
        hhr = max(1.4, rr * 0.26)
        c.create_oval(hx - hhr, hy - hhr, hx + hhr, hy + hhr,
                      fill=hi, outline="", tags=self._tag_stone)

    # ---- 落子交互（连续选择：点 1 格 -> 选 1；点 2 格 -> 自动落子） ----
    def _on_click(self, e):
        if self.game is None or self.thinking or self.game.finished:
            return
        cur = self.game.current_player()
        if cur.kind != "human":
            return
        xy = self._to_grid(e.x, e.y)
        if xy is None:
            return
        x, y = xy
        b = self.game.board
        # 已选同一格：取消该格（toggle），方便玩家微调
        for i, (sx, sy) in enumerate(self.selected):
            if sx == x and sy == y:
                self.selected.pop(i)
                self._redraw()
                self._refresh_step_ui()
                self._update_sel_hint()
                return
        if not b.is_empty(x, y):
            self._set_sel_hint("该点已有棋子，请另选空点")
            return
        # 已满本轮下子数：不允许继续选
        max_can = self.game.max_stones - self.game.stones_this_round
        if len(self.selected) >= max_can:
            self._set_sel_hint(f"本轮已选 {len(self.selected)}/{self.game.max_stones} 子，请点「结束本回合」或先确认")
            return
        self.selected.append((x, y))
        self.sound.play("click")
        # 选满 -> 立即落子；如果 max_stones=1 也直接走 confirm
        if (self.game.max_stones > 1 and len(self.selected) >= 2) \
                or self.game.stones_this_round + len(self.selected) >= self.game.max_stones:
            self._refresh_step_ui()
            self._update_sel_hint()
            self._redraw()
            self._confirm_stone()
            return
        self._refresh_step_ui()
        self._update_sel_hint()
        self._redraw()

    def _update_sel_hint(self):
        """根据当前已选点数更新选中提示（连续选择语义）。"""
        if self.game is None:
            return
        if not self.selected:
            self._set_sel_hint("点击棋盘选位（最多 2 个），选满自动落子")
            return
        n = len(self.selected)
        max_can = self.game.max_stones - self.game.stones_this_round
        if self.game.max_stones == 1:
            self._set_sel_hint(f"已选 {n}/{self.game.max_stones} 子，按回车或点「确认落子」")
        elif n >= 2 or n >= max_can:
            self._set_sel_hint(f"已选 {n}/{max_can} 子，选满即自动落子")
        else:
            self._set_sel_hint(f"已选 {n}/{max_can} 子，可继续选第 {n+1} 个，或回车确认")

    # ---- 确认落子（按当前 selected 列表一次性落 1~2 子） ----
    def _confirm_stone(self):
        if self.game is None or self.thinking or self.game.finished:
            return
        cur = self.game.current_player()
        if cur.kind != "human":
            return
        if not self.selected:
            self._set_sel_hint("请先在棋盘上选择落子位置")
            return
        # 合法性预检：所有点必须空，且同一轮内不能与已落子重合
        b = self.game.board
        for (x, y) in self.selected:
            if not b.is_empty(x, y):
                self.selected = []
                self._set_sel_hint("所选点已被占用，请重新选位")
                self._refresh_step_ui()
                self._redraw()
                return
        # 一次性 place 所有已选点；若任一失败则整体回滚（self.selected 重置）
        to_place = list(self.selected)
        self.selected = []
        any_ok = False
        last_line = None
        finished = False
        for (x, y) in to_place:
            ok, msg, line = self.game.place(x, y)
            if ok:
                any_ok = True
                last_line = line
                self.sound.play("stone")
                if line is not None or self.game.finished:
                    finished = True
                    break
            else:
                self._set_sel_hint(msg)
                if not any_ok:
                    # 第一次就失败 -> 全部撤销（无法真撤销，回滚 UI 即可）
                    self._update_info()
                    self._refresh_step_ui()
                    self._redraw()
                    return
                break
        self._refresh_step_ui()
        self._redraw()
        try:
            self._sync_winrate()
        except Exception:
            pass
        self._update_info()
        if finished or self.game.finished:
            self._on_game_end()
            return
        # 本轮仍可下子但轮到人类 -> 让玩家决定再下一子或结束
        self._finish_human_round_or_wait()

    def _finish_human_round_or_wait(self):
        """人类本轮落子后：若下满则结束；若没下满，等待玩家决定再下一子或结束本回合。"""
        if self.game is None or self.game.finished:
            return
        cur = self.game.current_player()
        if cur.kind == "human":
            if self.game.stones_this_round >= self.game.max_stones:
                self.game.end_round()
                self._update_info()
                self._refresh_step_ui()
            else:
                # 还可以再下一子；若已下 1 子，可再选 1 子或点结束
                left = self.game.max_stones - self.game.stones_this_round
                self._set_sel_hint(f"已落 {self.game.stones_this_round}/{self.game.max_stones} 子，"
                                   f"还可下 {left} 子，或点「结束本回合」")
        # 轮到引擎 -> 自动行棋
        self._schedule_ai_turn()

    def _schedule_ai_turn(self):
        if self.game is None or self.game.finished:
            return
        cur = self.game.current_player()
        if cur.kind == "human":
            self._update_info()
            return
        if self.thinking:
            return
        self.thinking = True
        self._set_thinking(True)
        threading.Thread(target=self._ai_worker, daemon=True).start()

    def _ai_worker(self):
        def safe_schedule(fn):
            """把回调放入线程安全队列，由主线程轮询执行。

            绝不能在后台线程直接调用 self.after()——tkinter 的 Tk 方法
            只允许主线程调用，跨线程调用会被静默丢弃或抛错（被吞掉后
            AI 结果永远不回填，thinking 状态卡死，界面无法继续落子）。
            """
            try:
                self._bg_queue.put(fn)
            except Exception:
                pass
        try:
            _lower_thread_priority()
            time.sleep(0.1)  # 让界面先刷新
            stones = self.game.ai_turn(show_info=False)
            safe_schedule(lambda: self._apply_ai_result(stones))
        except Exception as exc:
            safe_schedule(lambda e=exc: self._apply_ai_error(e))

    def _drain_bg_queue(self):
        """主线程：消费后台线程的结果队列并执行回调（每 100ms 一次）。"""
        try:
            if not self.winfo_exists():
                return
            # 终局兜底网：每 5 次（约 0.5s）做一次全盘深度扫描
            self._net_cnt = getattr(self, "_net_cnt", 0) + 1
            self._check_end_net(deep=(self._net_cnt % 5 == 0))
            for _ in range(64):
                try:
                    fn = self._bg_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                self._bg_job = self.after(100, self._drain_bg_queue)
            except Exception:
                pass

    def _apply_ai_result(self, stones):
        self.thinking = False
        self._set_thinking(False)
        if self.game is None:
            return
        # 先快照终局状态：终局判定绝不能被后续胜率绘制异常影响
        finished = bool(self.game.finished)
        self._flash_stones(stones)
        self.sound.play("stone")
        self._redraw()
        try:
            self._sync_winrate()
        except Exception:
            pass
        # 阶段6：并入本次 AI 搜索的根分值校正曲线（每 _search_refresh_every 子做一次，
        # 不额外起搜索，直接复用引擎刚算好的 best_val）
        if stones and _HAVE_WR2:
            mc = self.game.board.move_count
            if mc % self._search_refresh_every == 0:
                _lx, _ly, mover = stones[-1]
                pl = self.game.players[mover]
                if pl.kind == "ai" and getattr(pl, "engine", None) is not None:
                    score = getattr(pl.engine, "last_val", 0.0)
                    self._search_refine(score, mover, mc - 1)
        self._update_info()
        self._refresh_step_ui()
        if finished:
            self._on_game_end()
            return
        self._schedule_ai_turn()

    def _apply_ai_error(self, exc):
        self.thinking = False
        self._set_thinking(False)
        self._set_status(f"AI 出错：{exc}")
        # 回退到人类接管，避免卡死
        self.game.end_round()
        self._update_info()
        self._refresh_step_ui()

    def _flash_stones(self, stones):
        """落子闪烁（短暂高亮）。闪烁在棋子层之上，独立 tag 便于随刷新清理。"""
        if not stones or self.game is None:
            return
        c = self.board_canvas
        g = getattr(self, "_geom", None)
        if not g:
            return
        cell = g["cell"]; x0 = g["x0"]; y0 = g["y0"]
        c.delete("flash")
        for i, (x, y) in enumerate(stones):
            cx = x0 + x * cell; cy = y0 + y * cell
            item = c.create_oval(cx - cell * 0.55, cy - cell * 0.55,
                                 cx + cell * 0.55, cy + cell * 0.55,
                                 fill="", outline=C_GLOW, width=3,
                                 tags="flash")
            c.after(120 + i * 90, lambda it=item: c.delete(it))

    # ---- 胜率曲线 ----
    def _reset_winrate(self):
        """新对局 / 回到菜单时清空曲线，影子棋盘置空，异步状态复位。"""
        self._wr_y = []
        self._wr_board = None
        self._wr_mc_refined = set()
        self._wr_mc_worker_running = False
        self._wr_redraw_pending = False
        self._wr_gen += 1

    # ---- 6 阶段胜率流水线 ----
    # 阶段1-3（同步、毫秒级）：先把每步新增的曲线点用"路评分+威胁差→快映射"补上，
    # 让曲线即时出现、不卡 UI。
    def _sync_winrate(self):
        """阶段 1~3：把曲线补到与棋盘手数一致（每子一点，即时快估计）。

        影子棋盘与真实盘前缀一致；每次只对新增棋子增量取点，AI 一轮下 2 子
        也能逐子出点。写完后触发阶段 4-6 的异步精化。
        """
        if self.game is None:
            return
        live = self.game.board
        if not _HAVE_WR2 and winrate_black is None:
            return
        try:
            if self._wr_board is None:
                self._wr_board = Board(live.size, live.win_count)
            sb = self._wr_board
            # 真实盘回退（悔棋）或尺寸不符 -> 影子整体重建
            if sb.move_count > live.move_count or sb.size != live.size:
                self._wr_board = Board(live.size, live.win_count)
                self._wr_y = []
                self._wr_mc_refined = set()
                self._wr_gen += 1
                sb = self._wr_board
            # 防御性硬上限：正常情况每轮 place 必推进 move_count（严格 +1），
            # 循环最多 live.move_count 次即终止。上限取 2*+16 以容纳"悔棋/影子
            # 重建"导致的极端重放，同时杜绝任何理论上的无限自旋（主线程卡死）。
            guard = 0
            max_guard = live.move_count * 2 + 16
            while sb.move_count < live.move_count and guard < max_guard:
                guard += 1
                x, y, c = live.history[sb.move_count]
                if not sb.is_empty(x, y):
                    self._wr_board = Board(live.size, live.win_count)
                    self._wr_y = []
                    self._wr_mc_refined = set()
                    self._wr_gen += 1
                    sb = self._wr_board
                    if sb.move_count >= live.move_count:
                        break
                    x, y, c = live.history[sb.move_count]
                before = sb.move_count
                sb.place(x, y, c)
                if sb.move_count == before:
                    # place 未生效（如历史里出现非法颜色值）：立即跳出，绝不自旋
                    break
                if _HAVE_WR2:
                    p = winrate2.fast_black_winrate(sb)      # 阶段3 快映射
                elif winrate_black is not None:
                    p = winrate_black(sb)
                else:
                    p = 0.5
                self._wr_y.append(round(p * 100.0, 1))
        except Exception:
            return
        # 尾巴也必须自包异常：_draw_winrate / _start_wr_async 一旦抛异常，
        # 若冒泡到 _apply_ai_result / _confirm_stone，会跳过紧随其后的
        # _on_game_end()，导致“看到胜利却没弹窗”。这里兜底吞掉，保证终局判定不被胜率绘制影响。
        try:
            self._draw_winrate()
            # 异步精化（阶段 4-6），在 GUI 主线程之外的后台线程执行，绝不卡界面
            self._start_wr_async()
        except Exception:
            pass

    # 阶段 4-5：蒙特卡洛精化"最新曲线点"（后台线程、复用棋盘，省内存）
    #
    # 性能策略：只精化最新的 1 个点（刚落的子变化最大、最值得精化），
    # 早期各点已由阶段1-3的快估计覆盖，不必在后台逐点回补整条历史——
    # 那会让后台线程在整局里持续低频打断主线程重绘，正是"曲线卡顿"来源。
    # 线程仅在落子时启动、跑完即止，不自动链式补全历史点。
    _wr_refine_window = 1   # 精化最新 N 个点（窗口外视为已足够精确）

    def _start_wr_async(self):
        if not _HAVE_WR2 or self.game is None:
            return
        if self.game.finished:
            return
        if self._wr_mc_worker_running:
            return
        n = len(self._wr_y)
        if n == 0:
            return
        # 只考虑窗口内的点（最新 _wr_refine_window 个）
        lo = max(0, n - self._wr_refine_window)
        idx = None
        for k in range(n - 1, lo - 1, -1):
            if k not in self._wr_mc_refined:
                idx = k
                break
        if idx is None:
            return
        live = self.game.board
        gen = self._wr_gen
        try:
            snap = Board(live.size, live.win_count)
            for i in range(idx + 1):
                hx, hy, hc = live.history[i]
                if not snap.is_empty(hx, hy):
                    snap = live.snapshot()
                    break
                snap.place(hx, hy, hc)
        except Exception:
            return
        self._wr_mc_worker_running = True
        threading.Thread(target=self._wr_mc_worker,
                         args=(idx, gen, snap), daemon=True).start()

    def _wr_mc_worker(self, idx: int, gen: int, snap):
        """后台线程体：对某个前缀棋盘做蒙特卡洛，再把结果交给主线程回填。

        仅在后台做纯计算(mc_black_winrate)，绝不碰 tkinter；结果经
        _bg_queue 交主线程执行（跨线程调用 self.after 会被静默丢弃）。
        """
        try:
            _lower_thread_priority()
            p = winrate2.mc_black_winrate(
                snap, sims=5000, time_budget=3.0)   # 阶段4-5 强力 MC（全局胜率主信号）
        except Exception:
            p = None
        try:
            self._bg_queue.put(lambda: self._wr_apply_mc(idx, gen, p))
        except Exception:
            self._wr_mc_worker_running = False

    def _wr_apply_mc(self, idx: int, gen: int, p):
        """主线程：把蒙特卡洛结果回填曲线点 idx 并重绘。"""
        try:
            if gen != self._wr_gen:
                return                       # 局已换/悔棋，丢弃过期结果
            if p is not None and idx < len(self._wr_y):
                self._wr_y[idx] = round(p * 100.0, 1)
                self._wr_mc_refined.add(idx)
                self._schedule_wr_redraw()    # 节流合并重绘，避免后台回填高频全量刷新
        except Exception:
            pass
        finally:
            # 只释放运行标志；不自动补下一个旧点。
            # 下次落子的 _sync_winrate 会重新对最新点触发精化，避免整局链式后台补全。
            self._wr_mc_worker_running = False

    def _schedule_wr_redraw(self):
        """胜率曲线节流重绘：高频小更新(MC回填/搜索校正)合并到一次 after 绘制。"""
        if getattr(self, "_wr_redraw_pending", False):
            return
        self._wr_redraw_pending = True
        try:
            self.after(40, self._wr_redraw_flush)
        except Exception:
            self._wr_redraw_pending = False
            self._draw_winrate()

    def _wr_redraw_flush(self):
        self._wr_redraw_pending = False
        self._draw_winrate()

    # 阶段 6：并入"已有 AI 搜索"结果校正曲线（不额外起搜索）。
    # 每当引擎刚走完一手并给出搜索分值，用它精化该手对应的曲线点。
    def _search_refine(self, search_score, mover, point_idx):
        if not _HAVE_WR2 or not 0 <= point_idx < len(self._wr_y):
            return
        try:
            p = winrate2.search_score_to_black(search_score, mover,
                                                self.game.board)
            self._wr_y[point_idx] = round(p * 100.0, 1)
            self._wr_mc_refined.add(point_idx)   # 已被搜索精化，可跳过蒙特卡洛
            self._schedule_wr_redraw()
        except Exception:
            pass

    def _draw_winrate(self):
        """绘制胜率折线图。坐标为画布像素，右下对齐以免被侧栏裁剪。"""
        if not hasattr(self, "wr_canvas"):
            return
        c = self.wr_canvas
        # 面板底色：跟随当前侧栏主色(C_MAIN_DARK)微提亮，切换背景色时整块随之变化。
        # 即便画布过小无法绘图，也要先把底色刷新到位，避免四周露旧色块。
        panel_bg = blend(C_MAIN_DARK, "#FFFFFF", 0.06)
        try:
            if c.cget("bg") != panel_bg:
                c.configure(bg=panel_bg)
        except Exception:
            pass
        c.delete("all")
        W = max(c.winfo_width(), 1); H = max(c.winfo_height(), 1)
        if W < 60 or H < 40:
            return
        pad_l, pad_r, pad_t, pad_b = 6, 6, 8, 14
        plot_w = W - pad_l - pad_r
        plot_h = H - pad_t - pad_b
        if plot_w <= 2 or plot_h <= 2:
            return

        # 背景网格
        c.create_rectangle(0, 0, W, H, fill=panel_bg, outline="")
        # 基线 50%
        by = pad_t + plot_h * (1 - 0.5)
        c.create_line(pad_l, by, W - pad_r, by, fill="#4A5466", width=1, dash=(2, 2))
        # 100% 与 0% 参考线
        c.create_line(pad_l, pad_t, W - pad_r, pad_t, fill="#333A4C", width=1)
        c.create_line(pad_l, pad_t + plot_h, W - pad_r, pad_t + plot_h, fill="#333A4C", width=1)

        # 顶点标注（0 / 25 / 50 / 75 / 100）
        for val in (0, 25, 50, 75, 100):
            yy = pad_t + plot_h * (1 - val / 100.0)
            c.create_line(pad_l, yy, pad_l + 3, yy, fill="#5A6577", width=1)
            c.create_text(pad_l + 3, yy, text=str(val), anchor="w",
                          fill="#6B7486", font=(FALLBACK_FAMILY, 8))

        n = len(self._wr_y)
        if n == 0:
            c.create_text(W / 2, H / 2, text="对局开始后显示走势",
                          fill=C_TEXT_DIM, font=(FALLBACK_FAMILY, 10))
            return

        # 滚动窗口：点数超过上限时只绘制最近 MAX_PTS 手，避免一次重建超长折线
        # 造成的卡顿，同时保证纵轴走势与最新一手仍清晰可读。
        MAX_PTS = 90
        wstart = max(0, n - MAX_PTS)     # 曲线起点下标（0 基）
        view = self._wr_y[wstart:]        # 窗口内 y 值（wstart 对应手序 wstart+1）

        # 时序平滑（EMA）：MC 单点噪声 + fast 估计的局部抖动会让曲线出现
        # 无意义锯齿。对"历史段"做轻量 EMA，但保留最新点原值（最新点是最强
        # MC 精化结果，最准、不应被历史拖拽）。只影响显示走势、不改原始数据，
        # 让"纵观全局"的胜率趋势连贯可读。alpha 取 0.35，滞后小。
        def _ema_series(ys, alpha=0.35):
            if len(ys) <= 2:
                return ys
            out = []
            prev = ys[0]
            for v in ys[:-1]:
                prev = alpha * v + (1.0 - alpha) * prev
                out.append(prev)
            out.append(ys[-1])          # 最新点保留原值
            return out

        view = _ema_series(view)

        # 归一化 x：窗口内第 1 点映射画布左缘，最新点映射右缘
        xmin, xmax = 1, max(1, len(view))

        def xpx(xv):
            return pad_l + plot_w * (xv - xmin) / max(1.0, xmax - xmin)

        def ypx(yv):
            return pad_t + plot_h * (1 - min(100.0, max(0.0, yv)) / 100.0)

        # 折线（横坐标为窗口内顺序）
        pts = []
        for xv, yv in enumerate(view, start=1):
            pts.append((xpx(xv), ypx(yv)))
        if len(pts) >= 2:
            c.create_line(*sum(pts, ()), fill=C_ACCENT, width=2, smooth=True)
        # 手序点的圆点（点数过多时稀疏取样）
        step = max(1, len(pts) // 40)
        for i in range(0, len(pts), step):
            px, py = pts[i]
            c.create_oval(px - 2.5, py - 2.5, px + 2.5, py + 2.5,
                          fill=C_ACCENT, outline="")
        # 最新点高亮 + 标注当前胜率
        lx, ly = pts[-1]
        c.create_oval(lx - 4, ly - 4, lx + 4, ly + 4, fill=C_GLOW, outline="")
        cur = view[-1]
        tag = f"{cur:.0f}%"
        ax = lx + 8
        if ax + 30 > W:
            ax = lx - 8 - len(tag) * 7
        c.create_text(ax, ly, text=tag, anchor="w" if ax > lx else "e",
                      fill=C_GLOW, font=(FALLBACK_FAMILY, 9, "bold"))

        # 底部横轴提示：当前窗口首末绝对手数
        first_hand = wstart + 1
        c.create_text(pad_l, H - 2, text=f"手{first_hand}", anchor="sw",
                      fill="#6B7486", font=(FALLBACK_FAMILY, 8))
        c.create_text(W - pad_r, H - 2, text=f"手{n}", anchor="se",
                      fill="#6B7486", font=(FALLBACK_FAMILY, 8))

        # 更新右上角黑/白胜率
        bw = cur
        ww = 100.0 - bw
        self.lbl_wr_now.config(text=f"黑 {bw:.0f}% · 白 {ww:.0f}%")

    # ---- 信息更新 / 计时 ----
    def _update_info(self):
        if self.game is None:
            return
        g = self.game
        nb = self._player_label(g.players[BLACK], "黑")
        nw = self._player_label(g.players[WHITE], "白")
        self.lbl_black.config(text=f"黑方：{nb}")
        self.lbl_white.config(text=f"白方：{nw}")
        if g.finished:
            self.lbl_status.config(text=g.result_text())
        else:
            cur = g.current_player()
            if cur.kind == "human":
                # 人人对战时两个人都是 human，不能用"你"，须按棋色指明
                both_human = (g.players[BLACK].kind == "human"
                              and g.players[WHITE].kind == "human")
                who = (f"{COLOR_NAMES[g.current]}（{cur.name}）" if both_human
                       else "你")
            else:
                who = cur.name
            self.lbl_status.config(text=f"轮到：{who}（{g.max_stones - g.stones_this_round} 子可选）")
        # 时间显示
        if g.timer_enabled and not g.finished:
            self.lbl_time.config(text=f"剩余时间：{g.time_str(g.current_remain())}")
        else:
            self.lbl_time.config(text="计时：不限时")

    def _player_label(self, p, tag):
        if p.kind == "human":
            return f"{tag} · 玩家"
        if p.kind == "llm":
            eng = getattr(p, "engine", None)
            return f"{tag} · {getattr(eng, 'display_name', 'LLM')}"
        return f"{tag} · AI-{DIFFICULTY_CN.get(p.difficulty, p.difficulty)}"

    # ---- 两步交互 UI 状态 ----
    def _set_thinking(self, on: bool):
        if on:
            self.lbl_status.config(text="AI 思考中…")

    def _set_status(self, s: str):
        if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
            self.lbl_status.config(text=s)

    # ---- 轻提示（Toast）----
    def _toast(self, text: str, kind: str = "ok", ms: int = 3200,
               detail: str = ""):
        """在窗口底部浮出一条**非模态**提示，ms 毫秒后自动淡出。

        用于「数据库已就绪」这类无需打断操作的反馈：不抢焦点、不阻塞输入，
        与状态栏文字互补（状态栏可能被后续消息覆盖，浮层保证被看到）。
        样式与游戏一致：圆角玻璃卡片 + 金色描边 + 左侧状态色条。
        """
        try:
            self._toast_close()
        except Exception:
            pass
        try:
            import tkinter.font as tkfont
            col = {"ok": C_ACCENT, "info": C_TEXT_DIM,
                   "warn": C_ACCENT_DARK, "err": "#E5654B"}.get(kind, C_ACCENT)
            fam = getattr(self.fm, "current_family", FALLBACK_FAMILY)
            # 卡片尺寸按**实测文字度量**推导（而非按字数估算），
            # 字体/DPI/族变化都不会出现文字溢出或被裁。
            sc = max(1.0, float(getattr(self, "_dpi", 1.0) or 1.0))
            f1 = tkfont.Font(family=fam, size=12, weight="bold")
            f2 = tkfont.Font(family=FALLBACK_FAMILY, size=10)
            pad_x, pad_y = int(15 * sc), int(13 * sc)
            bar_w, gap = int(5 * sc), int(13 * sc)
            ls1 = f1.metrics("linespace")
            ls2 = f2.metrics("linespace") if detail else 0
            sep = int(3 * sc) if detail else 0
            inner = max(f1.measure(text), f2.measure(detail) if detail else 0)
            tw = pad_x * 2 + bar_w + gap + inner
            th = pad_y * 2 + ls1 + (ls2 + sep if detail else 0)
            maxw = max(int(160 * sc), self.winfo_width() - int(28 * sc))
            tw = max(min(tw, maxw), min(int(240 * sc), maxw))
            th = max(th, int(50 * sc))
            tx = pad_x + bar_w + gap          # 文字左起点（色条右侧）
            ty1 = pad_y + ls1 // 2
            ty2 = pad_y + ls1 + sep + ls2 // 2
            radius = max(4, int(13 * sc))
            win = tk.Toplevel(self)
            win.overrideredirect(True)
            try:
                win.transient(self)
            except Exception:
                pass
            key = "#0B0D12"          # 卡片外的抠色，Windows 下透明 -> 真圆角
            win.configure(bg=key)
            try:
                win.wm_attributes("-transparentcolor", key)
            except Exception:
                pass
            cv = tk.Canvas(win, width=tw, height=th, bg=key,
                           highlightthickness=0, bd=0)
            cv.pack()
            cv.create_polygon(
                rounded_rect_points(1, 1, tw - 1, th - 1, radius),
                fill=C_PANEL_BG, outline="", width=0)
            cv.create_polygon(
                rounded_rect_points(1, 1, tw - 1, th - 1, radius),
                fill="", outline=col, width=1)
            cv.create_polygon(
                rounded_rect_points(pad_x, pad_y, pad_x + bar_w, th - pad_y,
                                    max(1.5, bar_w / 2.0)),
                fill=col, outline="", width=0)
            cv.create_text(tx, ty1 if detail else th / 2, text=text,
                           fill=C_TEXT, font=(fam, 12, "bold"), anchor="w")
            if detail:
                cv.create_text(tx, ty2, text=detail, fill=C_TEXT_DIM,
                               font=(FALLBACK_FAMILY, 10), anchor="w")
            self._toast_win = win
            # 位置：水平居中、底部音乐栏上方；先低 off 再上浮（滑入）
            self.update_idletasks()
            off = int(16 * sc)
            mx = max(0, self.winfo_rootx() + (self.winfo_width() - tw) // 2)
            y = self.winfo_rooty() + max(
                off, self.winfo_height() - th - int(96 * sc))
            win.geometry(f"{tw}x{th}+{mx}+{y + off}")
            win.lift()

            def _slide(step: int = 0):
                if step >= 8:
                    win.geometry(f"{tw}x{th}+{mx}+{y}")
                    self._toast_jobs.append(self.after(ms, _fade))
                    return
                k = (step + 1) / 8.0
                win.geometry(f"{tw}x{th}+{mx}+{int(y + off * (1 - k))}")
                self._toast_jobs.append(self.after(16, lambda: _slide(step + 1)))

            def _fade(a: float = 1.0):
                a -= 0.12
                if a <= 0:
                    self._toast_close()
                    return
                try:
                    win.wm_attributes("-alpha", a)
                except Exception:
                    self._toast_close()
                    return
                self._toast_jobs.append(
                    self.after(28, lambda: _fade(a)))

            self._toast_jobs.append(self.after(16, _slide))
        except Exception:
            try:
                self._toast_close()
            except Exception:
                pass

    def _toast_close(self):
        """销毁当前轻提示浮层并取消其挂起动画（幂等）。"""
        win, self._toast_win = self._toast_win, None
        jobs, self._toast_jobs = list(self._toast_jobs), []
        for job in jobs:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def _set_sel_hint(self, s: str):
        if hasattr(self, "lbl_sel") and self.lbl_sel.winfo_exists():
            self.lbl_sel.config(text=s)

    def _refresh_step_ui(self):
        """依据当前状态刷新确认/取消按钮的可用性。"""
        if not hasattr(self, "btn_confirm"):
            return
        human_can_act = False
        if (self.game is not None and not self.thinking and not self.game.finished):
            cur = self.game.current_player()
            if cur.kind == "human":
                can_place = self.game.stones_this_round < self.game.max_stones
                # 连续选择：只要列表非空 + 每个点都是空格即可点确认
                has_sel = bool(self.selected) and all(
                    self.game.board.is_empty(x, y) for (x, y) in self.selected)
                human_can_act = can_place and has_sel
        self.btn_confirm.set_enabled(human_can_act)
        self.btn_clear.set_enabled(bool(self.selected))

    def _reset_step_ui(self):
        self.selected = []
        self._refresh_step_ui()
        max_s = 1 if getattr(self, "variant", "connect6") == "gomoku" else 2
        self._set_sel_hint(f"点击棋盘选位，选满自动落子（最多 {max_s} 个）")

    def _clear_selection(self):
        self.selected = []
        self._refresh_step_ui()
        self._set_sel_hint("已取消选择")
        self._redraw()

    def _on_enter_confirm(self, _e=None):
        # 回车 = 确认落子
        if self.game and self.thinking:
            return
        if self.selected and self.btn_confirm._enabled:
            self._confirm_stone()

    def _on_escape_clear(self, _e=None):
        if self.selected:
            self._clear_selection()

    def _timer_tick(self):
        try:
            if self.game and not self.game.finished and self.game.timer_enabled:
                self.game.tick(0.25)
                r = self.game.current_remain()
                self.lbl_time.config(text=f"剩余时间：{self.game.time_str(r)}")
                if self.game.finished:
                    self._update_info()
                    self._on_game_end()
        except Exception:
            pass
        # 终局兜底网：计时器无论是否启用都在跑，顺带每拍浅查、每 4 拍深扫
        try:
            self._tick_cnt = getattr(self, "_tick_cnt", 0) + 1
            self._check_end_net(deep=(self._tick_cnt % 4 == 0))
        except Exception:
            pass
        self._timer_job = self.after(250, self._timer_tick)
    # ---- 对局结束 / 存档 ----
    def _on_game_end(self):
        """终局处理（幂等）：每一步独立保护，任何一步失败都不阻断结果弹窗。"""
        if self.game is None:
            return
        if getattr(self, "_end_dialog_shown", False):
            return                      # 已处理过终局，防止重复弹窗
        self._end_dialog_shown = True
        for step in (self._update_info, self._redraw,
                     self._refresh_step_ui, self._save_game_async):
            try:
                step()
            except Exception:
                pass
        # 弹结束提示（用 after 切回主线程，避免在后台线程里弹模态阻塞）。
        # 用 _show_end_dialog_safe 兜底：无论自绘弹窗是否抛异常，用户一定能看到结果。
        try:
            if self.winfo_exists():
                self.after(50, self._show_end_dialog_safe)
        except Exception:
            self._show_end_dialog_safe()

    def _show_end_dialog_safe(self):
        """安全壳：尝试自绘弹窗；任何异常都回退到原生 messagebox，并保证记录堆栈。"""
        try:
            self._show_end_dialog()
        except Exception as _e:
            import traceback as _tb
            try:
                import os as _os
                _log = _os.path.join(logs_dir(), "end_dialog_error.log")
                with open(_log, "a", encoding="utf-8") as _f:
                    _f.write("\n===== _show_end_dialog 异常堆栈 =====\n")
                    _tb.print_exc(file=_f)
            except Exception:
                pass
            try:
                if self.game is not None:
                    messagebox.showinfo("对局结束", self.game.result_text(),
                                        parent=self)
            except Exception:
                pass

    def _check_end_net(self, deep=False):
        """终局兜底网（多路判定，不依赖单一调用点）。

        第一路：game.finished 已置位但弹窗未弹出（异常被吞 / after 回调丢失）
                —— 立即补弹。
        第二路（deep=True 时）：全盘扫描 board.scan_win()。盘面上客观存在
                ≥6 连就强制终局并弹窗——即使落子瞬间的 check_win 因任何
                原因漏判，这里也能把结果找回来。黑白双方通吃。
        """
        g = self.game
        if g is None:
            return
        if g.finished:
            if not getattr(self, "_end_dialog_shown", False):
                self._on_game_end()
            return
        if not deep:
            return
        # 深度兜底：全盘扫描（浅拷贝快照，避免与后台 AI 线程竞争写坏）
        try:
            winner, line = g.board.snapshot().scan_win()
        except Exception:
            return
        if winner is None:
            return
        try:
            g._finish(winner, g._win_reason(), line)
        except Exception:
            g.finished = True
            g.winner = winner
            g.win_line = line
        self._update_info()
        self._on_game_end()

    def _save_game_async(self):
        if self.game is None or Database is None:
            return
        g = self.game
        record = g.to_record()
        threading.Thread(target=self._db_save_worker, args=(record,), daemon=True).start()

    def _db_save_worker(self, record):
        """后台线程写库；结果回投主线程，成功/失败都给出可见反馈（不再静默）。"""
        ok, err = False, ""
        try:
            db = Database()
            db.connect()
            db.save_game(record, record["moves"])
            db.close()
            ok = True
        except Exception as exc:
            # 数据库未就绪时降级：不影响对弈，但必须让用户知道"这局没存上"
            err = str(exc).strip() or type(exc).__name__
        try:
            self._bg_queue.put(lambda: self._on_save_done(ok, err))
        except Exception:
            pass

    def _on_save_done(self, ok: bool, err: str = ""):
        """主线程：对局存档结果反馈（状态栏常驻 + 轻提示，全局可见）。"""
        if ok:
            self._set_status("对局已存档")
            self._toast_when_idle("对局已存档", kind="ok",
                                  detail="可在「战绩查询」中查看本局")
        else:
            self._set_status("对局存档失败")
            self._toast_when_idle("对局存档失败", kind="warn",
                                  detail=f"未写入数据库：{err[:48]}")

    def _toast_when_idle(self, text: str, kind: str = "ok",
                         detail: str = "", tries: int = 26):
        """在当前没有模态弹窗时才显示轻提示。

        终局时"结束弹窗"与"存档结果"几乎同时到达，浮层若直接显示会盖住
        弹窗按钮——这里轮询等待弹窗关闭（最多约 8 秒），期间状态栏已有反馈，
        超时则放弃浮层，绝不遮挡用户正在操作的弹窗。
        """
        try:
            if self.grab_current() is None:
                self._toast(text, kind=kind, detail=detail)
                return
            if tries <= 0:
                return
            self.after(300, lambda: self._toast_when_idle(
                text, kind, detail, tries - 1))
        except Exception:
            pass

    def _show_end_dialog(self):
        """对局结束：用游戏内带花纹的自绘弹窗展示结果，支持复盘/重开。

        复盘会打开棋谱回放窗口（含暂停与速度控制，默认较慢速）。
        """
        if self.game is None:
            return
        if OrnateDialog is None:
            messagebox.showinfo("对局结束", self.game.result_text(), parent=self)
            return
        g = self.game
        result = g.result_text()

        # 人类视角描述：仅人机对战使用"你"；人人/机机对战必须指明是哪一方
        human_side = getattr(self, "human_side", None)
        both_human = (g.players[BLACK].kind == "human"
                      and g.players[WHITE].kind == "human")
        has_human = (not both_human and human_side is not None
                     and g.players[human_side].kind == "human")
        you_win = None
        if has_human and g.winner is not None:
            you_win = (g.winner == human_side)
        line2 = ""
        title = "对局结束"
        if both_human:
            # 人人对战：按棋色 + 玩家名指明胜负双方
            if g.winner is None:
                line2 = "本局为平局"
            else:
                loser = WHITE if g.winner == BLACK else BLACK
                line2 = (f"{COLOR_NAMES[g.winner]}（{g.players[g.winner].name}）获胜，"
                         f"{COLOR_NAMES[loser]}（{g.players[loser].name}）落败")
        elif has_human:
            if g.winner is None:
                line2 = "本局为平局"
            elif you_win:
                line2 = "本局你获胜"
            else:
                line2 = "本局你落败"
        else:
            # 机机对战（演示）：同样指明哪一方获胜
            if g.winner is not None:
                line2 = f"{COLOR_NAMES[g.winner]}（{g.players[g.winner].name}）获胜"
            elif g.finished:
                line2 = "本局为平局"
        sub = f"黑方 {g.players[BLACK].name} vs 白方 {g.players[WHITE].name}"
        body_fg = C_TEXT
        if has_human and not you_win and g.winner is not None:
            body_fg = "#E87B6B"          # 战败用暖红
        elif (has_human and you_win) or (not has_human and g.winner is not None):
            body_fg = "#6BD1A6"          # 获胜/有胜方用亮绿

        dlg = OrnateDialog(self, title=title, width=490, height=380,
                           subtitle=sub)
        # 使用默认正文区：自动避开标题带与按钮带的花纹
        dlg.place_body()
        dlg.add_text(result, size=17, fg=body_fg, pady=(8, 4))
        if line2:
            dlg.add_text(line2, size=14, fg=C_ACCENT, pady=(2, 2))
        if g.reason and "认输" in g.reason:
            dlg.add_text(f"（{g.reason}）", size=11, fg=C_TEXT_DIM, pady=(2, 4))

        def _replay():
            dlg.close()
            if ReplayWindow is not None:
                try:
                    ReplayWindow(self, g.to_record(),
                                 title=f"棋谱回放 · {sub}").focus_force()
                except Exception:
                    pass
            else:
                messagebox.showinfo("复盘", "回放组件未就绪，暂不可用。", parent=self)

        def _restart():
            dlg.close()
            self._restart_current()

        def _close():
            dlg.close()

        btns = []
        if ReplayWindow is not None:
            btns.append(dlg.add_button("复盘", _replay, accent=False))
        btns.append(dlg.add_button("重新开始", _restart, accent=True))
        btns.append(dlg.add_button("关闭", _close, accent=False))
        dlg.button_row(btns)
        dlg.open()

    def _restart_current(self):
        """按当前对局的模式/执色/难度/棋种重新开局。"""
        if self.game is None:
            return
        self._start_game(self._last_mode(),
                         self.human_side == BLACK and "black" or "white",
                         self.difficulty, variant=self.variant)

    def _confirm_restart(self):
        if self.game is None:
            return
        if messagebox.askyesno("重新开始", "确定要重新开始本局吗？当前进度将丢失。",
                               parent=self):
            self._restart_current()

    def _last_mode(self):
        if self.game is None:
            return MODE_HUMAN_AI
        k = {self.game.players[BLACK].kind, self.game.players[WHITE].kind}
        if k == {"human"}:
            return MODE_HUMAN_HUMAN
        if k == {"ai"}:
            return MODE_AI_AI
        return MODE_HUMAN_AI

    def _back_to_menu(self):
        self.game = None
        self._show_menu()

    def _on_undo(self):
        if self.game is None or self.game.finished:
            return
        # 人机模式：一次撤销整轮（AI 一步 + 我方一步），回到我方重新行棋；
        # 双人 / AI 互弈：撤一轮。
        kinds = {p.kind for p in self.game.players.values()}
        self.game.undo_round(to_human=("human" in kinds and "ai" in kinds))
        self.selected = []
        self.thinking = False
        self.sound.play("click")
        self._update_info()
        self._refresh_step_ui()
        self._redraw()
        # 悔棋后曲线缩水到当前实际手数（由 _sync_winrate 在下次落子时增量补齐）
        self._wr_y = self._wr_y[: self.game.board.move_count]
        self._draw_winrate()
        # 撤到的可能是 AI 轮（如开局 AI 先行被撤光）——重新调度，人类回合自动跳过
        self._schedule_ai_turn()

    def _on_pass(self):
        """人类只下 1 子后结束本回合（Connect6 允许每轮 1~2 子）。"""
        if self.game is None or self.game.finished or self.thinking:
            return
        cur = self.game.current_player()
        if cur.kind != "human":
            return
        self.selected = []
        self.game.end_round()
        self.sound.play("click")
        self._update_info()
        self._refresh_step_ui()
        self._redraw()
        self._schedule_ai_turn()

    # ---- 设置回调 ----
    def _on_difficulty_change(self, label):
        m = {n: v for n, v in DIFFICULTY_ORDER}
        self.difficulty = m.get(label, "medium")
        self._set_status(f"AI 难度：{label}")

    def _on_theme_change(self, label):
        self.theme_name = label
        self.theme = get_theme(label)
        self._redraw(force=True)

    def _on_bg_change(self, label):
        """切换菜单页 / 游戏页容器主色（C_MAIN/C_MAIN_DARK），并触发重绘。"""
        a, b = BG_PRESET_MAP.get(label, BG_PRESET_MAP[BG_PRESETS[0][0]])
        # 改全局色 + 同步应用到两个容器
        global C_MAIN, C_MAIN_DARK
        old_a, old_b = C_MAIN, C_MAIN_DARK
        C_MAIN = a
        C_MAIN_DARK = b

        def _apply(w, old_bg, new_bg):
            try:
                if w is None:
                    return
                if not w.winfo_exists():
                    return
                cur = None
                try:
                    cur = w.cget("bg")
                except Exception:
                    cur = None
                if cur == old_bg:
                    w.configure(bg=new_bg)
            except Exception:
                pass

        for w in (self.menu_page, self.game_page, self.container,
                  self.menu_canvas, self.board_frame):
            _apply(w, old_a, a)
        # 侧栏与音乐栏是 C_MAIN_DARK
        for w in (self.sidebar,
                  getattr(self, "music_frame", None),
                  getattr(self, "music_label", None),
                  getattr(self, "music_vol", None),
                  getattr(self, "lbl_sel", None)):
            _apply(w, old_b, b)
        # 自绘音量滑杆（VolumeSlider，非 ttk.Scale，无 troughcolor）：
        # 仅同步其 Canvas 底色并触发重绘，让轨道/滑块随新背景融合。
        for vattr in ("music_vol", "gm_vol", "side_vsb"):
            try:
                vs = getattr(self, vattr, None)
                if vs is not None and vs.winfo_exists():
                    vs.configure(bg=b)
                    if hasattr(vs, "recolor"):
                        vs.recolor(b)
                    else:
                        vs._draw()
            except Exception:
                pass

        # 递归遍历 menu_page / game_page 的所有子 widget，
        # 谁原来 bg=old_a 就改成 a；bg=old_b 就改成 b（保证下钻到所有 labels 也生效）
        def _walk(widget):
            try:
                for child in widget.winfo_children():
                    _apply(child, old_a, a)
                    _apply(child, old_b, b)
                    _walk(child)
            except Exception:
                pass
        _walk(self.menu_page)
        _walk(self.game_page)
        _walk(self.container)

        # 自绘控件画布底色同步（MediaButton / VolumeSlider 在构建时把父容器底色
        # 固化成了自己的 Canvas bg，切换背景后必须显式重设，否则四周会露旧色块）
        for mbattr in ("music_mode_btn", "music_next_btn", "music_toggle_btn",
                       "music_prev_btn", "gm_mode_btn", "gm_prev_btn",
                       "gm_play_btn", "gm_next_btn"):
            try:
                mb = getattr(self, mbattr, None)
                if mb is not None and mb.winfo_exists():
                    mb.configure(bg=b)
            except Exception:
                pass

        # 胜率图底色随侧栏变化 → 强制重绘其画布背景与网格
        try:
            wr = getattr(self, "wr_canvas", None)
            if wr is not None and wr.winfo_exists():
                self._draw_winrate()
        except Exception:
            pass

        self._set_status(f"背景色：{label}")
        self._redraw_menu()
        self._redraw(force=True)

    # ---- 音乐控制（切歌前释放设备，修复错乱） ----
    # 播放按钮在 主菜单栏 与 下棋侧栏 各有一份，本类用统一同步使其图标/曲名一致。
    def _music_toggle(self):
        playing = self.music.toggle_play()
        self._sync_music_play_icons(playing)
        self._music_sync_ui()

    def _music_next(self):
        self.music.next()
        self._sync_music_play_icons(self.music.playing)
        self._music_sync_ui()

    def _music_prev(self):
        self.music.prev()
        self._sync_music_play_icons(self.music.playing)
        self._music_sync_ui()

    def _music_mode(self):
        order = [MODE_LOOP, MODE_SINGLE, MODE_SHUFFLE]
        self.music.mode = order[(order.index(self.music.mode) + 1) % 3]
        self._sync_music_mode_text()
        self._set_status(f"播放模式：{MODE_NAMES[self.music.mode]}")

    def _sync_music_play_icons(self, playing: bool):
        icon = "⏸" if playing else "▶"
        for attr in ("music_toggle_btn", "gm_play_btn"):
            w = getattr(self, attr, None)
            if w is not None and w.winfo_exists():
                try:
                    w.set_text(icon)
                except Exception:
                    pass

    def _sync_music_mode_text(self):
        txt = MODE_NAMES[self.music.mode]
        for attr in ("music_mode_btn", "gm_mode_btn"):
            w = getattr(self, attr, None)
            if w is not None and w.winfo_exists():
                try:
                    w.set_text(txt)
                except Exception:
                    pass

    def _music_sync_ui(self):
        cur = self.music.current
        title = cur.get("title", cur.get("name", "")) if cur else "未播放"
        if not title and cur:
            title = cur.get("name", "未播放")
        if not title:
            title = "未播放"
        for attr, is_label in (("music_label", True), ("gm_label", True)):
            w = getattr(self, attr, None)
            if w is not None and w.winfo_exists():
                try:
                    w.config(text=title)
                except Exception:
                    pass
        self._sync_music_play_icons(self.music.playing)
        self._sync_music_mode_text()

    # ---------------------------------------------------------------- 歌单选择
    def _open_playlist(self):
        """打开歌单选择窗：列出全部曲目，点选即播放（开局前挑选背景音乐）。"""
        mp = self.music
        if mp is None or not getattr(mp, "tracks", None):
            self._set_status("歌单为空：请将音乐文件放入 assets/music/")
            return
        old = getattr(self, "_playlist_dlg", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        n = len(mp.tracks)
        dlg = tk.Toplevel(self)
        self._playlist_dlg = dlg
        try:
            dlg.transient(self)
            dlg.grab_set()
        except Exception:
            pass
        dlg.title("背景音乐歌单")
        dlg.configure(bg=C_MAIN)
        dlg.resizable(False, False)
        row_h = 46
        Wd = 380
        Hd = 96 + row_h * n + 24
        dlg.geometry(f"{Wd}x{Hd}")

        tk.Label(dlg, text="背景音乐歌单", bg=C_MAIN, fg=C_ACCENT,
                 font=(FALLBACK_FAMILY, 15, "bold")).pack(pady=(12, 2))
        tk.Label(dlg, text="点选曲目即开始播放", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(pady=(0, 8))

        list_frame = tk.Frame(dlg, bg=C_MAIN)
        list_frame.pack(fill="both", expand=True, padx=18)

        row_btns: list = []
        cur_idx = mp.index % n

        def _pick(idx):
            mp.play_index(idx)
            self._sync_music_play_icons(True)
            self._music_sync_ui()
            self._set_status(f"正在播放：{mp.tracks[idx]['name']}")
            for j, b in enumerate(row_btns):
                on = (j == (mp.index % n))
                try:
                    b._bg = C_CONFIRM if on else "#3A4256"
                    b._fg = "#FFFFFF" if on else C_TEXT
                    b._draw()
                except Exception:
                    pass

        def _make_row(i):
            name = mp.tracks[i]["name"]
            on = (i == cur_idx)
            b = GlowButton(list_frame, text=name, command=lambda idx=i: _pick(idx),
                           width=Wd - 36, height=row_h - 8,
                           bg=(C_CONFIRM if on else "#3A4256"),
                           fg=("#FFFFFF" if on else C_TEXT),
                           font=(FALLBACK_FAMILY, 12, "bold"))
            b.pack(pady=4)
            return b

        row_btns = [_make_row(i) for i in range(n)]

        GlowButton(dlg, "关闭", command=dlg.destroy, width=120, height=38,
                   bg=C_CANCEL, fg=C_TEXT,
                   font=(FALLBACK_FAMILY, 13, "bold")).pack(pady=(8, 14))
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _poll_music(self):
        """主线程音乐 UI 轮询（每 ~0.9s 一次）+ 音效/音频自愈探针。

        音频引擎（music 引擎线程）负责全部 MCI 命令与曲目自动接续；本方法
        只读取引擎缓存的状态刷新按钮图标与曲名，**绝不发送任何 MCI 命令**。
        这是"音频设备异常不冻结界面"的关键——UI 与音频故障彻底隔离。

        自愈探针：若上一次音效投递后长时间没有成功消费（设备被独占/驱动
        异常导致 mciSendStringW 永久阻塞、工作线程卡死并持有全局锁），
        则重建 winmm 锁，让音效与背景音恢复——对应"下到一半没音效"。
        """
        try:
            if self.music:
                st = self.music.poll_state()
                self._music_sync_ui()
                # 图标语义：真正在播显示 ⏸（点击暂停）；暂停/停止显示 ▶（点击播放）
                real_playing = bool(st["playing"] and st["mode"] == "playing")
                self._sync_music_play_icons(real_playing)
            self._sfx_health_check()
        except Exception:
            pass
        finally:
            try:
                self._music_job = self.after(900, self._poll_music)
            except Exception:
                pass

    def _sfx_health_check(self):
        """音效健康探针：队列积压且长期不降 → 判定工作线程卡死并自愈。"""
        sm = getattr(self, "sound", None)
        if sm is None:
            return
        try:
            from . import sounds as _snd
            q = _snd._SFX_QUEUE
            if q is None:
                return
            # 只有"有积压 + 长时间不消费"才恢复，正常播放期间 qsize 恒为 0
            if q.qsize() < _snd._SFX_QUEUE_MAX - 2:
                self._sfx_stall_since = 0
                return
            now = int(time.time() * 10)
            if not getattr(self, "_sfx_stall_since", 0):
                self._sfx_stall_since = now
                return
            if now - self._sfx_stall_since < 30:      # 持续 3 秒积压才动手
                return
            self._sfx_stall_since = 0
            sm.recover()
            # 丢掉积压的旧任务，避免恢复瞬间一串爆音
            while q.qsize():
                try:
                    q.get_nowait()
                except Exception:
                    break
        except Exception:
            pass

    # ---- 启动 PostgreSQL 检测与游戏内询问 ----
    def _maybe_pg_prompt(self):
        """进入主界面后检测一次 PostgreSQL；根据状态用带花纹弹窗询问。
        全部在后台线程做网络/服务探测，绝不在主线程阻塞启动。
        """
        if self._pg_checked or check_status is None:
            self._pg_checked = True
            return
        self._pg_checked = True
        try:
            threading.Thread(target=self._pg_status_worker, daemon=True).start()
            self._pg_wait_job = self.after(120, self._pg_wait_result)
        except Exception:
            pass

    def _pg_status_worker(self):
        try:
            st = check_status()
        except Exception:
            st = None
        try:
            self._pg_queue.put(st)
        except Exception:
            pass

    def _pg_wait_result(self):
        try:
            st = None
            while True:
                try:
                    st = self._pg_queue.get_nowait()
                except queue.Empty:
                    break
            if st is None:
                self._pg_wait_job = self.after(120, self._pg_wait_result)
                return
            self._pg_handle_status(st)
        except Exception:
            pass

    def _pg_handle_status(self, status: str):
        if OrnateDialog is None:
            return
        if self._pg_prompt_shown:
            return
        self._pg_prompt_shown = True

        if status == STATUS_RUNNING:
            # 数据库已就绪：不打断启动，但给出**可见**反馈
            #   ① 状态栏一行字（长期驻留）  ② 轻提示浮层（确保被看到，自动消失）
            self._set_status("数据库已就绪，对局将自动存档")
            self._toast("数据库已就绪", kind="ok",
                        detail="PostgreSQL 运行正常 · 对局将自动存档")
            return

        if status == STATUS_STOPPED:
            dlg = OrnateDialog(self, title="启动数据库服务", width=480, height=390,
                               subtitle="检测到 PostgreSQL 已安装但未运行")
            dlg.place_body()
            dlg.add_status_icon("warn")
            dlg.add_text("已检测到本机安装了 PostgreSQL，但服务当前未启动。\n"
                         "对局战绩需要数据库服务才能保存。", size=13,
                         wraplength=420, pady=10)

            def _start():
                dlg.close()
                svc = first_service() if first_service else None
                ok = start_service(svc) if (svc and start_service) else False
                # 启动后复检一次，给出明确反馈（成功 / 失败都告知用户）
                running = False
                if ok and check_status is not None:
                    try:
                        running = (check_status() == STATUS_RUNNING)
                    except Exception:
                        running = False
                if running:
                    self._set_status("数据库服务已启动")
                    self._info_dialog(
                        "数据库已就绪",
                        "PostgreSQL 服务已成功启动，\n对局战绩将自动存档。",
                        subtitle="PostgreSQL", icon="ok",
                        width=450, height=330)
                else:
                    # 失败通常因缺少管理员权限
                    self._ask_start_pg(
                        "未能自动启动数据库服务（可能需要管理员权限）。\n"
                        "可手动运行生成的启动脚本，或以管理员身份重试。")

            def _skip():
                dlg.close()

            btns = [dlg.add_button("跳过", _skip, accent=False),
                    dlg.add_button("启动服务", _start, accent=True)]
            dlg.button_row(btns)
            dlg.open()
            return

        # STATUS_MISSING / 其它：未检测到安装
        dlg = OrnateDialog(self, title="检测到未安装数据库", width=480, height=400,
                           subtitle="PostgreSQL 未就绪")
        dlg.place_body()
        dlg.add_status_icon("db")
        dlg.add_text("本机暂未检测到 PostgreSQL。\n"
                     "战绩查询与自动存档需要它；纯对弈（不保存）不受影响。",
                     size=13, wraplength=420, pady=10)

        def _install_guide():
            dlg.close()
            self._ask_start_pg(
                "将为你生成安装引导脚本并打开 PostgreSQL 官网下载页。\n"
                "安装完成后请重启本程序。")

        def _skip():
            dlg.close()

        btns = [dlg.add_button("暂不使用", _skip, accent=False),
                dlg.add_button("安装引导", _install_guide, accent=True)]
        dlg.button_row(btns)
        dlg.open()

    def _ask_start_pg(self, msg: str):
        """生成/运行安装引导脚本的二次确认（需要写盘/启动进程前征求用户）。"""
        if OrnateDialog is None:
            messagebox.showwarning("PostgreSQL", msg, parent=self)
            return
        dlg = OrnateDialog(self, title="PostgreSQL 引导", width=460, height=370,
                           subtitle="需要你确认")
        dlg.place_body()
        dlg.add_status_icon("info")
        dlg.add_text(msg, size=13, wraplength=400, pady=10)

        def _go():
            dlg.close()
            try:
                if generate_install_bat:
                    bat = generate_install_bat(data_dir())
                    os.startfile(bat)          # noqa: S606 用户确认后的本机引导
            except Exception as exc:
                try:
                    import webbrowser
                    webbrowser.open("https://www.postgresql.org/download/windows/")
                except Exception:
                    pass
                self._set_status(f"数据库引导失败：{exc}")

        def _cancel():
            dlg.close()

        dlg.button_row([dlg.add_button("取消", _cancel, accent=False),
                        dlg.add_button("生成并打开引导", _go, accent=True)])
        dlg.open()

    # ---- 信息窗口（游戏内自绘弹窗，替代系统 messagebox） ----
    def _info_dialog(self, title: str, message: str, subtitle: str = "",
                     icon: str = "info", mono: bool = False, size: int = 13,
                     width: int = 470, height: int = 340):
        """游戏内自绘信息弹窗；自绘组件缺失时回退系统 messagebox。"""
        if OrnateDialog is None:
            messagebox.showinfo(title, message, parent=self)
            return None
        dlg = OrnateDialog(self, title=title, width=width, height=height,
                           subtitle=subtitle)
        dlg.place_body()
        try:
            if icon:
                dlg.add_status_icon(icon)
        except Exception:
            pass
        dlg.add_text(message, size=size, wraplength=width - 100, pady=8,
                     mono=mono)
        dlg.button_row([dlg.add_button("知道了", dlg.close, accent=True)])
        dlg.open()
        return dlg

    def _show_stats(self):
        if Database is None:
            self._info_dialog("战绩查询",
                              "未连接数据库，战绩功能暂不可用。\n请先配置 PostgreSQL。",
                              subtitle="需要数据库", icon="db",
                              width=470, height=350)
            return
        try:
            db = Database(); db.connect()
            stats = db.get_stats()
            db.close()
            lines = ["棋手          胜  负  平", "----------------------"]
            for s in stats:
                lines.append(f"{s.get('name','?'):<8}  {s.get('wins',0):>2}  "
                             f"{s.get('losses',0):>2}  {s.get('draws',0):>2}")
            body = "\n".join(lines) if stats else "暂无战绩记录。"
            self._info_dialog("战绩统计", body, subtitle="PostgreSQL",
                              icon="ok", mono=True, width=540, height=400)
        except Exception as exc:
            self._info_dialog("战绩查询", f"查询失败：{exc}",
                              subtitle="PostgreSQL", icon="warn",
                              width=490, height=350)

    def _open_tutorial(self):
        text = (f"{APP_NAME} 规则说明\n\n"
                "本程序收录三种经典棋，规则与玩法如下：\n\n"
                "【六子棋 Connect6】\n"
                "· 19×19 棋盘，黑先，第一手下 1 子；\n"
                "· 之后双方每轮下 1 或 2 子；\n"
                "· 横、竖、斜任一方向连成 6 子即获胜。\n\n"
                "【五子棋 Gomoku】\n"
                "· 15×15 棋盘，黑先，双方每轮各下 1 子；\n"
                "· 横、竖、斜任一方向连成 5 子即获胜；\n"
                "· AI 难度分简单 / 中等 / 困难三档，\n"
                "  「困难」启用完整算杀引擎。\n\n"
                "【中国象棋 Xiangqi】\n"
                "· 9×10 棋盘，红先，双方轮流行棋；\n"
                "· 车走直线、马走日（蹩腿）、象走田（塞眼）、\n"
                "  士走斜、将走宫、炮隔子吃、兵过河可平移；\n"
                "· 将帅不可照面；将死或困毙（无着可走）即负；\n"
                "· 本版为人人对战，后续版本将加入 AI。\n\n"
                "落子操作：六子棋 / 五子棋先在棋盘点击选位\n"
                "（虚线预览），再点右侧「确认落子」正式落子；\n"
                "象棋则先点选己方棋子，再点高亮处落子。")
        self._info_dialog("规则说明", text, subtitle=APP_NAME,
                          icon="info", width=540, height=480)

    def _open_about(self):
        self._info_dialog(
            "关于",
            f"{APP_NAME}\n六子棋 · 五子棋 · 中国象棋 经典对弈\n\n"
            "连珠棋 AI：Alpha-Beta 剪枝 + 置换表 + 迭代加深 + 算杀(VCF/VCT)\n"
            "中国象棋：完整规则引擎（人人对战）",
            subtitle=APP_NAME, icon="info", width=520, height=340)

    # ---- 关闭 / 工具 ----
    def _center_window(self, wnd, w, h):
        try:
            sw = wnd.winfo_screenwidth(); sh = wnd.winfo_screenheight()
            x = (sw - w) // 2; y = (sh - h) // 2
            wnd.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _on_close(self):
        """关闭窗口：释放可能泄漏的模态 grab、销毁残留弹窗、停掉音乐，再销毁。

        关键修复：若某个 OrnateDialog 因异常导致 grab 泄漏（看不见却仍
        抢输入），主窗口的 X 会失效（表现为"关不掉"）。这里无论何种情况都
        先释放 grab、清掉子弹窗，并启动一条独立守护线程在 1 秒后强制退出，
        保证"关不掉"永远不会发生（不依赖主事件循环是否畅通）。
        """
        # 1) 释放可能泄漏的模态 grab（幽灵弹窗会冻结主窗口、使 X 失效）
        try:
            cur = self.grab_current()
            if cur is not None:
                try:
                    cur.grab_release()
                except Exception:
                    pass
        except Exception:
            pass
        # 2) 销毁任何残留的子弹窗（防止孤立 Toplevel 持 grab）
        #    注意：不要用 self.toplevels() —— 该 API 在部分 Python/tkinter 版本
        #    上并不存在于 Tk 实例，会抛 AttributeError 而被吞掉，导致这一步
        #    形同虚设（孤立模态窗继续持 grab → 主窗口"关不掉"）。这里自己沿
        #    控件树枚举 Toplevel，保证一定生效。
        try:
            found = []
            stack = [self]
            while stack:
                node = stack.pop()
                try:
                    kids = node.winfo_children()
                except Exception:
                    continue
                for ch in kids:
                    if isinstance(ch, tk.Toplevel):
                        found.append(ch)
                    stack.append(ch)
            for tl in found:
                try:
                    tl.grab_release()
                except Exception:
                    pass
                try:
                    tl.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        # 3) 取消挂起任务
        for job_attr in ("_music_job", "_timer_job", "_pg_wait_job", "_bg_job",
                         "_menu_anim_job", "_menu_redraw_job"):
            job = getattr(self, job_attr, None)
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                try:
                    setattr(self, job_attr, None)
                except Exception:
                    pass
        # 3.5) 关闭轻提示浮层（连同其滑入/淡出动画任务）
        try:
            self._toast_close()
        except Exception:
            pass
        # 4) 停止音乐（非阻塞投递）
        try:
            if self.music:
                self.music.stop()
        except Exception:
            pass
        try:
            self.sound.play("click")
        except Exception:
            pass
        # 5) 销毁主窗口
        try:
            self.destroy()
        except Exception:
            pass
        # 6) 兜底：独立守护线程 1 秒后强制结束进程，确保无论如何都能退出。
        #    若 destroy() 已正常退出主循环，进程随主线程结束，此线程随之消亡。
        try:
            def _hard_exit():
                try:
                    import time as _t
                    _t.sleep(1.0)
                    os._exit(0)
                except Exception:
                    pass
            threading.Thread(target=_hard_exit, daemon=True).start()
        except Exception:
            try:
                os._exit(0)
            except Exception:
                pass


def _install_freeze_watchdog(gui):
    """主线程卡死诊断看门狗（诊断用，开销极低，不影响正常对局）。

    机理：主线程事件循环由 Tk 的 after 每 1s 打一次"心跳"；若主线程
    停摆超过 4s（陷入无限循环/死锁，而非正常计算），后台线程用
    faulthandler 把**全部线程堆栈**写入项目根目录 freeze_dump.log，
    据此可精确定位卡死点。另启用 faulthandler 兜底并每 45s 做一次
    C 级定时快照，覆盖部分极端场景。
    """
    try:
        import faulthandler
        log_path = os.path.join(logs_dir(), "freeze_dump.log")
        fh = open(log_path, "a", encoding="utf-8")
        fh.write("\n===== 六子棋 主线程看门狗已启用 =====\n")
        fh.flush()
        faulthandler.enable(file=fh)
        # 兜底：仅当主线程被 C 级死锁（长时间持有 GIL，_watch 线程无法被调度）
        # 时仍能周期性落一份快照。取较长间隔避免正常对局时刷屏。
        try:
            faulthandler.dump_traceback_later(120, repeat=True, exit=False, file=fh)
        except Exception:
            pass

        last = [time.monotonic()]

        def _beat():
            last[0] = time.monotonic()
            try:
                gui.after(1000, _beat)
            except Exception:
                pass

        def _watch():
            while True:
                time.sleep(1)
                gap = time.monotonic() - last[0]
                if gap > 4.0:
                    try:
                        fh.write("\n===== 检测到主线程停摆 %.0f 秒，全部线程堆栈 =====\n" % gap)
                        # 额外记录模态 grab 与顶层窗口：grab 泄漏会冻结主窗口
                        # 且看门狗难以察觉（grab 不阻塞 Tk 事件循环）。
                        try:
                            g = gui.grab_current()
                            fh.write("grab_current: %r\n" % (g,))
                        except Exception:
                            fh.write("grab_current: <unavailable>\n")
                        try:
                            tls = gui.toplevels()
                            fh.write("toplevels(%d): %s\n"
                                     % (len(tls), [str(t) for t in tls]))
                        except Exception:
                            pass
                        fh.flush()
                        faulthandler.dump_traceback(file=fh, all_threads=True)
                        fh.flush()
                    except Exception:
                        pass
                    last[0] = time.monotonic()

        try:
            gui.after(1000, _beat)
        except Exception:
            pass
        threading.Thread(target=_watch, daemon=True).start()
    except Exception:
        pass


def run():
    """GUI 入口（由 main.py 调用）。"""
    _enable_dpi_awareness()
    gui = Connect6GUI()
    _install_freeze_watchdog(gui)
    gui.mainloop()
