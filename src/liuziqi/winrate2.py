# -*- coding: utf-8 -*-
"""
winrate2.py —— 六子棋胜率 6 阶段增量引擎（内存安全版）

设计目标：UI 每落一子，曲线点先给"快速估计"，再被"异步蒙特卡洛"、"搜索校正"
逐级刷新，数值越来越准，同时绝不撑爆内存（<=16G 环境也安全）。

阶段映射（对应 UI 需求）：
    1. 路评分 S     —— line_score：滑窗静态分，O(线×窗)，约微秒级；
    2. 威胁差       —— threat_diff：双方"活三/冲四/活四"等威胁的加权差；
    3. 快速映射     —— fast_black_winrate：把 (S, 威胁差) 用 sigmoid 合成黑方胜率，
                      由 GUI 即时写入曲线（点 1）；
    4. 蒙特卡洛     —— mc_black_winrate：后台线程跑 N 次随机对局，只复用 1 块临时棋盘
                      (snapshot 一次 + place/undo)，不复制成百上千份棋盘；
    5. 蒙特卡洛结果 —— 由 GUI 回调把点 2 覆写到曲线；
    6. 搜索校正     —— search_score_to_black：把对局方 negamax 搜索分值换算成黑方
                      胜率，GUI 并入"已有 AI 搜索"结果（不额外起搜索）。

胜率约定：一律返回黑方胜率 (0.0, 1.0)；白方=1-黑方。
蒙特卡洛：从当前局面随机自对弈到终局，统计黑方胜局占比。局面已分出胜负时直接返回
(0/1)，不浪费模拟。
"""
from __future__ import annotations

import math
import random

from .board import BLACK, WHITE, EMPTY, OPPOSITE, Board
from .ai import _Eval, WIN_SCORE

_FLOOR = 0.02
_CEIL = 0.98

# 威胁当量（与 ai.py 棋型分值一致的量级，仅用于威胁差排序/加权）
_T_LIVE_FOUR = 60_000
_T_FOUR = 12_000
_T_LIVE_THREE = 6_000
_T_THREE = 900
_T_LIVE_TWO = 450

# sigmoid 缩放基数：让"威胁差"这类大数被温和压回 0~1，
# 避免曲线在中盘过早贴死 0/100（饱和会丢失区分度、观感突兀）。
_SCALE = 26_000.0

_DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))


def _clamp(p: float) -> float:
    if math.isnan(p) or math.isinf(p):
        return 0.5
    return max(_FLOOR, min(_CEIL, p))


def _sigmoid(x: float) -> float:
    """数值安全 sigmoid：避免 math.exp 大正数溢出抛 OverflowError。

    正侧用 1/(1+e^-x)；负侧用 e^x/(1+e^x)，两者都不产生大数 exp。
    NaN/Inf 一律回退到 0.5（中性地平），保证曲线稳定不出错。
    """
    if math.isnan(x) or math.isinf(x):
        return 0.5
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)   # x<0，安全
    return e / (1.0 + e)


# ----------------------------------------------------------------------
# 1. 路评分 S（黑 vs 白 的滑窗静态分差）
# ----------------------------------------------------------------------
def line_score(board: Board, color: int = BLACK) -> int:
    """滑窗静态分：color 侧所有『己方子、无对手子』六格窗得分之和。

    用 ai._Eval 的增量结构快速取两色总分，差即当前"路分差"。
    """
    ev = _Eval(board)
    return ev.score[color] - ev.score[OPPOSITE[color]]


# ----------------------------------------------------------------------
# 2. 威胁差
# ----------------------------------------------------------------------
def _segments(board: Board, color: int):
    """枚举 color 侧每条线内的连续同色段 (长度, 开放端数)。仅统计段首一次，避免重复。"""
    n = board.size
    g = board.grid
    for dx, dy in _DIRS:
        # 枚举所有平行线的起点
        starts = []
        if dx == 1 and dy == 0:
            starts = [(0, y) for y in range(n)]
        elif dx == 0 and dy == 1:
            starts = [(x, 0) for x in range(n)]
        elif dx == 1 and dy == 1:
            starts = [(0, k) for k in range(n)] + [(k, 0) for k in range(1, n)]
        else:
            starts = [(k, n - 1) for k in range(n)] + [(0, k) for k in range(n - 1)]
        for sx, sy in starts:
            i, j = sx, sy
            while 0 <= i < n and 0 <= j < n:
                if g[j][i] == color:
                    # 段首
                    seg = 0
                    ii, jj = i, j
                    while 0 <= ii < n and 0 <= jj < n and g[jj][ii] == color:
                        seg += 1
                        ii += dx
                        jj += dy
                    opens = 0
                    # 真正的两端坐标：段头 (i,j) 前一个点、段尾 (ii,jj)
                    for ex, ey in ((i - dx, j - dy), (ii, jj)):
                        if 0 <= ex < n and 0 <= ey < n and g[ey][ex] == EMPTY:
                            opens += 1
                    yield (seg, opens)
                    i, j = ii, jj
                else:
                    i += dx
                    j += dy


def _segment_value(seg: int, opens: int) -> int:
    """把一段 (长度, 开放端数) 折算为威胁当量。"""
    if seg >= 6:
        return WIN_SCORE
    if seg == 5:
        return _T_FOUR if opens else 0
    if seg == 4:
        return _T_LIVE_FOUR if opens >= 2 else (_T_FOUR if opens == 1 else 0)
    if seg == 3:
        return _T_LIVE_THREE if opens >= 2 else (_T_THREE if opens == 1 else 0)
    if seg == 2:
        return _T_LIVE_TWO if opens >= 2 else 0
    return 0


def threat_diff(board: Board, color: int = BLACK) -> int:
    """威胁差 = color 侧威胁当量 - 对手侧威胁当量。"""
    mine = sum(_segment_value(s, o) for s, o in _segments(board, color))
    opp = sum(_segment_value(s, o) for s, o in _segments(board, OPPOSITE[color]))
    return mine - opp


# ----------------------------------------------------------------------
# 3. 快速映射 → 黑方胜率（合并 S 与威胁差，sigmoid）
# ----------------------------------------------------------------------
def fast_black_winrate(board: Board) -> float:
    if board.move_count == 0:
        return 0.5
    # 终局直接给准值：黑胜 1 / 白胜 0 / 平局 0.5
    if board.move_count:
        lx, ly, lc = board.history[-1]
        if board.check_win(lx, ly) is not None:
            return 1.0 if lc == BLACK else 0.0
    S = line_score(board)
    T = threat_diff(board)
    # S、T 单位不同：把威胁差用 _SCALE 主控，静态分只作微调
    score = float(T) + float(S) * 0.5
    p = _sigmoid(score / _SCALE)
    return _clamp(p)


# ----------------------------------------------------------------------
# 4/5. 蒙特卡洛：随机自对弈统计黑方胜率（内存安全：只复用 1 块临时棋盘）
# ----------------------------------------------------------------------
def mc_black_winrate(board: Board, sims: int = 300,
                     time_budget: float = 0.3, seed: int | None = None) -> float:
    """从当前局面随机走子到终局，统计黑方胜率。

    安全实现：
        - 仅 snapshot() 一次创建工作棋盘，之后随机走子全程 place/undo 复用，
          不复制成百上千份棋盘对象（杜绝内存爆炸）；
        - 加入 time_budget 兜底，超时就提前返回当前统计（避免卡线程太久）；
        - 当前局面已见胜负时直接返回，不空耗模拟。
    注意：只读 board，不改动调用方传入的棋盘。
    """
    n = board.size
    # 当前局面若已见胜负（最后一手连六），直接判黑方，避免空耗模拟。
    if board.move_count:
        lx, ly, _ = board.history[-1]
        if board.check_win(lx, ly) is not None:
            return 1.0 if board.history[-1][2] == BLACK else 0.0

    work = board.snapshot()          # 只复制 1 次
    rng = random.Random(seed)
    import time as _time
    deadline = time_budget if time_budget and time_budget > 0 else 1e9
    start = _time.monotonic()
    black_wins = 0.0
    done = 0
    sims = max(1, int(sims))
    base = work.move_count          # 每次模拟结束后撤销回这个深度

    for _ in range(sims):
        if _time.monotonic() - start > deadline:
            break
        side = BLACK
        winner = None
        while work.move_count < n * n:
            cands = work.get_candidates(radius=1)
            if not cands:
                cands = work.get_candidates(radius=2)
            if not cands:
                break
            # 黑首轮只下 1 子；其余轮 1~2 子（60% 概率下满）
            is_first_black = (side == BLACK and work.move_count == base)
            need = 1 if is_first_black else (1 if rng.random() < 0.4 else 2)
            for _k in range(need):
                if work.move_count >= n * n:
                    break
                cands = work.get_candidates(radius=1)
                if not cands:
                    cands = work.get_candidates(radius=2)
                if not cands:
                    break
                px, py = rng.choice(cands)
                work.place(px, py, side)
                if work.check_win(px, py) is not None:
                    winner = side
                    break
            if winner is not None:
                break
            side = OPPOSITE[side]
        # 统计：黑胜 +1，白胜 +0，满盘平局 +0.5
        if winner == BLACK:
            black_wins += 1.0
        elif winner is None:
            black_wins += 0.5
        done += 1
        # 回滚本局所有临时落子（撤销回 base，复用同一块棋盘）
        while work.move_count > base:
            work.undo()
        if done >= sims:
            break

    if done == 0:
        return fast_black_winrate(board)
    return _clamp(black_wins / done)


# ----------------------------------------------------------------------
# 6. 搜索校正：把对局方 negamax 分值换算成黑方胜率
# ----------------------------------------------------------------------
def search_score_to_black(search_score: float, mover: int, board: Board) -> float:
    """把对局方(mover)的 negamax 分值换算为黑方胜率。

    search_score 越大 mover 越有利。若 mover==黑，score 越高黑越好；mover==白则反向。
    """
    if board is not None and board.move_count == 0:
        return 0.5
    s = float(search_score)
    if mover != BLACK:
        s = -s
    p = _sigmoid(s / _SCALE)
    return _clamp(p)
