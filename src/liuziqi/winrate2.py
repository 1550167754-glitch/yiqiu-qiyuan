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
# 4/5. 蒙特卡洛：启发式 rollout 自对弈统计黑方胜率（全局胜率主信号）
# ----------------------------------------------------------------------
# 依据 AlphaGo value network 的核心思想：胜率 = 从当前局面出发、双方按
# 某种"近似合理"策略下到终局，最终获胜的概率。纯随机 rollout 双方都极弱、
# 方差巨大（每步 noise 大、单点独立抖动），故改为"启发式 rollout"——
# 优先走强手/堵对方强手，使模拟更接近真实对局、方差大幅下降，曲线稳定可信。
#
# 强手优先级（每步，先"我能赢/必须堵"，再"造威胁/防威胁"，最后随机）：
#   1. 己方一手成五（立即胜）；
#   2. 堵对方一手成五（唯一/最优先）；
#   3. 己方走成活四 / 冲四；
#   4. 堵对方活四 / 冲四；
#   5. 己方走成活三；
#   6. 其余空点随机。
_HEURISTIC_DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))


def _count_dir(grid, n, x, y, dx, dy, color):
    """(x,y) 处沿 (dx,dy) 若落 color，连成的最长连续子数（含该点）。"""
    cnt = 1
    i, j = x + dx, y + dy
    while 0 <= i < n and 0 <= j < n and grid[j][i] == color:
        cnt += 1
        i += dx
        j += dy
    i, j = x - dx, y - dy
    while 0 <= i < n and 0 <= j < n and grid[j][i] == color:
        cnt += 1
        i -= dx
        j -= dy
    return cnt


def _best_move_after(board, color, rng, cands):
    """启发式 rollout 的单步选点：返回落点 (x, y)。

    按强手优先级降级选择；同类之间用 rng 随机，保证模拟有多样性
    （否则整局每个分支都走同一手，退化成一条确定路径、方差反而爆炸）。
    """
    n = board.size
    g = board.grid
    wc = board.win_count
    foe = OPPOSITE[color]

    win = []       # 己方一手成五
    block5 = []    # 堵对方一手成五
    make4 = []     # 己方活四/冲四
    block4 = []    # 堵对方活四/冲四
    make3 = []     # 己方活三
    rest = []
    for (x, y) in cands:
        if g[y][x] != EMPTY:
            continue
        # 己方落子后的棋力
        my_best = max(_count_dir(g, n, x, y, dx, dy, color) for dx, dy in _HEURISTIC_DIRS)
        if my_best >= wc:
            win.append((x, y))
            continue
        # 对方若落此点的棋力（堵的意义 = 对方在此会变强）
        foe_best = max(_count_dir(g, n, x, y, dx, dy, foe) for dx, dy in _HEURISTIC_DIRS)
        if foe_best >= wc:
            block5.append((x, y))
            continue
        # 己方能否形成活四/冲四（连 wc-1 及以上）
        if my_best >= wc - 1:
            make4.append((x, y))
            continue
        # 对方是否会因此成活四/冲四 → 需要堵
        if foe_best >= wc - 1:
            block4.append((x, y))
            continue
        # 己方活三
        if my_best >= wc - 2:
            make3.append((x, y))
            continue
        rest.append((x, y))

    for pool in (win, block5, make4, block4, make3, rest):
        if pool:
            return pool[rng.randrange(len(pool))]
    return None


def mc_black_winrate(board: Board, sims: int = 5000,
                     time_budget: float = 3.0, seed: int | None = None) -> float:
    """从当前局面做启发式 rollout 自对弈到终局，统计黑方胜率。

    这是"纵观全局"的胜率主信号：不是看当前一步的局部优势，而是统计
    "从此刻起、双方近似合理对弈到终局，黑方最终获胜的比例"。

    安全实现：
        - 仅 snapshot() 一次创建工作棋盘，之后全程 place/undo 复用，
          不复制海量棋盘对象（杜绝内存爆炸）；
        - time_budget 兜底，超时提前返回当前统计（避免卡后台线程太久）；
        - 当前局面已见胜负时直接返回，不空耗模拟。
    注意：只读 board，不改动调用方传入的棋盘。
    """
    n = board.size
    # 当前局面若已见胜负（最后一手连成），直接判黑方。
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
                mv = _best_move_after(work, side, rng, cands)
                if mv is None:
                    break
                px, py = mv
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
# 6. 搜索校正：把对局方 negamax 分值换算成黑方胜率（仅作先验微调）
# ----------------------------------------------------------------------
# 依据：胜率主信号是蒙特卡洛（真正"纵观全局"）。搜索分值只用来给 MC 一个
# 先验、加速收敛 / 降低单点噪声，不再直接当作胜率输出。
# last_val 量级来自 ai._Eval（活三 6000 / 冲四 20000 / 活四 60000 / 连五 1e7），
# 旧实现用一刀切 _SCALE=26000 的 sigmoid 硬压，导致"一个活四就 91%、连五顶 98%"
# 完全不成比例。改为分段线性标定，贴合棋型分值的实际含义。
_SCORE_STOPS = (
    (0.0,       0.50),   # 均势
    (6000.0,    0.62),   # 活三级别
    (20000.0,   0.78),   # 冲四级别
    (60000.0,   0.90),   # 活四级别
    (500000.0,  0.97),   # 五连开放
    (1000000.0, 0.99),   # 接近必胜
)


def _calibrate_score(s: float) -> float:
    """把搜索分值 s（越大对黑越有利，可正可负）分段线性标定为胜率。

    负分（白优）按对称表镜像到 [0, 0.5)：先取绝对值走正向标定，再取 1-p。
    """
    if s >= 0:
        if s >= _SCORE_STOPS[-1][0]:
            return _SCORE_STOPS[-1][1]
        for (s0, p0), (s1, p1) in zip(_SCORE_STOPS, _SCORE_STOPS[1:]):
            if s <= s1:
                return p0 + (p1 - p0) * (s - s0) / (s1 - s0)
        return _SCORE_STOPS[-1][1]
    # 负分：镜像
    p_neg = _calibrate_score(-s)
    return 1.0 - p_neg


def search_score_to_black(search_score: float, mover: int, board: Board) -> float:
    """把对局方(mover)的 negamax 分值换算为黑方胜率。

    search_score 越大 mover 越有利。若 mover==黑，score 越高黑越好；mover==白则反向。
    仅作先验：主信号是蒙特卡洛，此值不直接顶替曲线点。
    """
    if board is not None and board.move_count == 0:
        return 0.5
    s = float(search_score)
    if mover != BLACK:
        s = -s
    return _clamp(_calibrate_score(s))
