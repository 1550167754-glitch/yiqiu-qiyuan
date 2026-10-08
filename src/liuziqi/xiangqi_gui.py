# -*- coding: utf-8 -*-
"""
xiangqi_gui.py —— 中国象棋图形界面（集成进「弈趣棋苑」启动器）

渲染架构（v3，支持 144Hz 动画）：
    - 静态资源一次性预渲染为 PhotoImage 精灵：木纹底板（单一木色，无上下割裂）、
      14 种立体棋子（薄侧壁/盘面球面渐变 + 倒角明暗弧 + 镜面高光 + 底部反光 + 阴刻艺术字）、
      静止/抬起两档柔影、金环（选中随棋联动）/虚线蓝环（上一步）/红圈（可吃）/
      精致落点（可走）高亮；
    - 运行期只做画布项坐标移动（零 PIL 重绘），动效按 7ms 步长（≈144Hz）调度，
      并 timeBeginPeriod(1) 提升 Windows 定时器分辨率，插值基于真实时间；
    - 抬棋：点选己方棋子平滑升起，选中环随棋子同步上移（视觉不分离）；
      落棋：抛物线弧 travel + 落地回弹；
    - 吃子：被吃子沿撞击方向滑出消失 + 冲击光环扩散 + 全盘衰减震动（配合落子音效）；
    - 将军：被将方帅/将位置脉冲红环 + 全盘暗角探照警示过渡动画；
    - 棋子字形用打包的毛笔楷书艺术字体（缺字自动回退系统雅黑），河界文字同理。
"""

from __future__ import annotations

import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.ttk as ttk

from .xiangqi import (XiangqiBoard, RED, BLACK, PIECE_CHAR, COLOR_CN)
from .xiangqi_theme import THEME_NAMES, get_theme, DEFAULT_THEME, mix_hex
from .xiangqi_pieces import (PIECE_STYLES, STYLE_NAMES, DEFAULT_STYLE,
                            render_piece)

try:
    from .pikafish_engine import DIFFICULTY_PRESETS
except Exception:
    DIFFICULTY_PRESETS = {"easy": (3, 6), "medium": (12, 10), "hard": (20, 14)}

try:
    from .theme_boards import blend
except Exception:
    def blend(c1, c2, ratio):
        a, b = _hex(c1), _hex(c2)
        return "#%02X%02X%02X" % _mix(a, b, ratio)

try:
    from .gui import ThinScrollbar
except Exception:
    ThinScrollbar = None

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    _HAVE_PIL = True
except Exception:  # pragma: no cover
    _HAVE_PIL = False

try:
    from .sounds import SoundManager
except Exception:
    SoundManager = None

# ---- 主题色（与弈趣棋苑一致，独立内置以免强依赖 gui 模块） ----
C_MAIN = "#1F2430"
C_MAIN_DARK = "#171B24"
C_PANEL_BG = "#262C3A"
C_PANEL_BORDER = "#353D4F"
C_TEXT = "#EDEFF4"
C_TEXT_DIM = "#9AA3B2"
C_ACCENT = "#E8B34B"
C_ACCENT_DARK = "#C9972F"
C_GLOW = "#FFD98A"
C_DARK_BTN = "#3A4256"
FALLBACK_FAMILY = "Microsoft YaHei UI"

# 棋盘/棋子缺省配色（真实用色随主题走，见 xiangqi_theme.py 与 self._theme）
BOARD_BG = "#E9C189"
LINE = "#5A3D1E"
LINE_SOFT = "#7A5A2E"
RIVER_TXT = "#8A6A30"
SEL_RING = "#E8B34B"
LAST_DOT = "#3E7CB1"
CAP_RING = "#C0392B"
MOVE_DOT = "#2E8B57"
IMPACT_RING = "#FFE9B0"
CHECK_RING = "#E23B2E"   # 将军警示（脉冲红环）

# ---- 棋子配色（素色木片风格：浅木面 + 细深描边 + 纯色字） ----
RING_COL = {RED: "#B3271E", BLACK: "#1C1C1C"}     # 字色（红=朱红 / 黑=墨黑）
PIECE_FACE_TOP = "#FBF3E2"                        # 盘面上缘（亮奶油木色）
PIECE_FACE_BOT = "#F0E1C0"                        # 盘面下缘（略深）
PIECE_EDGE = "#A8763C"                            # 棋子描边（深棕细线）
SHADOW_RGB = (48, 34, 16)                         # 落在棋盘上的投影色

# 设计基准（96 DPI 像素），实际按 DPI 缩放
BASE_CELL = 58
BASE_MARGIN = 38
BASE_PANEL_W = 336     # 侧栏宽度（与五子棋/六子棋 sidebar 一致）
SS = 4          # 底板/精灵均为一次性预渲染，可承受 4× 超采样
# 艺术字体优先级：方正舒体繁简全覆盖且书法感最强，优先；
# 马善政/小薇只覆盖简体（缺「漢」「車馬將砲」），仅作补充。
_ART_FONTS = ("MaShanZheng.ttf", "ZCOOLXiaoWei.ttf")
# 系统书法字体（繁简全覆盖）：方正舒体 > 华文楷体 > 隶书
_ART_SYS_FONTS = ("FZSTK.TTF", "STKAITI.TTF", "SIMLI.TTF")
# 系统书法体的 family 名（供 Tk Label 使用，需先私有注册）
_ART_SYS_FAMILY = {"FZSTK.TTF": "FZShuTi", "STKAITI.TTF": "STKaiti",
                   "SIMLI.TTF": "LiSu"}

# 动画节奏（毫秒；调度步长 7ms ≈ 144Hz）
T_LIFT, T_SETTLE, T_TRAVEL, T_LAND = 130, 120, 250, 90
T_KNOCK, T_IMPACT, T_SHAKE = 150, 200, 170
LIFT_H = 0.30        # 抬起高度（× cell）
ARC_H = 0.52         # travel 弧顶（× cell）
FRAME_MS = 7         # 动画调度步长（≈144Hz）


def _hex(c):
    """#RRGGBB → (r,g,b)；也接受已是 (r,g,b) 元组（主题里落影色即为元组）。"""
    if isinstance(c, (tuple, list)):
        return tuple(int(v) for v in c[:3])
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def _ease_in_out(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _vbar(d, cx, cy, r, c_top, c_bot, steps=48):
    """竖向线性渐变实心圆（自上而下 c_top → c_bot），逐行扫描实现。

    比逐层同心圆更贴近"平涂木片"观感：上缘略亮、下缘略暗，
    且不会出现球面渐变那种中心亮点。
    """
    n = max(2, steps)
    for i in range(n):
        t = i / (n - 1)
        yy = cy - r + 2 * r * t
        half = (r * r - (yy - cy) ** 2) ** 0.5
        if half.__class__ is complex or half <= 0:   # 边界浮点误差会产生复数
            continue
        d.line([cx - half, yy, cx + half, yy], fill=_mix(c_top, c_bot, t))


def _covers(ft, ch: str) -> bool:
    """字形覆盖检测：与私有区 notdef(\\uE000) 的 bbox 对比。"""
    try:
        return ft.getbbox(ch) != ft.getbbox("\uE000")
    except Exception:
        return True


_TTF_CACHE: dict = {}


def _load_ttf(path: str, size: int):
    """PIL TrueType 字体加载（进程级缓存；失败返回 None 由调用方走回退链）。"""
    key = (path, size)
    if key in _TTF_CACHE:
        return _TTF_CACHE[key]
    try:
        ft = ImageFont.truetype(path, size)
    except Exception:
        ft = None
    _TTF_CACHE[key] = ft
    return ft


def _register_calligraphy():
    """把书法字体经 GDI 私有注册（FR_PRIVATE），返回可用 family 名。

    Tk 的 Label/Button 只能按 family 名取字体，故界面标题要用书法效果，
    必须先 AddFontResourceExW 私有注册（不污染系统字体表）。
    失败返回空串，调用方回退雅黑。
    """
    if not sys.platform.startswith("win"):
        return ""
    try:
        import ctypes
        import ctypes.wintypes
        gdi32 = ctypes.windll.gdi32
        gdi32.AddFontResourceExW.restype = ctypes.c_int
        gdi32.AddFontResourceExW.argtypes = [
            ctypes.wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_void_p]
        for fn in _ART_SYS_FONTS:
            p = os.path.join(r"C:/Windows/Fonts", fn)
            if os.path.exists(p) and gdi32.AddFontResourceExW(p, 0x10, 0) > 0:
                return _ART_SYS_FAMILY.get(fn, "")
        return ""
    except Exception:
        return ""


def _resolve_ttf_paths():
    """候选字体：系统书法体（方正舒体等，繁简全）→ 打包毛笔体 → 系统雅黑/宋体。

    铁坑：马善政/志莽行书等毛笔体**缺繁体字形**（車馬將砲/漢），
    用它们画红方繁体字会渲成豆腐块，故繁简字体必须排在前面。
    """
    cands = []
    sysdir = r"C:/Windows/Fonts"
    for fn in _ART_SYS_FONTS:
        p = os.path.join(sysdir, fn)
        if os.path.exists(p):
            cands.append(("art", p))
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for fn in _ART_FONTS:
        p = os.path.join(base, "assets", "fonts", fn)
        if os.path.exists(p):
            cands.append(("art2", p))
    for fn in ("msyh.ttc", "simsun.ttc", "simhei.ttf"):
        p = os.path.join(sysdir, fn)
        if os.path.exists(p):
            cands.append(("base", p))
    return cands


class XiangqiApp(tk.Toplevel):
    """中国象棋对弈窗口（人人可玩，含抬棋/落棋/吃子动效）。"""

    def __init__(self, master=None, mode="pve", difficulty="medium"):
        """mode: pvp（双人对弈）/ pve（人机，AI 执黑）/ aia（皮卡鱼互弈观战）
        difficulty: easy / medium / hard（皮卡鱼三档）"""
        super().__init__(master)
        self.title("中国象棋 · 弈趣棋苑")
        try:
            self.configure(bg=C_MAIN)
        except Exception:
            pass

        try:
            s = float(self.tk.call("tk", "scaling")) / 1.3333
        except Exception:
            s = 1.0
        self._dpi = max(1.0, min(s, 1.8))
        self.cell = int(round(BASE_CELL * self._dpi))
        self.margin = int(round(BASE_MARGIN * self._dpi))
        self.bw = self.margin * 2 + 8 * self.cell
        self.bh = self.margin * 2 + 9 * self.cell
        # 侧栏宽度与五子棋/六子棋 sidebar 一致：336 物理像素，不随 DPI 放大
        self.panel_w = BASE_PANEL_W
        self.r_piece = self.cell * 0.44

        self.board = XiangqiBoard()
        self.selected = None
        self.targets = []
        self._legal = []
        self.last_move = None
        self._busy = False
        self._ready = False
        self._piece_items = {}
        self._lift_id = None
        self._lift_h = 0.0
        self._sel_id = None        # 选中环独立画布项（随棋子联动）
        self._check_id = None      # 将军警示环画布项
        self._check_dim = None     # 将军暗角矩形画布项
        self._travel = None

        # ---- 人机对战（皮卡鱼 NNUE）状态 ----
        self.mode_var = tk.StringVar(value=mode if mode in
                                     ("pvp", "pve", "aia") else "pve")
        self.diff_var = tk.StringVar(value=difficulty if difficulty in
                                     ("easy", "medium", "hard") else "medium")
        self._init_mode = self.mode_var.get()   # 启动时按初始模式准备引擎
        # ---- 书法字体（GDI 私有注册，供标题/装饰文字使用） ----
        self._calli = _register_calligraphy() or FALLBACK_FAMILY
        # ---- 棋盘配色（5 套） ----
        self.theme_name = DEFAULT_THEME
        self._theme = get_theme(self.theme_name)
        # ---- 棋子材质（5 种实心木质工艺，与棋盘配色独立可组合） ----
        self.piece_style = DEFAULT_STYLE
        self.engine = None            # PikafishEngine，懒加载
        self._engine_state = "idle"   # idle / loading / ready / failed
        self._engine_kind = None      # 引擎类别：pikafish / ds（两引擎不共用 state）
        self._loading_kind = None     # 正在加载的引擎类别（丢弃过期加载结果用）
        self._ai_busy = False
        self._ai_queue: "queue.Queue" = queue.Queue()
        self._ai_job = None
        # 胜率曲线数据：逐点记录黑视角评估分(cp)，显示时再换算+平滑
        self._wr_cp: list[float] = []
        self._wr_src: list[str] = []      # mat=子力分 / eng=引擎分 / end=终局
        self._wr_y: list[float] = []      # 平滑后的显示序列（_winrate_series 产出）

        self._build()
        self._bump_timer_resolution()
        self._update_status("正在准备棋盘…")
        self.after(30, self._init_and_start)
        self._fit_to_desktop()
        self._resize_job = None
        self.bind("<Configure>", self._on_resize, add="+")
        self._relayout_lock = False
        self.bind("<Destroy>", self._on_destroy, add="+")

    # ------------------------------------------------------- 全屏自适应
    def _fit_to_desktop(self):
        """与五子棋/六子棋启动器一致的窗口几何：按桌面尺寸适配，可缩放。"""
        try:
            self.update_idletasks()
            d_w = self.winfo_screenwidth()
            d_h = self.winfo_screenheight()
        except Exception:
            d_w, d_h = 1280, 800
        avail_w, avail_h = max(320, d_w - 8), max(240, d_h - 56)
        win_w = min(1240, avail_w)
        win_h = min(820, avail_h)
        min_w = min(640, d_w)
        min_h = min(520, avail_h)
        win_w = max(win_w, min_w)
        win_h = max(win_h, min_h)
        try:
            self.geometry(f"{win_w}x{win_h}")
            self.minsize(min_w, min_h)
            self.resizable(True, True)
        except Exception:
            pass

    def _on_resize(self, _ev=None):
        if _ev is not None and getattr(_ev, "widget", None) is not self:
            return
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(180, self._relayout)

    def _relayout(self):
        """窗口尺寸落定后重算棋盘几何并一次性重建全部精灵（零 PIL 常驻重绘不变）。"""
        self._resize_job = None
        if not self._ready or self._relayout_lock:
            return
        try:
            avail_w = max(420, self.winfo_width() - self.panel_w - 74)
            avail_h = max(460, self.winfo_height() - 60)
            cell = min(int((avail_w - 2 * BASE_MARGIN) / 8),
                       int((avail_h - 2 * BASE_MARGIN) / 9))
            cell = max(38, min(cell, 150))
            if cell == self.cell:
                return
            self._relayout_lock = True
            self.cell = cell
            self.margin = int(round(cell * BASE_MARGIN / BASE_CELL))
            self.bw = self.margin * 2 + 8 * self.cell
            self.bh = self.margin * 2 + 9 * self.cell
            self.r_piece = self.cell * 0.44
            # 取消交互态，重建全部静态资源
            self.selected = None
            self.targets = []
            self._lift_id = None
            self._lift_h = 0.0
            self._clear_selring()
            self._clear_check_anim()
            self._font_cache.clear()
            self._board_photo = self._make_board_photo()
            self._sprites = {key: self._make_piece_sprite(key[0], key[1])
                             for key in PIECE_CHAR}
            self._sh_rest = self._make_shadow_sprite(lift=False)
            self._sh_lift = self._make_shadow_sprite(lift=True)
            self._sp_sel = self._make_ring_sprite(SEL_RING, 0.48, 0.062, glow=True)
            self._sp_cap = self._make_ring_sprite(CAP_RING, 0.50, 0.070, glow=True)
            self._sp_last = self._make_dash_ring_sprite(LAST_DOT)
            self._sp_check = self._make_check_ring_sprite()
            self._sp_dot = self._make_dot_sprite()
            self.canvas.config(width=self.bw, height=self.bh)
            self.canvas.delete("all")
            self._place_board()
            self._rebuild_pieces()
            self._refresh_under()
        except Exception:
            pass
        finally:
            self._relayout_lock = False

    # ------------------------------------------------------- 定时器精度
    def _bump_timer_resolution(self):
        """timeBeginPeriod(1)：把 Windows 定时器精度从 ~15.6ms 提到 1ms，
        让 after(8) 真正按 ~8ms 触发（≈120fps 调度）。"""
        self._tp_ok = False
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
            self._tp_ok = True
        except Exception:
            self._tp_ok = False

    def _restore_timer_resolution(self):
        if getattr(self, "_tp_ok", False):
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
            self._tp_ok = False

    def _on_destroy(self, e=None):
        if e is not None and getattr(e, "widget", None) is not self:
            return
        self._closing = True
        self._restore_timer_resolution()
        # 停止音乐 UI 轮询；自建播放器才回收（共享的主控播放器不能关）
        job = getattr(self, "_music_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._music_job = None
        if getattr(self, "_mp_own", False):
            try:
                self._mp.shutdown()
            except Exception:
                pass
            self._mp = None
        # 恢复全局滚轮绑定（避免覆盖五子棋/六子棋主窗的同名绑定）
        try:
            prev = getattr(self, "_prev_wheel_bind", None)
            if prev is not None:
                self.tk.call("bind", "all", "<MouseWheel>", prev)
        except Exception:
            pass
        eng = getattr(self, "engine", None)
        if eng is not None:
            try:
                eng.close()
            except Exception:
                pass
            self.engine = None

    # ---------------------------------------------------------- 界面骨架
    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, width=self.bw, height=self.bh,
                                bg=BOARD_BG, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, padx=14, pady=14)  # 无 sticky：随窗口居中
        self.canvas.bind("<Button-1>", self._on_click)

        # ---- 右侧栏（照五子棋/六子棋 sidebar：固定宽 + 滚动容器 + 自绘滚动条）----
        self.grid_columnconfigure(1, weight=0, minsize=self.panel_w)
        self.sidebar = tk.Frame(self, bg=C_MAIN_DARK, width=self.panel_w)
        self.sidebar.grid(row=0, column=1, sticky="ns")
        self.sidebar.grid_propagate(False)

        self.side_canvas = tk.Canvas(self.sidebar, bg=C_MAIN_DARK,
                                     highlightthickness=0, bd=0,
                                     width=self.panel_w - 14,
                                     yscrollincrement=1)
        self.side_canvas.pack(side="left", fill="both", expand=True)
        if ThinScrollbar is not None:
            self.side_vsb = ThinScrollbar(self.sidebar,
                                          command=self.side_canvas.yview,
                                          width=12, bg=C_MAIN_DARK)
            self.side_vsb.place(relx=1.0, rely=0.0, relheight=1.0, width=12,
                                anchor="ne")
            self.side_canvas.configure(yscrollcommand=self.side_vsb.set)

        self.side_inner = tk.Frame(self.side_canvas, bg=C_MAIN_DARK,
                                   width=self.panel_w - 14)
        self._side_win = self.side_canvas.create_window(
            (0, 0), window=self.side_inner, anchor="nw",
            width=self.panel_w - 14)
        self.side_inner.bind("<Configure>", lambda e: self._side_update_scroll())
        self.side_canvas.bind("<Configure>", lambda e: self._side_update_scroll())
        self.side_canvas.bind("<MouseWheel>", self._side_on_wheel)
        self._side_wheel_remain = 0
        self._side_wheel_after = None
        # 全局滚轮兜底（悬停侧栏子控件也能滚）；保存旧脚本，销毁时恢复，
        # 避免覆盖五子棋/六子棋主窗的同名全局绑定
        try:
            self._prev_wheel_bind = str(self.tk.call("bind", "all", "<MouseWheel>"))
        except Exception:
            self._prev_wheel_bind = ""
        self.bind_all("<MouseWheel>", self._side_on_wheel_all)

        inner = self.side_inner
        tk.Label(inner, text="对局控制", bg=C_MAIN_DARK, fg=C_TEXT,
                 font=(FALLBACK_FAMILY, 15, "bold")).pack(pady=(12, 2))

        # 双方信息 + 状态
        self.lbl_red = tk.Label(inner, text="红方：玩家（先行）", bg=C_MAIN_DARK,
                                fg=C_TEXT, font=(FALLBACK_FAMILY, 12), anchor="w")
        self.lbl_red.pack(fill="x", padx=18, pady=2)
        self.lbl_black = tk.Label(inner, text="黑方：玩家", bg=C_MAIN_DARK,
                                  fg=C_TEXT, font=(FALLBACK_FAMILY, 12), anchor="w")
        self.lbl_black.pack(fill="x", padx=18, pady=2)
        self.lbl_status = tk.Label(inner, text="准备对局", bg=C_MAIN_DARK,
                                   fg=C_ACCENT, font=(FALLBACK_FAMILY, 12, "bold"),
                                   anchor="w", wraplength=self.panel_w - 44)
        self.lbl_status.pack(fill="x", padx=18, pady=(4, 1))
        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)

        # 对局模式：人人 / 人机 / 机机（皮卡鱼互弈）
        tk.Label(inner, text="对局模式", bg=C_MAIN_DARK, fg=C_TEXT_DIM,
                 font=(self._calli, 12)).pack(anchor="w", padx=18)
        for val, txt in (("pvp", "双人对弈"),
                         ("pve", "人机对战（AI 执黑）"),
                         ("aia", "机机对战 · 皮卡鱼互弈（中等）")):
            tk.Radiobutton(inner, text=txt, variable=self.mode_var,
                           value=val, command=self._on_mode_change,
                           bg=C_MAIN_DARK, fg=C_TEXT, selectcolor="#3A4256",
                           activebackground=C_MAIN_DARK, activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11),
                           highlightthickness=0, bd=0).pack(anchor="w", padx=26)
        tk.Label(inner, text="AI 难度（皮卡鱼 · NNUE）", bg=C_MAIN_DARK,
                 fg=C_TEXT_DIM, font=(self._calli, 12)).pack(
            anchor="w", padx=18, pady=(6, 0))
        # 外观设置：棋盘配色（5 套）与棋子材质（5 种）两个独立维度，可自由组合
        tk.Label(inner, text="棋盘配色", bg=C_MAIN_DARK, fg=C_TEXT_DIM,
                 font=(self._calli, 12)).pack(anchor="w", padx=18,
                                                   pady=(10, 4))
        theme_row = tk.Frame(inner, bg=C_MAIN_DARK)
        theme_row.pack(fill="x", padx=18)
        self._var_theme = tk.StringVar(value=self.theme_name)
        self.cmb_theme = ttk.Combobox(
            theme_row, textvariable=self._var_theme, values=list(THEME_NAMES),
            state="readonly", font=(FALLBACK_FAMILY, 11), width=16)
        self.cmb_theme.pack(side="left", pady=(0, 2))
        self.cmb_theme.bind("<<ComboboxSelected>>",
                            lambda e: self._on_theme_change(self._var_theme.get()))

        tk.Label(inner, text="棋子材质", bg=C_MAIN_DARK, fg=C_TEXT_DIM,
                 font=(self._calli, 12)).pack(anchor="w", padx=18,
                                                   pady=(8, 4))
        style_row = tk.Frame(inner, bg=C_MAIN_DARK)
        style_row.pack(fill="x", padx=18)
        self._var_style = tk.StringVar(value=self.piece_style)
        self.cmb_style = ttk.Combobox(
            style_row, textvariable=self._var_style, values=list(STYLE_NAMES),
            state="readonly", font=(FALLBACK_FAMILY, 11), width=16)
        self.cmb_style.pack(side="left", pady=(0, 2))
        self.cmb_style.bind("<<ComboboxSelected>>",
                            lambda e: self._on_piece_style(self._var_style.get()))

        diff_row = tk.Frame(inner, bg=C_MAIN_DARK)
        diff_row.pack(anchor="w", padx=26, pady=(0, 4))
        for val, txt in (("easy", "简单"), ("medium", "中等"), ("hard", "困难")):
            tk.Radiobutton(diff_row, text=txt, variable=self.diff_var,
                           value=val, command=self._on_diff_change,
                           bg=C_MAIN_DARK, fg=C_TEXT, selectcolor="#3A4256",
                           activebackground=C_MAIN_DARK, activeforeground=C_TEXT,
                           font=(FALLBACK_FAMILY, 11),
                           highlightthickness=0, bd=0).pack(side="left", padx=(0, 8))
        tip = ("操作：点选己方棋子（棋子与选中环一同抬起），\n"
               "再点高亮处即走子；吃子有震动反馈。\n"
               "圆环为可走、红圈为可吃、虚线为上一手。")
        tk.Label(inner, text=tip, bg=C_MAIN_DARK, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11), justify="left",
                 wraplength=self.panel_w - 44).pack(
            anchor="w", padx=18, pady=(2, 2))

        # 胜率曲线（黑方胜率随手数走势，与五子棋/六子棋一致）
        self._build_winrate()

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)

        # 背景音乐（与五子棋侧栏同一套组件/交互：歌单 + 上下首 + 播放 + 音量）
        self._build_music_panel(inner)

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)

        # 操作按钮
        btn_w = self.panel_w - 40
        self.btn_undo = self._mk_button(inner, "悔棋", self._on_undo,
                                        accent=False, width=btn_w)
        self.btn_restart = self._mk_button(inner, "重新开始", self._on_restart,
                                           accent=False, width=btn_w)
        self.btn_back = self._mk_button(inner, "返回菜单", self._on_back,
                                        accent=True, width=btn_w)

        tk.Label(inner, text="弈趣棋苑 · 象棋模块", bg=C_MAIN_DARK,
                 fg=C_TEXT_DIM, font=(FALLBACK_FAMILY, 10)).pack(
            side="bottom", anchor="w", padx=18, pady=(0, 6))

    def _mk_button(self, parent, text, cmd, accent, width=None):
        bw = width or (self.panel_w - 40)
        try:
            from .gui import GlowButton
            btn = GlowButton(parent, text, command=cmd, width=bw, height=42,
                             bg=(C_ACCENT if accent else C_DARK_BTN),
                             fg=("#1F2430" if accent else C_TEXT),
                             font=(FALLBACK_FAMILY, 13, "bold"))
        except Exception:
            btn = tk.Button(parent, text=text, command=cmd,
                            bg=(C_ACCENT if accent else C_DARK_BTN),
                            fg=("#1F2430" if accent else C_TEXT),
                            font=(FALLBACK_FAMILY, 13, "bold"),
                            relief="flat", height=2)
        btn.pack(pady=4)
        return btn

    # ---- 背景音乐（与五子棋侧栏同款：MediaButton + VolumeSlider + 歌单窗）----
    def _music_engine(self):
        """复用主控的 MusicPlayer（避免两个 MCI 引擎抢音频设备）；取不到则自建。"""
        mp = getattr(self, "_mp", None)
        if mp is not None:
            return mp
        mp = None
        try:                       # 主窗口（启动器/五子棋）已有播放器 → 共享
            mp = getattr(self.master, "music", None)
        except Exception:
            mp = None
        if mp is None:
            try:
                from .music import MusicPlayer
                mp = MusicPlayer()
                self._mp_own = True
            except Exception:
                mp = None
        self._mp = mp
        return mp

    def _build_music_panel(self, parent):
        """侧栏音乐面板：标题行(歌单/模式) + 曲名 + 上/播/下 + 音量滑杆。"""
        try:
            from .gui import MediaButton, VolumeSlider
        except Exception:
            return          # 组件不可用时静默跳过（音乐非核心功能）
        try:
            from .music import MODE_NAMES
        except Exception:
            MODE_NAMES = {"loop": "列表循环", "single": "单曲循环",
                          "shuffle": "随机播放"}
        mp = self._music_engine()
        f = tk.Frame(parent, bg=C_MAIN_DARK, bd=0, highlightthickness=0)
        f.pack(fill="x", padx=10, pady=(2, 6))

        hdr = tk.Frame(f, bg=C_MAIN_DARK)
        hdr.pack(fill="x", pady=(0, 1))
        tk.Label(hdr, text="背景音乐", bg=C_MAIN_DARK, fg=C_ACCENT,
                 font=(self._calli, 12, "bold")).pack(side="left", padx=(2, 0))
        self.gm_mode_btn = MediaButton(
            hdr, MODE_NAMES[getattr(mp, "mode", "loop")] if mp else "列表循环",
            command=self._music_mode, width=74, height=24, accent=False)
        self.gm_mode_btn.pack(side="right", padx=(4, 0))
        self.gm_playlist_btn = MediaButton(
            hdr, "歌单", command=self._open_playlist,
            width=72, height=24, accent=False)
        self.gm_playlist_btn.pack(side="right", padx=(4, 0))

        self.gm_label = tk.Label(f, text="未播放", bg=C_MAIN_DARK,
                                 fg=C_TEXT_DIM, font=(FALLBACK_FAMILY, 10),
                                 anchor="w")
        self.gm_label.pack(fill="x", padx=(2, 0), pady=(1, 4))

        row2 = tk.Frame(f, bg=C_MAIN_DARK)
        row2.pack(fill="x")
        # 媒体符号走矢量绘制（艺术字缺 ▶⏮ 字形会变方块）
        self.gm_prev_btn = MediaButton(row2, "⏮", command=self._music_prev,
                                        width=34, height=30, accent=False)
        self.gm_prev_btn.pack(side="left", padx=(2, 2))
        self.gm_play_btn = MediaButton(row2, "▶", command=self._music_toggle,
                                       width=46, height=32, accent=True)
        self.gm_play_btn.pack(side="left", padx=2)
        self.gm_next_btn = MediaButton(row2, "⏭", command=self._music_next,
                                       width=34, height=30, accent=False)
        self.gm_next_btn.pack(side="left", padx=2)
        self.gm_vol = VolumeSlider(
            row2, value=getattr(mp, "volume", 60) if mp else 60,
            length=max(90, self.panel_w - 190), height=24,
            command=lambda v: mp.set_volume(int(v)) if mp else None)
        self.gm_vol.pack(side="left", padx=(10, 2), expand=True)

        self._music_job = None
        self._playlist_dlg = None
        self._music_sync_ui()
        self._music_job = self.after(900, self._poll_music)

    # -- 音乐控制（与五子棋同名方法语义一致；只读取引擎缓存，绝不在 UI 发 MCI 命令）
    def _music_toggle(self):
        mp = self._music_engine()
        if mp is not None:
            mp.toggle_play()
        self._music_sync_ui()

    def _music_next(self):
        mp = self._music_engine()
        if mp is not None:
            mp.next()
        self._music_sync_ui()

    def _music_prev(self):
        mp = self._music_engine()
        if mp is not None:
            mp.prev()
        self._music_sync_ui()

    def _music_mode(self):
        mp = self._music_engine()
        if mp is None:
            return
        from .music import MODE_LOOP, MODE_SINGLE, MODE_SHUFFLE
        order = [MODE_LOOP, MODE_SINGLE, MODE_SHUFFLE]
        try:
            mp.mode = order[(order.index(mp.mode) + 1) % 3]
        except ValueError:
            mp.mode = MODE_LOOP
        self._music_sync_ui()

    def _sync_music_play_icons(self, playing: bool):
        w = getattr(self, "gm_play_btn", None)
        if w is not None and w.winfo_exists():
            try:
                w.set_text("⏸" if playing else "▶")
            except Exception:
                pass

    def _sync_music_mode_text(self):
        mp = self._music_engine()
        w = getattr(self, "gm_mode_btn", None)
        if w is None or not w.winfo_exists() or mp is None:
            return
        try:
            from .music import MODE_NAMES
            w.set_text(MODE_NAMES[mp.mode])
        except Exception:
            pass

    def _music_sync_ui(self):
        mp = self._music_engine()
        title = "未播放"
        if mp is not None:
            cur = None
            try:
                cur = mp.current
            except Exception:
                cur = None
            if cur:
                title = cur.get("title") or cur.get("name") or "未播放"
        lbl = getattr(self, "gm_label", None)
        if lbl is not None and lbl.winfo_exists():
            try:
                lbl.config(text=title)
            except Exception:
                pass
        self._sync_music_play_icons(bool(mp is not None and mp.playing))
        self._sync_music_mode_text()

    def _poll_music(self):
        """主线程音乐 UI 轮询（~0.9s）：只读取引擎缓存状态刷新曲名/图标。"""
        self._music_job = None
        try:
            if not getattr(self, "_closing", False):
                mp = self._music_engine()
                if mp is not None:
                    st = mp.poll_state()
                    self._music_sync_ui()
                    real = bool(st.get("playing") and st.get("mode") == "playing")
                    self._sync_music_play_icons(real)
            self._sfx_health_check()
        except Exception:
            pass
        finally:
            try:
                if not getattr(self, "_closing", False):
                    self._music_job = self.after(900, self._poll_music)
            except Exception:
                pass

    def _sfx_health_check(self):
        """音效健康探针：队列长期积压（工作线程卡死）→ 重建 winmm 锁自愈。

        与 gui.py 同款逻辑；象棋窗有独立的 SoundManager，故需自行探活。
        """
        sm = getattr(self, "sounds", None)
        if sm is None:
            return
        try:
            from . import sounds as _snd
            q = _snd._SFX_QUEUE
            if q is None:
                return
            if q.qsize() < _snd._SFX_QUEUE_MAX - 2:
                self._sfx_stall_since = 0
                return
            now = int(time.time() * 10)
            if not getattr(self, "_sfx_stall_since", 0):
                self._sfx_stall_since = now
                return
            if now - self._sfx_stall_since < 30:
                return
            self._sfx_stall_since = 0
            sm.recover()
            while q.qsize():
                try:
                    q.get_nowait()
                except Exception:
                    break
        except Exception:
            pass

    def _open_playlist(self):
        """歌单选择窗（与五子棋一致）：列出全部曲目，点选即播放。"""
        mp = self._music_engine()
        if mp is None or not getattr(mp, "tracks", None):
            self._update_status("歌单为空：请将音乐文件放入 assets/music/")
            return
        old = getattr(self, "_playlist_dlg", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    return
            except Exception:
                pass
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
        row_h, Wd = 46, 380
        dlg.geometry(f"{Wd}x{96 + row_h * n + 24}")

        tk.Label(dlg, text="背景音乐歌单", bg=C_MAIN, fg=C_ACCENT,
                 font=(FALLBACK_FAMILY, 15, "bold")).pack(pady=(12, 2))
        tk.Label(dlg, text="点选曲目即开始播放", bg=C_MAIN, fg=C_TEXT_DIM,
                 font=(FALLBACK_FAMILY, 11)).pack(pady=(0, 8))
        list_frame = tk.Frame(dlg, bg=C_MAIN)
        list_frame.pack(fill="both", expand=True, padx=18)

        row_btns: list = []
        try:
            from .gui import GlowButton
        except Exception:
            GlowButton = None

        def _pick(idx):
            mp.play_index(idx)
            self._music_sync_ui()
            self._sync_music_play_icons(True)
            for j, b in enumerate(row_btns):
                on = (j == (mp.index % n))
                try:
                    b._bg = C_MAIN if on else "#3A4256"
                    b._fg = C_ACCENT if on else C_TEXT
                    b._draw()
                except Exception:
                    pass

        for i in range(n):
            name = mp.tracks[i]["name"]
            if GlowButton is not None:
                b = GlowButton(list_frame, text=name,
                               command=lambda idx=i: _pick(idx),
                               width=Wd - 36, height=row_h - 8,
                               bg="#3A4256", fg=C_TEXT,
                               font=(FALLBACK_FAMILY, 12, "bold"))
            else:
                b = tk.Button(list_frame, text=name,
                              command=lambda idx=i: _pick(idx),
                              bg="#3A4256", fg=C_TEXT, relief="flat")
            b.pack(pady=4)
            row_btns.append(b)

        if GlowButton is not None:
            GlowButton(dlg, "关闭", command=dlg.destroy, width=120, height=38,
                       bg=C_DARK_BTN, fg=C_TEXT,
                       font=(FALLBACK_FAMILY, 13, "bold")).pack(pady=(8, 14))
        else:
            tk.Button(dlg, text="关闭", command=dlg.destroy, bg=C_DARK_BTN,
                      fg=C_TEXT, relief="flat").pack(pady=(8, 14))
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ---- 侧栏滚动 ----
    def _side_update_scroll(self):
        try:
            self.side_canvas.configure(
                scrollregion=self.side_canvas.bbox("all"))
            sw = self.sidebar.winfo_width()
            if sw > 1:
                self.side_canvas.itemconfigure(self._side_win, width=sw - 14)
        except Exception:
            pass

    def _side_on_wheel(self, e):
        try:
            delta = int(e.delta)
        except Exception:
            delta = 120
        self._side_wheel_remain += -delta
        if self._side_wheel_after is None:
            self._side_wheel_after = self.after(12, self._side_wheel_step)
        return "break"

    def _side_wheel_step(self):
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

    # ---------------------------------------------------------- 资源预渲染
    def _init_and_start(self):
        """一次性预渲染全部静态资源（底板 + 精灵），随后摆子开局。"""
        if _HAVE_PIL:
            self._cands = _resolve_ttf_paths()
            self._font_cache = {}
            self._board_photo = self._make_board_photo()
            self._sprites = {}
            for key in PIECE_CHAR:
                self._sprites[key] = self._make_piece_sprite(key[0], key[1])
            self._sh_rest = self._make_shadow_sprite(lift=False)
            self._sh_lift = self._make_shadow_sprite(lift=True)
            self._sp_sel = self._make_ring_sprite(SEL_RING, 0.48, 0.062, glow=True)
            self._sp_cap = self._make_ring_sprite(CAP_RING, 0.50, 0.070, glow=True)
            self._sp_last = self._make_dash_ring_sprite(LAST_DOT)
            self._sp_check = self._make_check_ring_sprite()
            self._sp_dot = self._make_dot_sprite()
            self.sounds = None
            if SoundManager is not None:
                try:
                    self.sounds = SoundManager()
                except Exception:
                    self.sounds = None
        else:
            self._fallback_board()
            return
        self._place_board()
        self._rebuild_pieces()
        self._refresh_legal()
        self._refresh_under()
        self._ready = True
        self._update_status()
        # 窗口按桌面尺寸适配后，棋盘几何需按实际窗口重排一次
        self.after(80, self._relayout)
        # 按初始模式准备引擎（人机/机机均为皮卡鱼 NNUE）
        if self._init_mode in ("pve", "aia"):
            self.after(150, self._ensure_engine)

    # ---- 字体 ----
    def _font(self, size_disp: int, art: bool):
        key = (size_disp, art)
        if key in self._font_cache:
            return self._font_cache[key]
        ft = None
        wants = ("art", "art2") if art else ("base",)
        for kind, path in self._cands:
            if kind not in wants:
                continue
            ft = _load_ttf(path, int(size_disp * SS))
            if ft:
                break
        self._font_cache[key] = ft
        return ft

    def _word_font(self, word: str, size_disp: int):
        """整词选字体：艺术字体全覆盖才用，否则整体回退雅黑（避免混排突兀）。"""
        art = self._font(size_disp, art=True)
        if art and all(_covers(art, ch) for ch in word):
            return art
        return self._font(size_disp, art=False)

    def _glyph_font(self, ch: str, size_disp: int):
        art = self._font(size_disp, art=True)
        if art and _covers(art, ch):
            return art
        return self._font(size_disp, art=False)

    # ---- 底板 ----
    def _make_board_photo(self):
        """棋盘底板：主题渐变底 + 网格/九宫/星位/河界（用色全部来自 self._theme）。"""
        ss = 4 if self.cell <= 110 else 3   # 大棋盘降超采样，控制渲染峰值内存
        t = self._theme
        c_line, c_soft = t["line"], t["mark"]
        W, H = self.bw * ss, self.bh * ss
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c, m = self.cell * ss, self.margin * ss
        # 底色：竖向柔和渐变（上浅下深），比纯平涂更有质感
        rows = max(2, int(H / 2))
        for i in range(rows):
            yy0 = H * i / rows
            yy1 = H * (i + 1) / rows + 1
            d.rectangle([0, yy0, W, yy1], fill=mix_hex(t["bg_a"], t["bg_b"], i / rows))

        x0, y0, x1, y1 = m, m, m + 8 * c, m + 9 * c
        lw = max(1, int(1.6 * ss))
        d.rectangle([x0, y0, x1, y1], outline=c_line, width=lw)
        d.rectangle([x0 - 4 * ss, y0 - 4 * ss, x1 + 4 * ss, y1 + 4 * ss],
                    outline=c_soft, width=max(1, int(ss)))
        for j in range(10):
            yy = y0 + j * c
            d.line([x0, yy, x1, yy], fill=c_line, width=lw)
        for i in range(9):
            xx = x0 + i * c
            d.line([xx, y0, xx, y0 + 4 * c], fill=c_line, width=lw)
            d.line([xx, y0 + 5 * c, xx, y1], fill=c_line, width=lw)
        for (ax, ay, bx, by) in ((3, 0, 5, 2), (5, 0, 3, 2),
                                 (3, 7, 5, 9), (5, 7, 3, 9)):
            p = (x0 + ax * c, y0 + ay * c)
            q = (x0 + bx * c, y0 + by * c)
            d.line([p[0], p[1], q[0], q[1]], fill=c_line, width=lw)
        marks = [(1, 2), (7, 2), (1, 7), (7, 7),
                 (0, 3), (2, 3), (4, 3), (6, 3), (8, 3),
                 (0, 6), (2, 6), (4, 6), (6, 6), (8, 6)]
        mk = int(c * 0.10)
        for (mx, my) in marks:
            cx, cy = x0 + mx * c, y0 + my * c
            d.line([cx - mk, cy, cx + mk, cy], fill=c_soft,
                   width=max(1, int(ss)))
            d.line([cx, cy - mk, cx, cy + mk], fill=c_soft,
                   width=max(1, int(ss)))

        # 河界文字（艺术字体，整词覆盖校验后使用）
        fsize = int(self.cell * 0.42)
        for word, cxi in (("楚河", 1.65), ("漢界", 5.75)):
            ft = self._word_font(word, fsize)
            if ft is None:
                continue
            yc = y0 + 4.5 * c
            step = int(c * 0.78)
            start = x0 + int(cxi * c)
            for i, ch in enumerate(word):
                bb = d.textbbox((0, 0), ch, font=ft)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                d.text((start + i * step - tw / 2 - bb[0],
                        yc - th / 2 - bb[1]), ch, fill=t["river"], font=ft)
        img = img.resize((self.bw, self.bh), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    # ---- 主题 ----
    def _on_piece_style(self, name):
        """切换棋子材质（5 种实心木质工艺）：仅重建 14 枚棋子 + 环/阴影精灵。

        铁坑：绝不重建底板（_board_photo）——底板 PhotoImage 一旦被重新赋值，
        旧引用归零 → Tk 删除旧图像 → 棋盘画布项变空白；而材质切换又不会重新
        _place_board，结果就是"换外观后棋盘消失"。底板只随主题/cell 变化。
        """
        if name == self.piece_style:
            return
        self.piece_style = name
        if not getattr(self, "_ready", False):
            return
        self._rebuild_piece_sprites()
        self._rebuild_pieces()
        self._update_status()

    def _rebuild_piece_sprites(self):
        """重建棋子 + 环 + 阴影精灵（不含底板，供材质切换复用）。"""
        for key in PIECE_CHAR:
            self._sprites[key] = self._make_piece_sprite(key[0], key[1])
        self._sh_rest = self._make_shadow_sprite(lift=False)
        self._sh_lift = self._make_shadow_sprite(lift=True)
        self._sp_sel = self._make_ring_sprite(SEL_RING, 0.48, 0.062, glow=True)
        self._sp_cap = self._make_ring_sprite(CAP_RING, 0.50, 0.070, glow=True)
        self._sp_last = self._make_dash_ring_sprite(LAST_DOT)
        self._sp_check = self._make_check_ring_sprite()
        self._sp_dot = self._make_dot_sprite()

    def _rebuild_sprites(self):
        """重建全部静态精灵（底板 + 棋子 + 环 + 阴影）。"""
        self._board_photo = self._make_board_photo()
        self._rebuild_piece_sprites()

    def _on_theme_change(self, name):
        """切换棋盘/棋子主题：重建底板 + 全部精灵 + 重摆棋子。

        运行期"零 PIL 重绘"只对动画过程成立；主题切换是低频操作，
        一次性重建静态资源是正确做法（比维护多套精灵缓存简单可靠）。
        """
        if name == self.theme_name:
            return
        self.theme_name = name
        self._theme = get_theme(name)
        try:
            self.canvas.configure(bg=self._theme["bg_a"])
        except Exception:
            pass
        if not getattr(self, "_ready", False):
            return
        try:
            self._rebuild_sprites()
            self._place_board()
            self._rebuild_pieces()
            self._refresh_under()
        except Exception:
            pass
        self._update_status()

    # ---- 棋子精灵 ----
    def _make_piece_sprite(self, color, kind):
        """棋子：按「棋子材质」（5 种实心木质工艺）渲染，圆形不变。

        棋盘配色与棋子材质是两个独立维度，可自由组合；
        材质内部的字色对比由 xiangqi_pieces 保证（深底配浅字、浅底配深字）。
        """
        ch = PIECE_CHAR[(color, kind)]
        px = int(self.r_piece * 2) + 6
        st = PIECE_STYLES.get(self.piece_style, PIECE_STYLES[DEFAULT_STYLE])
        gcol = st["glyph_red"] if color == RED else st["glyph_black"]
        # _font(size_disp) 内部已按 size_disp*SS 加载（SS 空间像素），
        # render_piece 在 SS 空间画布上绘制后统一降采样——
        # **铁坑：这里绝不能再乘 SS**（双重放大 16 倍会让笔画溢出棋子成"乱码"）。
        ft_ss = self._glyph_font(ch, int(self.cell * 0.62))
        img = render_piece(px, self.piece_style, ch, gcol, font=ft_ss, ss=SS)
        return ImageTk.PhotoImage(img)

    # ---- 阴影精灵 ----
    def _make_shadow_sprite(self, lift: bool):
        # 参考实物棋子：落影是"紧贴底缘的柔和投影"，不是大范围光晕
        R = self.r_piece * (1.16 if lift else 1.04) * SS
        pad = int(R * 0.22)
        S = int(2 * R + 2 * pad)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        theme = self._theme
        shadow = _hex(theme["shadow"])
        cx = cy = S // 2 + (int(SS * 1.2) if lift else int(SS * 0.8))
        layers = 9
        a_peak = 44 if lift else 72
        for i in range(layers):
            u = i / (layers - 1)              # 0 外圈最淡 → 1 中心最浓
            rr = R * (1.0 - 0.42 * u)
            a = int(a_peak * (0.12 + 0.88 * u))
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                      fill=shadow + (a,))
        img = img.resize((int(S / SS), int(S / SS)), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    # ---- 高亮精灵 ----
    def _make_ring_sprite(self, color, radius_k, width_k, glow: bool):
        R = self.cell * radius_k * SS
        pad = int(R * 0.45) if glow else int(R * 0.22)
        S = int(2 * R + 2 * pad)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = cy = S // 2
        col = _hex(color)
        if glow:  # 外圈柔光
            for i in range(3):
                a = 46 + i * 30
                rr = R + (2 - i) * int(1.6 * SS)
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                          outline=col + (a,), width=max(1, int(1.6 * SS)))
        d.ellipse([cx - R, cy - R, cx + R, cy + R],
                  outline=col + (235,), width=max(1, int(self.cell * width_k * SS)))
        img = img.resize((int(S / SS), int(S / SS)), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _make_dot_sprite(self):
        """精致落点指示：外圈柔光环 + 细描边圆环 + 中心亮点（非单调绿点）。"""
        R = self.cell * 0.16 * SS
        pad = int(R * 1.1)
        S = int(2 * R + 2 * pad)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = cy = S // 2
        col = _hex(MOVE_DOT)
        # 外圈柔光（3 层递减 alpha）
        for i in range(3):
            a = 34 + i * 22
            rr = R + (2 - i) * int(1.4 * SS)
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                      outline=col + (a,), width=max(1, int(1.4 * SS)))
        # 细描边圆环
        d.ellipse([cx - R, cy - R, cx + R, cy + R],
                  outline=col + (210,), width=max(1, int(SS * 0.9)))
        # 中心亮点（内实心小圆，带高光感）
        ir = R * 0.42
        for i in range(3):
            t = i / 2.0
            rr = ir * (1.0 - 0.28 * t)
            cc = _mix(col, (255, 255, 255), 0.10 + 0.28 * t)
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=cc + (235,))
        img = img.resize((int(S / SS), int(S / SS)), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _make_dash_ring_sprite(self, color, radius_k=0.30, width_k=0.020,
                               alpha=140, segs=12, arc_deg=14):
        """虚线环精灵（上一步落子位置提示）：细小淡化的短弧段。

        尺寸准则：直径 ≈ 0.60 格 < 棋子 0.88 格，空交点上与棋盘比例协调；
        线宽取格宽 2%，透明度压到 140，避免"一个大圈圈"抢视觉重心。
        """
        R = self.cell * radius_k * SS
        w = max(1, int(self.cell * width_k * SS))
        pad = int(max(w * 2, R * 0.12))     # 抗锯齿留边，避免外圈被裁
        S = int(2 * R + 2 * pad)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = cy = S // 2
        col = _hex(color)
        step = 360.0 / segs
        for k in range(segs):
            start = k * step
            d.arc([cx - R, cy - R, cx + R, cy + R],
                  start=start, end=start + arc_deg, fill=col + (alpha,), width=w)
        img = img.resize((int(S / SS), int(S / SS)), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _make_check_ring_sprite(self):
        """将军警示环：外圈柔光 + 粗描边红环（用于帅/将位置脉冲）。"""
        R = self.cell * 0.56 * SS
        pad = int(R * 0.45)
        S = int(2 * R + 2 * pad)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = cy = S // 2
        col = _hex(CHECK_RING)
        for i in range(4):
            a = 30 + i * 34
            rr = R + (3 - i) * int(2.0 * SS)
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                      outline=col + (a,), width=max(1, int(2.0 * SS)))
        d.ellipse([cx - R, cy - R, cx + R, cy + R],
                  outline=col + (240,), width=max(1, int(self.cell * 0.09 * SS)))
        img = img.resize((int(S / SS), int(S / SS)), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    # ---------------------------------------------------------- 画布布置
    def _place_board(self):
        self.canvas.delete("board")           # 先清旧底板，防重复堆叠
        if getattr(self, "_board_photo", None) is not None:
            self.canvas.create_image(0, 0, image=self._board_photo,
                                     anchor="nw", tags=("board",))

    def _cx(self, gx):
        return self.margin + gx * self.cell

    def _cy(self, gy):
        return self.margin + gy * self.cell

    def _rebuild_pieces(self):
        self.canvas.delete("shadow", "piece")
        self._piece_items = {}
        for y in range(10):
            for x in range(9):
                p = self.board.grid[y][x]
                if p is None:
                    continue
                cx, cy = self._cx(x), self._cy(y)
                sh = self.canvas.create_image(
                    cx + self.r_piece * 0.07, cy + self.r_piece * 0.14,
                    image=self._sh_rest, anchor="center", tags=("shadow",))
                pi = self.canvas.create_image(cx, cy, image=self._sprites[p],
                                              anchor="center", tags=("piece",))
                self._piece_items[(x, y)] = (sh, pi)
        self._lift_id = None
        self._lift_h = 0.0

    def _refresh_under(self):
        self.canvas.delete("under")
        if self.last_move:
            for (gx, gy) in self.last_move:
                self.canvas.create_image(self._cx(gx), self._cy(gy),
                                         image=self._sp_last, anchor="center",
                                         tags=("under",))
        for (tx, ty) in self.targets:
            sp = self._sp_cap if self.board.piece(tx, ty) else self._sp_dot
            self.canvas.create_image(self._cx(tx), self._cy(ty), image=sp,
                                     anchor="center", tags=("under",))
        # 选中环由 _lift_select 单独创建为可移动项（随棋子联动），不在此绘制

    # ---------------------------------------------------------- 动画引擎
    def _animate(self, ms, step, done=None):
        """按 7ms（≈144Hz）步长调度的时间插值动画；控件销毁自动停止。"""
        t0 = time.perf_counter()
        dur = max(1e-3, ms / 1000.0)

        def frame():
            try:
                if not self.winfo_exists():
                    return
                t = (time.perf_counter() - t0) / dur
                if t >= 1.0:
                    step(1.0)
                    if done:
                        done()
                    return
                step(t)
                self.after(FRAME_MS, frame)    # 144Hz 调度步长
            except Exception:
                return                        # 控件已销毁等，静默收场
        frame()

    # ---- 抬棋 / 放回 ----
    def _set_lift(self, h):
        self._lift_h = h
        if self._lift_id is None or self.selected is None:
            return
        gx, gy = self.selected
        cx, cy = self._cx(gx), self._cy(gy)
        try:
            self.canvas.coords(self._lift_id, cx, cy - h)
            # 选中环随棋子同步上移，消除视觉分离
            if self._sel_id is not None:
                self.canvas.coords(self._sel_id, cx, cy - h)
            sh, _ = self._piece_items[(gx, gy)]
            self.canvas.itemconfig(
                sh, image=self._sh_lift if h > self.cell * 0.12 else self._sh_rest)
            self.canvas.coords(sh, cx + self.r_piece * 0.10,
                               cy + h * 0.55 + self.r_piece * 0.14)
        except Exception:
            pass

    def _lift_select(self, gx, gy):
        self.selected = (gx, gy)
        self.targets = [t for (f, t) in self._legal if f == (gx, gy)]
        self._refresh_under()
        _, pi = self._piece_items[(gx, gy)]
        self._lift_id = pi
        # 选中环作为独立画布项，位于棋子之下、随棋子同步移动
        self.canvas.delete(self._sel_id) if self._sel_id else None
        self._sel_id = self.canvas.create_image(
            self._cx(gx), self._cy(gy), image=self._sp_sel,
            anchor="center", tags=("selring",))
        self.canvas.tag_lower(self._sel_id, pi)
        if self.sounds:
            self.sounds.play("click")
        h = self.cell * LIFT_H
        self._animate(T_LIFT, lambda t: self._set_lift(h * _ease_out(t)))

    def _settle_deselect(self, then=None):
        if self.selected is None or self._lift_id is None:
            self.selected = None
            self.targets = []
            self._clear_selring()
            self._refresh_under()
            if then:
                then()
            return
        h0 = self._lift_h

        def step(t):
            self._set_lift(h0 * (1.0 - _ease_in_out(t)))

        def done():
            self._lift_id = None
            self._lift_h = 0.0
            self.selected = None
            self.targets = []
            self._clear_selring()
            self._refresh_under()
            if then:
                then()
        self._animate(T_SETTLE, step, done)

    def _clear_selring(self):
        if self._sel_id is not None:
            self.canvas.delete(self._sel_id)
            self._sel_id = None

    # ---- 走子（弧线 travel + 落地回弹） ----
    def _start_travel(self, frm, to):
        self._busy = True
        self._travel = (frm, to)
        captured = self.board.piece(to[0], to[1])
        cap_ids = self._piece_items.get(to) if captured else None
        self.targets = []
        self.selected = None
        self._lift_id = None
        self._clear_selring()
        self.canvas.delete("under")
        sh, pi = self._piece_items[frm]
        x0, y0 = self._cx(frm[0]), self._cy(frm[1])
        x1, y1 = self._cx(to[0]), self._cy(to[1])
        h0 = self._lift_h
        arc = self.cell * ARC_H

        def step(t):
            te = _ease_in_out(t)
            x = x0 + (x1 - x0) * te
            ybase = y0 + (y1 - y0) * te
            h = h0 * (1.0 - te) + arc * math.sin(math.pi * te)
            self.canvas.coords(pi, x, ybase - h)
            self.canvas.coords(sh, x + self.r_piece * 0.08,
                               ybase + h * 0.30 + self.r_piece * 0.12)
            self.canvas.itemconfig(
                sh, image=self._sh_lift if h > self.cell * 0.10 else self._sh_rest)

        def landed():
            self.canvas.coords(pi, x1, y1)
            self.canvas.coords(sh, x1 + self.r_piece * 0.07,
                               y1 + self.r_piece * 0.14)
            self.canvas.itemconfig(sh, image=self._sh_rest)
            if self.sounds:
                self.sounds.play("stone")
            if cap_ids:
                self._capture_fx(cap_ids, x1, y1, (x1 - x0, y1 - y0))
            dip = self.cell * 0.035

            def bounce(tt):
                off = dip * math.sin(tt * math.pi)
                self.canvas.coords(pi, x1, y1 + off)
            self._animate(T_LAND, bounce)
            self.after(max(T_IMPACT, T_SHAKE, T_LAND) + 60, self._finalize_move)

        self._animate(T_TRAVEL, step, landed)

    # ---- 吃子特效：撞飞 + 冲击光环 + 全盘震动 ----
    def _capture_fx(self, cap_ids, x, y, direction):
        csh, cpi = cap_ids
        dx, dy = direction
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        dist = self.cell * 0.38

        def knock(t):
            e = _ease_out(t)
            px = x + ux * dist * e
            py = y + uy * dist * e - self.cell * 0.20 * e
            self.canvas.coords(cpi, px, py)
            self.canvas.coords(csh, px + self.r_piece * 0.07,
                               py + self.r_piece * (0.14 + 0.10 * e))
        self._animate(T_KNOCK, knock,
                      done=lambda: self._safe_delete((csh, cpi)))

        ring = self.canvas.create_oval(
            x - self.r_piece, y - self.r_piece,
            x + self.r_piece, y + self.r_piece,
            outline=IMPACT_RING, width=max(2, int(self.cell * 0.075)),
            tags=("over",))

        def ripple(t):
            rr = self.r_piece * (0.95 + 0.95 * _ease_out(t))
            self.canvas.coords(ring, x - rr, y - rr, x + rr, y + rr)
            self.canvas.itemconfig(ring,
                                   width=max(1, int(self.cell * 0.075 * (1 - t))))
        self._animate(T_IMPACT, ripple,
                      done=lambda: self._safe_delete_item(ring))
        self._shake()

    def _shake(self):
        """全盘衰减震动：整体平移全部画布项，结束时回移复位（净位移为零）。"""
        amp = self.cell * 0.055
        total = [0.0, 0.0]
        prev = [0.0, 0.0]

        def sh(t):
            dec = 1.0 - t
            ox = amp * dec * math.sin(t * math.pi * 5.0)
            oy = amp * 0.6 * dec * math.cos(t * math.pi * 4.0)
            dx_, dy_ = ox - prev[0], oy - prev[1]
            self.canvas.move("all", dx_, dy_)
            total[0] += dx_
            total[1] += dy_
            prev[0], prev[1] = ox, oy

        def done():
            try:
                self.canvas.move("all", -total[0], -total[1])
            except Exception:
                pass
        self._animate(T_SHAKE, sh, done)

    def _safe_delete(self, ids):
        try:
            self.canvas.delete(*ids)
        except Exception:
            pass

    # ---- 将军过渡动画：被将方帅/将位置脉冲红环 + 全盘暗角警示 ----
    def _play_check_anim(self):
        """被将军一方的帅/将位置显示脉冲红环，配合全盘短暂暗角，明确提示被将方。"""
        if self.board.game_over:
            return
        kpos = self.board._find_king(self.board.turn)
        if kpos is None:
            return
        kx, ky = kpos
        cx, cy = self._cx(kx), self._cy(ky)

        # 全盘暗角探照：整板半透明白→暗，聚焦被将方
        self._check_dim = self.canvas.create_rectangle(
            0, 0, self.bw, self.bh, fill="#3A0D0A", stipple="gray50",
            outline="", tags=("checkdim",))
        # 被将方帅/将位置红环
        self._check_id = self.canvas.create_image(
            cx, cy, image=self._sp_check, anchor="center", tags=("checkring",))
        self.canvas.tag_raise(self._check_id)

        def pulse(t):
            # 红环缩放脉冲：1.0 → 1.28 → 1.0 循环
            sc = 1.0 + 0.28 * math.sin(t * math.pi * 3.0)
            try:
                self.canvas.scale(self._check_id, cx, cy, sc, sc)
            except Exception:
                pass

        self._animate(T_SHAKE * 2, pulse,
                      done=lambda: self._clear_check_anim())

    def _clear_check_anim(self):
        try:
            if self._check_id is not None:
                self.canvas.delete(self._check_id)
        except Exception:
            pass
        try:
            if getattr(self, "_check_dim", None) is not None:
                self.canvas.delete(self._check_dim)
        except Exception:
            pass
        self._check_id = None
        self._check_dim = None

    def _safe_delete_item(self, item):
        try:
            self.canvas.delete(item)
        except Exception:
            pass

    def _finalize_move(self):
        if self._travel is None:
            return
        frm, to = self._travel
        self._travel = None
        self.board.apply(frm, to)
        self.last_move = (frm, to)
        self._refresh_legal()
        self._rebuild_pieces()
        self._refresh_under()
        self._update_status()
        self._busy = False
        if self.board.game_over:
            self.after(300, self._show_gameover)
        elif self.board.in_check(self.board.turn):
            self.after(60, self._play_check_anim)
        self._record_winrate()
        self._maybe_trigger_ai()

    # ---------------------------------------------------------- 人机对战
    def _on_mode_change(self):
        if self._ai_busy:
            # AI 思考中切换：作废本轮结果（代数守卫见 _poll_ai）
            self._ai_busy = False
            if self._ai_job is not None:
                try:
                    self.after_cancel(self._ai_job)
                except Exception:
                    pass
                self._ai_job = None
        self._reset_for_new_game()
        mode = self.mode_var.get()
        if mode in ("pve", "aia"):
            self._ensure_engine()
        else:
            self._update_status()
            return
        # 机机模式下开局无先手行棋事件，需主动调度首次 AI 落子
        # （引擎未就绪时 _maybe_trigger_ai 自带 300ms 重试轮询）
        self.after(300, self._maybe_trigger_ai)

    def _on_diff_change(self):
        if self.engine is not None:
            try:
                self.engine.set_difficulty(self.diff_var.get())
            except Exception:
                pass

    def _reset_for_new_game(self):
        self.board.reset()
        self.last_move = None
        self.selected = None
        self.targets = []
        self._clear_selring()
        self._clear_check_anim()
        self._wr_cp.clear()
        self._wr_src.clear()
        self._wr_y.clear()
        self._draw_winrate()
        self._refresh_legal()
        self._rebuild_pieces()
        self._refresh_under()
        self._update_status()

    def _desired_kind(self):
        """当前模式所需的引擎类别（象棋 AI 均为皮卡鱼 NNUE）。"""
        return "pikafish"

    def _ensure_engine(self):
        """懒加载皮卡鱼：后台线程启动（NNUE 加载 ~1s），失败明确提示并回退人人。"""
        if self._desired_kind() != "pikafish":
            return    # 双人对弈不需要引擎，忽略遗留调度
        if self._engine_state == "ready" and self._engine_kind == "pikafish":
            self._update_status()
            return
        if self._engine_state == "loading" and self._loading_kind == "pikafish":
            return
        from . import pikafish_engine as pf
        exe, nnue = pf.find_engine()
        if not exe or not nnue:
            self._engine_state = "failed"
            self.mode_var.set("pvp")
            self._update_status()
            self._alert("未找到皮卡鱼引擎",
                        "未找到 Pikafish 引擎或 NNUE 权重文件。\n"
                        "请确认引擎目录存在（项目 engine/ 下或桌面），\n"
                        "或在 config/pikafish.ini 中配置 exe/nnue 路径。\n"
                        "已回退为双人对弈。")
            return
        self._engine_state = "loading"
        self._engine_kind = None
        self._loading_kind = "pikafish"
        self._update_status("正在加载皮卡鱼引擎（NNUE）…")
        diff = self.diff_var.get()   # tk.StringVar 只能在主线程读，先取出

        def loader():
            try:
                eng = pf.PikafishEngine(exe, nnue)
                eng.set_difficulty(diff)
                eng.new_game()
                if getattr(self, "_closing", False):   # 窗口已关：直接回收
                    eng.close()
                    return
                self._ai_queue.put(("engine_ready", eng, "pikafish"))
            except Exception as exc:
                self._ai_queue.put(("engine_failed", repr(exc), "pikafish"))

        threading.Thread(target=loader, daemon=True).start()
        self._start_engine_poll()

    def _start_engine_poll(self):
        """启动引擎就绪轮询；代际令牌保证旧循环自动退出（防多循环抢消息）。"""
        try:
            self._poll_gen += 1
        except AttributeError:
            self._poll_gen = 1
        gen = self._poll_gen
        self._poll_engine(gen)

    def _poll_engine(self, gen):
        if gen != getattr(self, "_poll_gen", None):
            return    # 已有新一轮轮询接管，旧循环退出
        try:
            msg = self._ai_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_engine, gen)
            return
        except ValueError:
            return
        if msg[0] != "bestmove":
            self._handle_engine_msg(msg)

    def _handle_engine_msg(self, msg):
        """统一处理 engine_ready/engine_failed（3 元组，带引擎类别 ekind）。"""
        kind, payload, ekind = msg
        if ekind != self._desired_kind():
            # 模式已切换：丢弃过期引擎（皮卡鱼子进程需回收），不改变当前状态
            if ekind == "pikafish" and kind == "engine_ready":
                try:
                    payload.close()
                except Exception:
                    pass
            return
        if kind == "engine_ready":
            self.engine = payload
            self._engine_kind = ekind
            self._engine_state = "ready"
            self._update_status()
        elif kind == "engine_failed":
            self._engine_state = "failed"
            self.mode_var.set("pvp")
            self._update_status()
            self._alert("引擎启动失败",
                        f"引擎启动失败。\n已回退为双人对弈。\n\n{payload}")

    def _maybe_trigger_ai(self):
        """机机/人机调度：pve=黑方由皮卡鱼应手；aia=皮卡鱼互弈观战。"""
        mode = self.mode_var.get()
        if mode == "pvp" or self.board.game_over:
            return
        if mode == "pve" and (self.board.turn != BLACK
                              or not self.board.history):
            return
        if self._engine_state != "ready" or self._engine_kind != self._desired_kind():
            if self._engine_state == "loading":
                self._update_status("引擎准备中…稍候自动走子")
                self.after(300, self._maybe_trigger_ai)
            elif self._engine_state == "idle":
                self._ensure_engine()
                self.after(300, self._maybe_trigger_ai)
            return

        self._ai_busy = True
        side = COLOR_CN[self.board.turn]
        self._update_status(f"皮卡鱼（{side}方）思考中…")
        diff = "medium" if mode == "aia" else self.diff_var.get()
        moves_uci = [self.board.uci_move((h[0], h[1]), (h[2], h[3]))
                     for h in self.board.history]
        _, depth = DIFFICULTY_PRESETS.get(diff, (12, 10))

        def worker():
            try:
                mv, score = self.engine.best_move(moves_uci, depth=depth)
            except Exception:
                mv, score = None, None
            self._ai_queue.put(("bestmove", (mv, score)))

        threading.Thread(target=worker, daemon=True).start()
        self._ai_job = self.after(120, self._poll_ai)

    def _fallback_move(self):
        """引擎异常时的兜底着法：优先吃价值最高的子（并列随机），观战不中断。"""
        import random
        if not self._legal:
            return None
        val = {"R": 900, "C": 450, "H": 450, "E": 200, "A": 200, "P": 100}

        def cap_val(m):
            p = self.board.piece(*m[1])
            return val.get(p[1], 0) if p else 0
        best = max(cap_val(m) for m in self._legal)
        top = [m for m in self._legal if cap_val(m) == best]
        return random.choice(top)

    def _poll_ai(self):
        self._ai_job = None
        try:
            msg = self._ai_queue.get_nowait()
        except queue.Empty:
            self._ai_job = self.after(120, self._poll_ai)
            return
        if msg[0] != "bestmove":
            # 引擎就绪/失败消息被本轮询抢先取到：转交处理器，继续等 bestmove
            self._handle_engine_msg(msg)
            self._ai_job = self.after(120, self._poll_ai)
            return
        kind, payload = msg
        if not self._ai_busy:     # 对局已重开/切模式：丢弃过期结果
            return
        mv, extra = payload
        self._ai_busy = False
        # 皮卡鱼评分精化最新胜率点（score 为行棋方视角 cp，需归一到黑视角）
        self._refine_winrate(extra, self.board.turn)
        move = self.board.parse_uci_move(mv) if mv else None
        if move is None or move not in self._legal:
            # 兜底：引擎返回异常着法 → 优先吃大子的合法着顶替，对局不中断
            if self._legal:
                move = self._fallback_move()
                self._update_status("着法异常，已用备选着法")
                self.after(700, lambda: self._start_travel(*move)
                           if not self._busy and not self.board.game_over else None)
            else:
                self._update_status("无合法着法")
            return
        self._start_travel(*move)

    def _alert(self, title, msg):
        """明确反馈弹窗：优先游戏内自绘弹窗，兜底 messagebox。"""
        try:
            from .styled_dialog import confirm_dialog
            confirm_dialog(self, title, msg, ok_text="知道了")
        except Exception:
            try:
                from tkinter import messagebox
                messagebox.showwarning(title, msg, parent=self)
            except Exception:
                pass

    # ---------------------------------------------------------- 交互
    def _refresh_legal(self):
        self._legal = self.board.legal_moves() if not self.board.game_over else []

    def _on_click(self, event):
        if self._busy or self._ai_busy or not self._ready or self.board.game_over:
            return
        gx = round((event.x - self.margin) / self.cell)
        gy = round((event.y - self.margin) / self.cell)
        if not (0 <= gx <= 8 and 0 <= gy <= 9):
            self._settle_deselect()
            return
        p = self.board.piece(gx, gy)
        if self.selected is None:
            if p is not None and p[0] == self.board.turn:
                self._lift_select(gx, gy)
            return
        if (gx, gy) == self.selected:
            self._settle_deselect()
            return
        if (gx, gy) in self.targets:
            self._start_travel(self.selected, (gx, gy))
            return
        if p is not None and p[0] == self.board.turn:
            self._settle_deselect(then=lambda: self._lift_select(gx, gy))
            return
        self._settle_deselect()

    def _on_undo(self):
        if self._busy or self._ai_busy or not self.board.history:
            return
        self.board.undo()
        popped = 1
        # 人机模式：撤掉 AI 一步 + 自己一步，回到玩家行棋
        if (self.mode_var.get() == "pve" and self.board.turn == BLACK
                and self.board.history):
            self.board.undo()
            popped += 1
        self.last_move = None
        self.selected = None
        self.targets = []
        self._clear_selring()
        self._clear_check_anim()
        self._pop_winrate(popped)
        self._refresh_legal()
        self._rebuild_pieces()
        self._refresh_under()
        self._update_status()
        # 机机/高阶机机：悔棋后 AI 自动续走，观战不中断
        self._maybe_trigger_ai()

    def _on_restart(self):
        if self._busy or self._ai_busy:
            return
        self._reset_for_new_game()
        if (self.mode_var.get() == "pve" and self._engine_state == "ready"):
            try:
                self.engine.new_game()
            except Exception:
                pass

    def _on_back(self):
        try:
            self.destroy()
        except Exception:
            pass

    def _update_status(self, text=None):
        """侧栏状态更新：双方信息 + 当前行棋/将军/终局（加载文案模式见 text）。"""
        if not hasattr(self, "lbl_status"):
            return
        if text is not None:
            self.lbl_status.config(text=text, fg=C_ACCENT)
            return
        mode = self.mode_var.get()
        if mode == "pve":
            self.lbl_red.config(text="红方：玩家（先行）")
            self.lbl_black.config(text="黑方：皮卡鱼 NNUE")
        elif mode == "aia":
            self.lbl_red.config(text="红方：皮卡鱼 NNUE")
            self.lbl_black.config(text="黑方：皮卡鱼 NNUE（机机）")
        else:
            self.lbl_red.config(text="红方：玩家（先行）")
            self.lbl_black.config(text="黑方：玩家")
        if self.board.game_over:
            w = COLOR_CN.get(self.board.winner, "")
            self.lbl_status.config(text=f"对局结束 · {w}方胜", fg=C_ACCENT)
            return
        side = COLOR_CN[self.board.turn]
        if self.board.in_check(self.board.turn):
            self.lbl_status.config(text=f"轮到 {side}方 · 将军！请应将",
                                   fg="#E86A5A")
        else:
            self.lbl_status.config(text=f"轮到 {side}方行棋", fg=C_ACCENT)

    # ---- 胜率曲线（黑方期望得分率，随手数走势） ----
    # 方法依据（见工程记忆）：
    #   · Pikafish 官方 Wiki《各个引擎的打分为什么不一样》给出象棋引擎分的
    #     Elo 口径 D=400：「一方优势 200 分代表 76% 胜率」，反解 200/0.5004≈400。
    #     故换算用 W = 100 / (1 + 10^(-cp/400))，锚点：+1兵(100cp)≈64%、
    #     +2兵(200cp)≈76%、+4兵≈91%。
    #   · 象棋和棋率极高（引擎自战 >94%），单值胜率封顶 [5,95]，用期望得分率
    #     （胜 + 0.5×和）而非纯胜率。
    #   · 引擎分在开局低分区间噪声大，故曲线按「概率」做 EMA(α=0.45) 平滑，
    #     并限幅单步 ±10 个百分点，彻底消除单点跳变（开局恒为 50%）。
    #   · 横轴 = ply（半回合）序号，窗口滚动时按真实手数打刻度。
    WR_D = 400.0          # Pikafish 官方 Elo 口径
    WR_ALPHA = 0.45       # 概率 EMA 系数
    WR_MAX_STEP = 10.0    # 单步最大变动（百分点）
    WR_CAP = 95.0
    WR_FLOOR = 5.0
    WR_WINDOW = 120       # 曲线显示窗口（ply）

    # 子力价值（cp 量级，业界通用表）：车 900 / 马 450 / 炮 450 / 相士 200 / 兵 100
    _XQ_VAL = {"R": 900.0, "C": 450.0, "H": 450.0, "E": 200.0, "A": 200.0,
               "P": 100.0}

    def _build_winrate(self):
        wr_header = tk.Frame(self.side_inner, bg=C_MAIN_DARK)
        wr_header.pack(fill="x", padx=18, pady=(4, 0))
        tk.Label(wr_header, text="胜率曲线", bg=C_MAIN_DARK, fg=C_TEXT,
                 font=(self._calli, 14, "bold")).pack(side="left")
        self.lbl_wr_now = tk.Label(wr_header, text="黑 — · 红 —", bg=C_MAIN_DARK,
                                   fg=C_ACCENT, font=(FALLBACK_FAMILY, 11, "bold"))
        self.lbl_wr_now.pack(side="right")

        self.wr_canvas = tk.Canvas(self.side_inner, bg="#202530",
                                   highlightthickness=0, bd=0, width=300,
                                   height=140)
        self.wr_canvas.pack(fill="x", padx=14, pady=4)
        self.wr_canvas.bind("<Configure>", lambda e: self._draw_winrate())

        tk.Label(self.side_inner,
                 text="—— 黑方期望得分率（引擎评估分换算，D=400）",
                 bg=C_MAIN_DARK, fg=C_TEXT_DIM, anchor="w",
                 font=(FALLBACK_FAMILY, 10)).pack(fill="x", padx=20)

    def _black_cp(self):
        """黑视角评估分（正=黑优）；过河兵价值翻倍。"""
        cp = 0.0
        for y in range(10):
            for x in range(9):
                p = self.board.grid[y][x]
                if p is None:
                    continue
                color, kind = p
                v = self._XQ_VAL.get(kind, 0.0)
                if kind == "P" and (y <= 4 if color == RED else y >= 5):
                    v *= 2.0
                cp += v if color == BLACK else -v
        return cp

    @classmethod
    def _wr_from_cp(cls, cp: float) -> float:
        """评估分 → 黑方期望得分率(%)：Elo 口径 D=400，封顶 [5,95]。"""
        try:
            cp = float(cp)
        except (TypeError, ValueError):
            return 50.0
        cp = max(-4000.0, min(4000.0, cp))
        w = 100.0 / (1.0 + 10.0 ** (-cp / cls.WR_D))
        return max(cls.WR_FLOOR, min(cls.WR_CAP, w))

    def _winrate_series(self):
        """把逐点评估分序列转成显示用胜率序列：EMA 平滑 + 单步限幅。

        平滑与限幅都在「概率域」做（研究结论：cp 域大数值会饱和失真），
        因此开局第一点必然是 50% 附近，后续随局势平缓推进。
        """
        out = []
        prev = 50.0
        for cp in self._wr_cp:
            raw = self._wr_from_cp(cp)
            step = self.WR_ALPHA * (raw - prev)
            step = max(-self.WR_MAX_STEP, min(self.WR_MAX_STEP, step))
            prev = max(self.WR_FLOOR, min(self.WR_CAP, prev + step))
            out.append(prev)
        self._wr_y = out
        return out

    def _record_winrate(self, cp=None, src="mat"):
        """每走一步追加一个评估分点（默认黑方视角子力分）。"""
        if self.board.game_over:
            cp = 100000.0 if self.board.winner == BLACK else -100000.0
            src = "end"
        elif cp is None:
            cp = self._black_cp()
        self._wr_cp.append(float(cp))
        self._wr_src.append(src)
        self._winrate_series()
        self._draw_winrate()

    def _pop_winrate(self, n: int):
        if n > 0 and self._wr_cp:
            del self._wr_cp[-n:]
            del self._wr_src[-n:]
        self._winrate_series()
        self._draw_winrate()

    def _refine_winrate(self, score, side=None):
        """用引擎评估分精化最新点（score 为行棋方视角 cp，需归一到黑视角）。"""
        if not self._wr_cp or score is None:
            return
        # 引擎分是「行棋方视角」：AI 执黑时即黑视角，执红时取反
        cp_black = float(score) if (side is None or side == BLACK) else -float(score)
        self._wr_cp[-1] = cp_black
        self._wr_src[-1] = "eng"
        self._winrate_series()
        self._draw_winrate()

    def _draw_winrate(self):
        """绘制胜率折线（50% 基线 + EMA 平滑 + 真实手数刻度）。"""
        if not hasattr(self, "wr_canvas"):
            return
        c = self.wr_canvas
        panel_bg = blend(C_MAIN_DARK, "#FFFFFF", 0.06)
        try:
            if c.cget("bg") != panel_bg:
                c.configure(bg=panel_bg)
        except Exception:
            pass
        c.delete("all")
        W = max(c.winfo_width(), 1)
        H = max(c.winfo_height(), 1)
        if W < 60 or H < 40:
            return
        pad_l, pad_r, pad_t, pad_b = 6, 6, 8, 20
        plot_w = W - pad_l - pad_r
        plot_h = H - pad_t - pad_b
        if plot_w <= 2 or plot_h <= 2:
            return

        c.create_rectangle(0, 0, W, H, fill=panel_bg, outline="")
        by = pad_t + plot_h * 0.5
        c.create_line(pad_l, by, W - pad_r, by, fill="#4A5466", width=1,
                      dash=(2, 2))
        c.create_line(pad_l, pad_t, W - pad_r, pad_t, fill="#333A4C", width=1)
        c.create_line(pad_l, pad_t + plot_h, W - pad_r, pad_t + plot_h,
                      fill="#333A4C", width=1)
        for val in (0, 25, 50, 75, 100):
            yy = pad_t + plot_h * (1 - val / 100.0)
            c.create_line(pad_l, yy, pad_l + 3, yy, fill="#5A6577", width=1)
            c.create_text(pad_l + 3, yy, text=str(val), anchor="w",
                          fill="#6B7486", font=(FALLBACK_FAMILY, 8))

        series = self._winrate_series()
        n = len(series)
        if n == 0:
            c.create_text(W / 2, H / 2, text="对局开始后显示走势",
                          fill=C_TEXT_DIM, font=(FALLBACK_FAMILY, 10))
            self.lbl_wr_now.config(text="黑 — · 红 —")
            return

        wstart = max(0, n - self.WR_WINDOW)
        view = series[wstart:]

        def xpx(idx):
            """idx = 全局 ply 序号（0 起）→ 像素 x。"""
            return pad_l + plot_w * (idx - wstart) / max(1.0, len(view) - 1)

        def ypx(yv):
            return pad_t + plot_h * (1 - min(100.0, max(0.0, yv)) / 100.0)

        pts = [(xpx(i), ypx(v)) for i, v in enumerate(view)]
        if len(pts) >= 2:
            c.create_line(*sum(pts, ()), fill=C_ACCENT, width=2, smooth=True)
        step = max(1, len(pts) // 40)
        for i in range(0, len(pts), step):
            px, py = pts[i]
            c.create_oval(px - 2.0, py - 2.0, px + 2.0, py + 2.0,
                          fill=C_ACCENT, outline="")
        lx, ly = pts[-1]
        c.create_oval(lx - 4, ly - 4, lx + 4, ly + 4, fill=C_GLOW, outline="")
        cur = view[-1]
        tag = f"{cur:.0f}%"
        ax = lx + 8
        anchor = "w"
        if ax + 30 > W:
            ax = lx - 8
            anchor = "e"
        c.create_text(ax, ly, text=tag, anchor=anchor,
                      fill=C_GLOW, font=(FALLBACK_FAMILY, 9, "bold"))

        # 横轴：按真实手数（每 ~1/4 窗口一个刻度），左右端标注当前窗口手数
        span = len(view)
        tick_step = max(5, int(round(span / 4.0 / 5.0)) * 5 or 5)
        for k in range(0, span, tick_step):
            tx = xpx(k)
            c.create_line(tx, pad_t + plot_h, tx, pad_t + plot_h + 3,
                          fill="#5A6577", width=1)
            c.create_text(tx, H - 3, text=f"{wstart + k + 1}", anchor="s",
                          fill="#6B7486", font=(FALLBACK_FAMILY, 8))
        c.create_text(pad_l, H - 3, text="手", anchor="sw",
                      fill="#6B7486", font=(FALLBACK_FAMILY, 8))
        c.create_text(W - pad_r, H - 3, text=f"第 {n} 手", anchor="se",
                      fill="#6B7486", font=(FALLBACK_FAMILY, 8))

        self.lbl_wr_now.config(text=f"黑 {cur:.0f}% · 红 {100 - cur:.0f}%")

    # ------------------------------------------------------ 无 PIL 回退
    def _fallback_board(self):
        self.canvas.delete("all")
        c, m = self.cell, self.margin
        t = self._theme
        LINE, LINE_SOFT, RING_COL = t["line"], t["mark"], t
        self.canvas.configure(bg=t["bg_a"])
        self.canvas.create_rectangle(m, m, m + 8 * c, m + 9 * c, outline=t["line"])
        for j in range(10):
            self.canvas.create_line(m, m + j * c, m + 8 * c, m + j * c, fill=LINE)
        for i in range(9):
            xx = m + i * c
            self.canvas.create_line(xx, m, xx, m + 4 * c, fill=LINE)
            self.canvas.create_line(xx, m + 5 * c, xx, m + 9 * c, fill=LINE)
        pr = int(self.cell * 0.40)
        for y in range(10):
            for x in range(9):
                p = self.board.grid[y][x]
                if p:
                    cx, cy = m + x * c, m + y * c
                    col = (t["glyph_red"] if p[0] == RED else t["glyph_black"])
                    self.canvas.create_oval(cx - pr, cy - pr, cx + pr, cy + pr,
                                            fill=t["face_b"], outline=col, width=2)
                    self.canvas.create_text(cx, cy, text=PIECE_CHAR[p],
                                            fill=col,
                                            font=(FALLBACK_FAMILY,
                                                  int(self.cell * 0.5), "bold"))
        self._ready = True

    # ---------------------------------------------------------- 结束弹窗
    def _show_gameover(self):
        win = tk.Toplevel(self)
        win.title("对局结束")
        win.configure(bg=C_MAIN)
        win.resizable(False, False)
        try:
            win.transient(self)
            win.grab_set()
        except Exception:
            pass
        w = COLOR_CN.get(self.board.winner, "")
        tk.Label(win, text=f"{w}方胜", bg=C_MAIN, fg=C_ACCENT,
                 font=(FALLBACK_FAMILY, 24, "bold")).pack(padx=40, pady=(24, 6))
        tk.Label(win, text="对方无合法着法（将死或困毙）", bg=C_MAIN,
                 fg=C_TEXT_DIM, font=(FALLBACK_FAMILY, 12)).pack(pady=(0, 18))

        def restart():
            try:
                win.destroy()
            except Exception:
                pass
            self._on_restart()

        def close():
            try:
                win.destroy()
            except Exception:
                pass
        try:
            from .gui import GlowButton
            b1 = GlowButton(win, "再来一局", command=restart, width=160,
                            height=42, bg=C_ACCENT, fg="#1F2430",
                            font=(FALLBACK_FAMILY, 14, "bold"))
            b2 = GlowButton(win, "关闭", command=close, width=160, height=42,
                            bg=C_DARK_BTN, fg=C_TEXT,
                            font=(FALLBACK_FAMILY, 14, "bold"))
        except Exception:
            b1 = tk.Button(win, text="再来一局", command=restart, bg=C_ACCENT,
                           fg="#1F2430", font=(FALLBACK_FAMILY, 14, "bold"))
            b2 = tk.Button(win, text="关闭", command=close, bg=C_DARK_BTN,
                           fg=C_TEXT, font=(FALLBACK_FAMILY, 14, "bold"))
        b1.pack(padx=30, pady=(0, 8))
        b2.pack(padx=30, pady=(0, 18))
        win.update_idletasks()
        try:
            px, py = self.winfo_rootx(), self.winfo_rooty()
            pw, ph = self.winfo_width(), self.winfo_height()
            ww, wh = win.winfo_width(), win.winfo_height()
            win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")
        except Exception:
            pass
