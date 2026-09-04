# -*- coding: utf-8 -*-
"""
ai.py —— 本地 AI 引擎（medium 难度重点强化版）

一、基础搜索（地基）
    1. 极大极小值（Negamax 形式实现，等价于 Minimax）
    2. Alpha-Beta 剪枝
    3. Principal Variation Search（PVS，零窗口试探 + 失败重搜）

二、六子棋核心
    4. 威胁空间搜索 TSS：
       - 必胜点检测（一手成六 / 双威胁点）
       - 强制防守约束（对手有冲六威胁时，搜索只沿防守点展开）
       - 冲四连击搜索（VCF 风格：只沿"产生成六点"的着法递归）

三、性能加速（外挂）
    7. 置换表：Zobrist 哈希 + 深度优先替换
    8. 走法排序：置换表最佳走法 > 威胁等级 > 历史启发 > 杀手走法
    9. 迭代加深：逐层加深，超时即返回上一层最佳结果
"""
from __future__ import annotations

import random
import time

from .board import BLACK, EMPTY, OPPOSITE, WHITE, Board

# ----------------------------------------------------------------------
# 棋型分值
# ----------------------------------------------------------------------
WIN_SCORE = 10_000_000          # 已成六连
FIVE_OPEN = 500_000             # 五连且至少一端开放（下一手必胜）
FOUR_OPEN = 60_000              # 活四（两个成六点）
FOUR_SIMPLE = 12_000            # 冲四（一个成六点）
THREE_OPEN = 6_000              # 活三
THREE_SIMPLE = 900              # 眠三
TWO_OPEN = 450                  # 活二
TWO_SIMPLE = 80                 # 眠二

# 滑窗打分表：窗口内己方 k 子（对手 0 子）时的基础分
WINDOW_SCORE = {0: 0, 1: 2, 2: 24, 3: 620, 4: 8_400, 5: 120_000, 6: WIN_SCORE}

INF = float("inf")

# ----------------------------------------------------------------------
# Zobrist 哈希
# ----------------------------------------------------------------------
_RNG = random.Random(0x636F6E6E65633636)   # 固定种子，保证可复现
ZOBRIST = {}                                # (x, y, color) -> 64bit
for _y in range(19):
    for _x in range(19):
        for _c in (BLACK, WHITE):
            ZOBRIST[(_x, _y, _c)] = _RNG.getrandbits(64)
TURN_KEY = {                                # 轮次状态附加键
    (BLACK, 1): _RNG.getrandbits(64),
    (BLACK, 2): _RNG.getrandbits(64),
    (WHITE, 1): _RNG.getrandbits(64),
    (WHITE, 2): _RNG.getrandbits(64),
}

TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2


# ----------------------------------------------------------------------
# 威胁检测工具
# ----------------------------------------------------------------------
def _win_points(board: Board, color: int,
                cands=None) -> list[tuple[int, int]]:
    """找出 color 落一子即成六连的所有点。"""
    pts = []
    n = board.size
    grid = board.grid
    rng = cands if cands is not None else [
        (x, y) for y in range(n) for x in range(n) if grid[y][x] == EMPTY]
    for (x, y) in rng:
        if grid[y][x] != EMPTY:
            continue
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
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
            if cnt >= 6:
                pts.append((x, y))
                break
    return pts


def _five_open_ends(board: Board, color: int) -> list[tuple[int, int]]:
    """color 已有五连的空端点列表（对手下一手即可成六）。"""
    n = board.size
    grid = board.grid
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        for y in range(n):
            for x in range(n):
                if grid[y][x] != color:
                    continue
                # 找以 (x,y) 为起点、方向 (dx,dy) 的连续段
                px, py = x - dx, y - dy
                if 0 <= px < n and 0 <= py < n and grid[py][px] == color:
                    continue  # 不是段首
                seg = 0
                i, j = x, y
                while 0 <= i < n and 0 <= j < n and grid[j][i] == color:
                    seg += 1
                    i += dx
                    j += dy
                if seg != 5:
                    continue
                ends = []
                bx, by = x - dx, y - dy
                ex, ey = i, j
                if 0 <= bx < n and 0 <= by < n and grid[by][bx] == EMPTY:
                    ends.append((bx, by))
                if 0 <= ex < n and 0 <= ey < n and grid[ey][ex] == EMPTY:
                    ends.append((ex, ey))
                if ends:
                    return ends
    return []


# ----------------------------------------------------------------------
# 增量评估器（滑窗法）
# ----------------------------------------------------------------------
class _Eval:
    """以 6 格滑窗对每条线打分；place/undo 只重算受影响的线。"""

    DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))

    def __init__(self, board: Board):
        self.board = board
        self.n = board.size
        self.score = {BLACK: 0, WHITE: 0}
        self._line_map = {}   # (x, y) -> [(dir, line_id), ...]
        self._lines = {}      # (dir, line_id) -> list[(x, y)]
        self._build_lines()
        for c in (BLACK, WHITE):
            self.score[c] = self._eval_all(c)

    def _build_lines(self):
        n = self.n
        for d, (dx, dy) in enumerate(self.DIRS):
            if dx == 1 and dy == 0:
                starts = [(0, y) for y in range(n)]
            elif dx == 0 and dy == 1:
                starts = [(x, 0) for x in range(n)]
            elif dx == 1 and dy == 1:
                starts = [(0, k) for k in range(n)] + \
                         [(k, 0) for k in range(1, n)]
            else:
                starts = [(k, n - 1) for k in range(n)] + \
                         [(0, k) for k in range(n - 1)]
            for li, (sx, sy) in enumerate(starts):
                pts = []
                i, j = sx, sy
                while 0 <= i < n and 0 <= j < n:
                    pts.append((i, j))
                    self._line_map.setdefault((i, j), []).append((d, li))
                    i += dx
                    j += dy
                self._lines[(d, li)] = pts

    def _line_score(self, pts, color: int) -> int:
        grid = self.board.grid
        m = len(pts)
        total = 0
        for s in range(m - 5):
            mine = 0
            opp = 0
            for k in range(s, s + 6):
                v = grid[pts[k][1]][pts[k][0]]
                if v == color:
                    mine += 1
                elif v != EMPTY:
                    opp += 1
            if opp == 0:
                total += WINDOW_SCORE[mine]
        return total

    def _eval_all(self, color: int) -> int:
        return sum(self._line_score(pts, color)
                   for pts in self._lines.values())

    def place(self, x: int, y: int, color: int):
        b = self.board
        affected = self._line_map[(x, y)]
        for (d, li) in affected:            # 先减旧分（旧棋盘）
            pts = self._lines[(d, li)]
            for c in (BLACK, WHITE):
                self.score[c] -= self._line_score(pts, c)
        b.grid[y][x] = color                # 落子
        b.move_count += 1
        b.history.append((x, y, color))
        for (d, li) in affected:            # 再加新分（新棋盘）
            pts = self._lines[(d, li)]
            for c in (BLACK, WHITE):
                self.score[c] += self._line_score(pts, c)

    def undo(self):
        b = self.board
        x, y, _c = b.history.pop()
        affected = self._line_map[(x, y)]
        for (d, li) in affected:
            pts = self._lines[(d, li)]
            for c in (BLACK, WHITE):
                self.score[c] -= self._line_score(pts, c)
        b.grid[y][x] = EMPTY                # 撤子
        b.move_count -= 1
        for (d, li) in affected:
            pts = self._lines[(d, li)]
            for c in (BLACK, WHITE):
                self.score[c] += self._line_score(pts, c)

    def evaluate(self, color: int) -> int:
        """color 视角的局面分。

        进攻节奏设计（避免"只会堵着续命"）：
            - 己方子分权重 1.10（略高于对手），鼓励 AI 主动发展己方活三/活四威胁，
              而不是一直被动拆招；
            - 对手分权重 1.0；真正的一手成六/冲六仍由外层强制防守逻辑兜底，
              故这里的"轻攻"不会让 AI 漏守致命威胁。
        """
        return int(self.score[color] * 1.10) - self.score[OPPOSITE[color]]


# ----------------------------------------------------------------------
# 主引擎
# ----------------------------------------------------------------------
class AlphaBetaEngine:
    """迭代加深 + PVS + 置换表 + 威胁空间搜索。"""

    def __init__(self, max_depth: int = 8, time_limit: float = 2.5,
                 candidate_limit: int = 14, pair_top: int = 6, seed=None):
        self.max_depth = max_depth
        self.time_limit = time_limit
        self.candidate_limit = candidate_limit
        self.pair_top = pair_top
        self.seed = seed
        self.nodes = 0
        self.deadline = 0.0
        self.tt: dict[int, tuple] = {}
        self.history: dict[tuple, int] = {}
        self.killers: dict[int, list] = {}
        self._stop = False
        self._tss_nodes = 0
        self.last_val = 0.0   # 最近一次搜索的根结点分值（供 GUI 胜率校正）

    # ------------------------------------------------------------------
    def best_move(self, board: Board, color: int,
                  stones_to_place: int) -> list[tuple[int, int]]:
        """入口：返回本轮要落的 1~2 个点。"""
        self.nodes = 0
        self.tt.clear()
        self.history.clear()
        self.killers.clear()
        self.deadline = time.monotonic() + self.time_limit
        self._stop = False

        # 关键：全程在快照上搜索，任何中途超时 / 异常都不会污染真实棋盘
        board = board.snapshot()
        cands = self._gen_candidates(board, color)

        # ---------- 1. 己方一手成六 ----------
        win_pts = _win_points(board, color, cands)
        if win_pts:
            if stones_to_place == 2:
                p = win_pts[0]
                board.place(p[0], p[1], color)
                more = _win_points(board, color, cands)
                board.undo()
                if more:
                    return [p, more[0]]
            return [win_pts[0]]

        # ---------- 2. 对手威胁 → 强制防守 ----------
        opp = OPPOSITE[color]
        five_ends = _five_open_ends(board, opp)
        if five_ends:
            if len(five_ends) == 2 and stones_to_place == 2:
                return five_ends                       # 正好两端各堵一子
            return [five_ends[0]]
        opp_win = _win_points(board, opp, cands)
        if opp_win:
            if stones_to_place == 2 and len(opp_win) >= 2:
                # 两个冲六点：两子分别堵上（按我方价值排序）
                a, b2 = opp_win[0], opp_win[1]
                return [a, b2]
            p = opp_win[0]
            if stones_to_place == 2:
                # 堵一个后，为第二子重新挑（堵完可能又出现新威胁）
                board.place(p[0], p[1], color)
                new_opp = _win_points(board, opp, cands)
                if new_opp:
                    board.undo()
                    return [p, new_opp[0]]
                rest = [q for q in cands if q != p]
                scored = self._score_candidates(board, color, rest)
                p2 = scored[0][0] if scored else (p[0], p[1] + 1)
                board.undo()
                return [p, p2]
            return [p]

        # ---------- 3. TSS：冲四连击找强制胜 ----------
        seq = self._threat_search(board, color, stones_to_place)
        if seq:
            return seq[:stones_to_place]

        # ---------- 4. 迭代加深 + PVS ----------
        if board.move_count == 0:
            c = board.size // 2
            self.last_val = 0.0
            return [(c, c)]

        pool = [p for p, _s in
                self._score_candidates(board, color, cands)[: self.candidate_limit * 3]]
        ev = _Eval(board)
        best = None
        self.last_val = 0.0
        for depth in range(2, self.max_depth + 1, 2):
            best_this = None
            best_val = -INF
            alpha, beta = -INF, INF
            try:
                for i, p in enumerate(pool):
                    ev.place(p[0], p[1], color)
                    if stones_to_place == 1:
                        val = -self._alphabeta(ev, opp, 2, depth - 1,
                                               -beta, -alpha, 1)
                    else:
                        val = self._alphabeta(ev, color, 1, depth - 1,
                                              alpha, beta, 1)
                    ev.undo()
                    if self._stop:
                        raise TimeoutError
                    if best_val == -INF or val > best_val:
                        best_val = val
                        best_this = [p]
                    if val > alpha:
                        alpha = val
            except TimeoutError:
                break
            if best_this and not self._stop:
                best = best_this
                self._root_best = best
                self.last_val = float(best_val)
            if best_val >= WIN_SCORE // 2:
                break
            if time.monotonic() >= self.deadline:
                break

        if not best:
            best = [pool[0]]
        if stones_to_place == 2 and len(best) == 1:
            p1 = best[0]
            ev.place(p1[0], p1[1], color)
            rest = [q for q in pool if q != p1]
            p2 = self._pick_second(board, color, rest)
            ev.undo()
            best.append(p2)
        return best

    # ------------------------------------------------------------------
    # PVS + Alpha-Beta（Negamax）
    # ------------------------------------------------------------------
    def _alphabeta(self, ev: _Eval, color: int, remain: int, depth: int,
                   alpha: float, beta: float, ply: int) -> float:
        if self._stop or ((self.nodes & 255) == 0
                          and time.monotonic() >= self.deadline):
            self._stop = True
            raise TimeoutError
        self.nodes += 1

        board = ev.board
        alpha_orig = alpha

        # ---- 置换表查询 ----
        key = self._hash(board, color, remain)
        entry = self.tt.get(key)
        tt_move = None
        if entry is not None:
            e_depth, e_flag, e_val, e_move = entry
            tt_move = e_move
            if e_depth >= depth:
                if e_flag == TT_EXACT:
                    return e_val
                if e_flag == TT_LOWER and e_val >= beta:
                    return e_val
                if e_flag == TT_UPPER and e_val <= alpha:
                    return e_val

        # ---- 静态返回 ----
        if depth <= 0:
            return ev.evaluate(color)

        cands = self._gen_candidates(board, color)

        # ---- 己方一手成六：直接赢 ----
        my_wins = _win_points(board, color, cands)
        if my_wins:
            return WIN_SCORE - ply

        # ---- 对手威胁：强制防守 ----
        opp = OPPOSITE[color]
        opp_win = _win_points(board, opp, cands)
        if opp_win:
            blockset = set(opp_win)
            scored = [(p, 0) for p in opp_win]
        else:
            scored = self._score_candidates(board, color, cands,
                                            tt_move=tt_move, ply=ply)
            scored = scored[: self.candidate_limit]

        best_val = -INF
        best_move = None
        first = True
        for (p, _s) in scored:
            ev.place(p[0], p[1], color)
            r2 = remain - 1
            if r2 == 0:
                val = -self._alphabeta(ev, opp, 2, depth - 1,
                                       -beta, -alpha, ply + 1)
            elif first:
                val = self._alphabeta(ev, color, r2, depth - 1,
                                      alpha, beta, ply + 1)
            else:
                # PVS 零窗口试探
                val = self._alphabeta(ev, color, r2, depth - 1,
                                      -alpha - 1, -alpha, ply + 1)
                if alpha < val < beta:
                    val = self._alphabeta(ev, color, r2, depth - 1,
                                          -beta, -val, ply + 1)
            ev.undo()
            if self._stop:
                raise TimeoutError
            if best_val == -INF or val > best_val:
                best_val = val
                best_move = p
            if val > alpha:
                alpha = val
            first = False
            if alpha >= beta:
                if remain == 2:
                    ks = self.killers.setdefault(ply, [])
                    if p not in ks:
                        ks.insert(0, p)
                        del ks[2:]
                self.history[(color, p[0], p[1])] = \
                    self.history.get((color, p[0], p[1]), 0) + depth * depth
                break

        # ---- 写置换表（深度优先替换）----
        if not self._stop and best_move is not None:
            if best_val <= alpha_orig:
                flag = TT_UPPER
            elif best_val >= beta:
                flag = TT_LOWER
            else:
                flag = TT_EXACT
            old = self.tt.get(key)
            if old is None or old[0] <= depth:
                self.tt[key] = (depth, flag, best_val, best_move)
        return best_val

    # ------------------------------------------------------------------
    # 威胁空间搜索（VCF 风格）
    # ------------------------------------------------------------------
    def _threat_search(self, board: Board, color: int,
                       stones_to_place: int):
        """找一条由"成六点威胁"组成的强制胜序列，返回前几步落点。"""
        self._tss_nodes = 0
        seq: list[tuple[int, int]] = []
        if self._tss(board, color, stones_to_place, 10, seq):
            return seq
        return None

    def _tss(self, board: Board, color: int, remain: int,
             budget: int, seq: list) -> bool:
        if budget <= 0 or self._tss_nodes > 6000:
            return False
        self._tss_nodes += 1
        if time.monotonic() >= self.deadline:
            return False
        opp = OPPOSITE[color]
        cands = self._gen_candidates(board, color)
        wins = _win_points(board, color, cands)
        if wins:
            seq.append(wins[0])
            if remain == 2:
                for q in cands:
                    if q != wins[0]:
                        seq.append(q)
                        break
                else:
                    c = board.size // 2
                    alt = (c, c) if (c, c) != wins[0] else (c + 1, c)
                    seq.append(alt)
            return True

        if remain == 2:
            # 第一子从强威胁点里挑，继续以 remain=1 递归
            for p, _s in self._score_candidates(board, color, cands)[:8]:
                if board.grid[p[1]][p[0]] != EMPTY:
                    continue
                board.place(p[0], p[1], color)
                sub_seq = [p]
                ok = self._tss(board, color, 1, budget - 1, sub_seq)
                board.undo()
                if ok:
                    seq.extend(sub_seq)
                    return True
            return False

        # remain == 1：找能制造成六点的着法（冲四/活四）
        threats = []
        for p, _s in self._score_candidates(board, color, cands)[:12]:
            board.place(p[0], p[1], color)
            wins2 = _win_points(board, color)
            board.undo()
            if wins2:
                threats.append((p, len(wins2)))
        threats.sort(key=lambda t: -t[1])
        for p, nwins in threats:
            board.place(p[0], p[1], color)
            wins2 = _win_points(board, color)
            if len(wins2) >= 3:
                # 三重威胁，对手两手堵不完 → 必胜
                board.undo()
                seq.append(p)
                return True
            # 对手被迫堵全部成六点（最多 2 个），其另一子任意
            blocks_needed = wins2[:2]
            if len(wins2) == 1:
                b1 = blocks_needed[0]
                board.place(b1[0], b1[1], opp)
                rest = [q for q in cands if q != b1 and q != p]
                opp2 = self._score_candidates(board, opp, rest)
                b2 = opp2[0][0] if opp2 else None
                if b2 is None or not board.is_empty(b2[0], b2[1]):
                    b2 = (b1[0], (b1[1] + 1) % board.size)
                    if not board.is_empty(b2[0], b2[1]):
                        b2 = None
                if b2 is not None:
                    board.place(b2[0], b2[1], opp)
                    sub_seq = [p, b1, b2]
                    ok = self._tss(board, color, 2, budget - 3, sub_seq)
                    board.undo()
                    board.undo()
                    if ok:
                        seq.extend(sub_seq)
                        return True
                else:
                    board.undo()
                    continue
            else:
                (b1, b2) = blocks_needed
                board.place(b1[0], b1[1], opp)
                board.place(b2[0], b2[1], opp)
                sub_seq = [p, b1, b2]
                ok = self._tss(board, color, 2, budget - 3, sub_seq)
                board.undo()
                board.undo()
                if ok:
                    seq.extend(sub_seq)
                    return True
        return False

    # ------------------------------------------------------------------
    # 走法生成与排序
    # ------------------------------------------------------------------
    def _gen_candidates(self, board: Board,
                        color: int = 0) -> list[tuple[int, int]]:
        cands = board.get_candidates(radius=2)
        if not cands:
            cands = board.get_candidates(radius=4)
        return cands

    def _single_gain(self, board: Board, color: int, p) -> int:
        """在 p 落 color 一子沿四方向形成的棋型分。"""
        x, y = p
        n = board.size
        grid = board.grid
        total = 0
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            cnt = 1
            open_ends = 0
            i, j = x + dx, y + dy
            while 0 <= i < n and 0 <= j < n and grid[j][i] == color:
                cnt += 1
                i += dx
                j += dy
            if 0 <= i < n and 0 <= j < n and grid[j][i] == EMPTY:
                open_ends += 1
            i, j = x - dx, y - dy
            while 0 <= i < n and 0 <= j < n and grid[j][i] == color:
                cnt += 1
                i -= dx
                j -= dy
            if 0 <= i < n and 0 <= j < n and grid[j][i] == EMPTY:
                open_ends += 1
            if cnt >= 6:
                total += WIN_SCORE
            elif cnt == 5:
                total += FIVE_OPEN if open_ends else FOUR_SIMPLE
            elif cnt == 4:
                total += FOUR_OPEN if open_ends >= 2 else (
                    FOUR_SIMPLE if open_ends == 1 else 0)
            elif cnt == 3:
                total += THREE_OPEN if open_ends >= 2 else (
                    THREE_SIMPLE if open_ends == 1 else 0)
            elif cnt == 2:
                total += TWO_OPEN if open_ends >= 2 else (
                    TWO_SIMPLE if open_ends == 1 else 0)
        return total

    def _point_gain(self, board: Board, color: int, p) -> int:
        """进攻分(权重高) + 占对方要点(防守，也计入)。

        进攻权重 > 防守，使 AI 在没有致命威胁时优先构建己方活三/活四节奏，
        避免"只会堵着续命"。若对手已有冲六，外层强制防守逻辑优先覆盖此处。
        """
        opp_gain = self._single_gain(board, OPPOSITE[color], p)
        atk_gain = self._single_gain(board, color, p)
        return atk_gain * 3 + opp_gain

    def _score_candidates(self, board: Board, color: int, cands,
                          tt_move=None, ply: int = 0):
        scored = []
        hist = self.history
        for p in cands:
            if board.grid[p[1]][p[0]] != EMPTY:
                continue  # 只对空点评分，避免占位点混入导致回溯错位
            s = self._point_gain(board, color, p)
            s += hist.get((color, p[0], p[1]), 0)
            if tt_move is not None and p == tt_move:
                s += 1 << 30
            else:
                for k in self.killers.get(ply, ()):
                    if p == k:
                        s += 1 << 20
            scored.append((p, s))
        scored.sort(key=lambda t: -t[1])
        return scored

    def _pick_second(self, board: Board, color: int, pool) -> tuple[int, int]:
        """为已定的一子挑选配套的第二子。"""
        best_p, best_s = None, -1
        for p in pool[:12]:
            s = self._point_gain(board, color, p)
            if s > best_s:
                best_s, best_p = s, p
        if best_p is None:
            c = board.size // 2
            best_p = (c, c)
        return best_p

    def _hash(self, board: Board, color: int, remain: int) -> int:
        h = 0
        for (x, y, c) in board.history:
            h ^= ZOBRIST[(x, y, c)]
        h ^= TURN_KEY[(color, remain)]
        return h


# ----------------------------------------------------------------------
# 简单难度：浅层 + 少量随机（保留一点"人情味"）
# ----------------------------------------------------------------------
class _EasyEngine(AlphaBetaEngine):
    def __init__(self, seed=None):
        super().__init__(max_depth=2, time_limit=0.5,
                         candidate_limit=8, pair_top=4, seed=seed)

    def best_move(self, board, color, stones_to_place):
        rng = random.Random(self.seed)
        board = board.snapshot()
        cands = self._gen_candidates(board, color)
        win_pts = _win_points(board, color, cands)
        if win_pts:
            if stones_to_place == 2:
                p = win_pts[0]
                board.place(p[0], p[1], color)
                more = _win_points(board, color, cands)
                board.undo()
                if more:
                    return [p, more[0]]
            return [win_pts[0]]
        opp = OPPOSITE[color]
        opp_win = _win_points(board, opp, cands)
        if opp_win:
            return [opp_win[0]] if stones_to_place == 1 else \
                [opp_win[0], cands[len(cands) // 2] if cands else opp_win[0]]
        scored = self._score_candidates(board, color, cands)[:10]
        if not scored:
            c = board.size // 2
            return [(c, c)]
        pick1 = scored[rng.randrange(min(3, len(scored)))][0]
        res = [pick1]
        if stones_to_place == 2:
            rest = [p for p, _ in scored if p != pick1]
            if rest:
                res.append(rest[rng.randrange(min(3, len(rest)))])
            else:
                res.append(pick1)
        return res


# ----------------------------------------------------------------------
# 对外统一入口
# ----------------------------------------------------------------------
class AI:
    """难度封装：easy / medium / hard。"""

    _PROFILES = {
        "easy": dict(cls=_EasyEngine),
        "medium": dict(cls=AlphaBetaEngine,
                       max_depth=8, time_limit=2.5,
                       candidate_limit=14, pair_top=6),
        "hard": dict(cls=AlphaBetaEngine,
                     max_depth=12, time_limit=6.0,
                     candidate_limit=18, pair_top=8),
    }

    def __init__(self, difficulty: str = "medium", seed=None):
        self.difficulty = difficulty
        prof = self._PROFILES.get(difficulty, self._PROFILES["medium"])
        kwargs = {k: v for k, v in prof.items() if k != "cls"}
        self.engine = prof["cls"](seed=seed, **kwargs)

    def get_move(self, board: Board, color: int,
                 stones_to_place: int) -> list[tuple[int, int]]:
        stones = self.engine.best_move(board, color, stones_to_place)
        if not stones:
            c = board.size // 2
            stones = [(c, c)]
        return stones[:stones_to_place]

    def last_nodes(self) -> int:
        try:
            return self.engine.nodes
        except AttributeError:
            return 0

    @property
    def last_val(self) -> float:
        """最近一次搜索的根分值（供 GUI 胜率曲线第 6 阶段校正用）。"""
        try:
            return getattr(self.engine, "last_val", 0.0)
        except Exception:
            return 0.0

    def __repr__(self):
        return f"AI(difficulty={self.difficulty!r})"
