# -*- coding: utf-8 -*-
"""
replay.py —— 棋谱回放窗口（独立 Toplevel）

读取一局对局的落子序列，按步回放/快进，显示当前局面与胜负结果。
用于"对局结束后的复盘"以及数据库存档的棋谱回放。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .board import Board, BLACK, WHITE
from .theme_boards import get_theme
from .roundrect import draw_3d_button

SPEEDS = [("慢速", 1400), ("较慢", 900), ("中速", 600), ("快速", 300)]
DEFAULT_SPEED = SPEEDS[1][1]   # 默认"较慢"，复盘不赶时间


def _blend(c1: str, c2: str, ratio: float) -> str:
    r = int(int(c1[1:3], 16) + (int(c2[1:3], 16) - int(c1[1:3], 16)) * ratio)
    g = int(int(c1[3:5], 16) + (int(c2[3:5], 16) - int(c1[3:5], 16)) * ratio)
    b = int(int(c1[5:7], 16) + (int(c2[5:7], 16) - int(c1[5:7], 16)) * ratio)
    return f"#{max(0,r):02X}{max(0,g):02X}{max(0,b):02X}"


def _shade(color: str, factor: float) -> str:
    c = color.lstrip("#")
    r = max(0, min(255, int(int(c[0:2], 16) * factor)))
    g = max(0, min(255, int(int(c[2:4], 16) * factor)))
    b = max(0, min(255, int(int(c[4:6], 16) * factor)))
    return f"#{r:02X}{g:02X}{b:02X}"


class CanvasButton(tk.Canvas):
    """棋谱回放窗口自绘按钮：与游戏主程序一致的立体光影风格
    （投影 + 渐变 + 顶部高光 + 悬停光晕 + 按下内陷）。"""

    def __init__(self, master, text: str, command=None, width: int = 120,
                 height: int = 34, bg: str = "#3A4256",
                 fg: str = "#EDEFF4"):
        try:
            parent_bg = master.cget("bg")
        except Exception:
            parent_bg = "#1F2430"
        super().__init__(master, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        # 注意：绝不能用 self._w / self._h 存尺寸 —— tkinter 内部用
        # self._w 存 widget 的 Tcl 路径名，覆写会使 pack() 报
        # "bad window path name"。尺寸存 _bw / _bh。
        self._bw = width
        self._bh = height
        self._pressed = False
        self._hover = False
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self._draw()

    def _hov(self, v):
        self._hover = v
        self._draw()

    def _press(self, _e):
        self._pressed = True
        self._draw()

    def _release(self, _e):
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self._command:
            self._command()

    def set_text(self, text: str):
        self._text = text
        self._draw()

    def _draw(self):
        # 统一走全局玻璃质感渲染器（PIL 超采样：真抗锯齿边缘 + 半透明高光）
        draw_3d_button(self, self._bw, self._bh,
                       base=self._bg, fg=self._fg, text=self._text,
                       font=("Microsoft YaHei UI", 11, "bold"),
                       hover=self._hover, pressed=self._pressed,
                       enabled=True, radius=min(10, self._bh // 3))


class ReplayWindow(tk.Toplevel):
    """棋谱回放窗口。

    record : Game.to_record() 或 get_game_record() 的字典，
             含 "moves" = [(x, y, color) | (color, x, y), ...]
    """

    def __init__(self, master, record: dict, title: str = "棋谱回放"):
        super().__init__(master)
        self.title(title)
        self.configure(bg="#1F2430")
        self.geometry("760x780")
        self.minsize(560, 600)

        # 归一化 moves：统一为 [(x, y, color)]
        raw = record.get("moves", [])
        moves = []
        for m in raw:
            if len(m) == 3:
                if m[2] in (BLACK, WHITE):
                    x, y, c = m
                else:
                    c, x, y = m
                moves.append((x, y, c))
        self.moves = moves
        self.record = record
        self.theme = get_theme("经典原木")

        # 棋种随棋谱携带（旧棋谱无字段时回退为六子棋 19×19/连六）
        self._bsize = int(record.get("size", 19) or 19)
        self._bwin = int(record.get("win_count", 6) or 6)

        self.b = Board(self._bsize, self._bwin)
        self.step_i = 0
        self.playing = False
        self.speed = DEFAULT_SPEED
        self._job = None

        self._build()
        self._draw()

    def _mk_btn(self, parent, text, cmd):
        return CanvasButton(parent, text=text, command=cmd, width=120,
                            height=34, bg="#3A4256", fg="#EDEFF4")

    def _build(self):
        self.canvas = tk.Canvas(self, bg="#1F2430", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw())

        bar = tk.Frame(self, bg="#1F2430")
        bar.pack(fill="x", padx=8, pady=6)
        # 播放/暂停 + 手动步进
        self.btn_play = self._mk_btn(bar, "▶ 自动播放", self._toggle_play)
        self.btn_play.pack(side="left", padx=2)
        self._mk_btn(bar, "⏮ 开头", lambda: self._goto(0)).pack(side="left", padx=2)
        self._mk_btn(bar, "◀ 上一步", lambda: self._step(-1)).pack(side="left", padx=2)
        self._mk_btn(bar, "下一步 ▶", lambda: self._step(1)).pack(side="left", padx=2)
        self._mk_btn(bar, "⏭ 结尾", lambda: self._goto(len(self.moves))).pack(side="left", padx=2)

        # 播放速度（复盘默认可调慢，不赶）
        tk.Label(bar, text="速度", bg="#1F2430", fg="#9AA3B2",
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(10, 2))
        speed_var = tk.StringVar(value="较慢")
        speed_cbo = ttk.Combobox(bar, textvariable=speed_var,
                                 values=[n for n, _ in SPEEDS],
                                 state="readonly", width=5,
                                 font=("Microsoft YaHei UI", 10))
        speed_cbo.pack(side="left", padx=(0, 4))
        speed_cbo.bind("<<ComboboxSelected>>",
                       lambda e: self._set_speed(speed_var.get()))

        self.info = tk.Label(self, text="", bg="#1F2430", fg="#E8B34B",
                             font=("Microsoft YaHei UI", 12))
        self.info.pack(fill="x", padx=12, pady=(0, 8))

    def _set_speed(self, label: str):
        self.speed = dict(SPEEDS).get(label, DEFAULT_SPEED)

    def _cancel_job(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _toggle_play(self):
        self.playing = not self.playing
        self.btn_play.set_text("⏸ 暂停" if self.playing else "▶ 自动播放")
        if self.playing:
            if self.step_i >= len(self.moves):
                self.step_i = 0
                self.b = Board(self._bsize, self._bwin)
            self._schedule()
        else:
            self._cancel_job()

    def _schedule(self):
        if not self.playing:
            return
        if self.step_i >= len(self.moves):
            self.playing = False
            self.btn_play.set_text("▶ 自动播放")
            return
        self._job = self.after(self.speed, self._advance_once)

    def _advance_once(self):
        if not self.playing:
            return
        if self._apply_forward():
            self._draw()
            self._schedule()

    def _step(self, d):
        self.playing = False
        self._cancel_job()
        self.btn_play.set_text("▶ 自动播放")
        if d > 0:
            self._apply_forward()
        else:
            self._rewind()
        self._draw()

    def _goto(self, idx):
        self.playing = False
        self._cancel_job()
        self.btn_play.set_text("▶ 自动播放")
        self.b = Board(self._bsize, self._bwin)
        for m in self.moves[:idx]:
            self.b.place(m[0], m[1], m[2])
        self.step_i = idx
        self._draw()

    def _apply_forward(self) -> bool:
        if self.step_i >= len(self.moves):
            return False
        x, y, c = self.moves[self.step_i]
        self.b.place(x, y, c)
        self.step_i += 1
        return True

    def _rewind(self):
        if self.step_i <= 0:
            return
        self.step_i -= 1
        self.b = Board(self._bsize, self._bwin)
        for m in self.moves[:self.step_i]:
            self.b.place(m[0], m[1], m[2])

    def _draw(self):
        c = self.canvas
        c.delete("all")
        W = max(c.winfo_width(), 1); H = max(c.winfo_height(), 1)
        t = self.theme
        side = min(W, H) - 24
        if side < 40:
            return
        off = (min(W, H) - side) / 2
        x0, y0 = off, off
        x1, y1 = off + side, off + side
        for i in range(16):
            yy = y0 + (y1 - y0) * i / 15
            yy2 = y0 + (y1 - y0) * (i + 1) / 15 + 1
            c.create_rectangle(x0, yy, x1, yy2, fill="#C8A87A", outline="")
        n = self.b.size
        cell = side / (n - 1)
        for i in range(n):
            p = y0 + i * cell
            c.create_line(x0, p, x1, p, fill="#4A3B28")
            c.create_line(p, y0, p, y1, fill="#4A3B28")
        # 星位
        for sy in (3, n // 2, n - 4):
            for sx in (3, n // 2, n - 4):
                cx = x0 + sx * cell; cy = y0 + sy * cell
                c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#4A3B28")
        for (x, y, col) in self.b.history:
            cx = x0 + x * cell; cy = y0 + y * cell
            r = cell * 0.42
            body = "#1B1E23" if col == BLACK else "#F5F5F0"
            edge = "#000000" if col == BLACK else "#8A8A8A"
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=body, outline=edge)
        # 信息
        res = self.record.get("result", "")
        if self.step_i >= len(self.moves) and res in ("BLACK", "WHITE", "DRAW"):
            txt = {"BLACK": "黑方获胜", "WHITE": "白方获胜", "DRAW": "平局"}.get(res, "")
            self.info.config(text=f"{txt}  ·  共 {len(self.moves)} 手")
        else:
            self.info.config(text=f"第 {self.step_i} / {len(self.moves)} 手")
