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
from .kill_search import GomokuEval, KillSearch, KillTimeout

# ----------------------------------------------------------------------
# 棋型分值
# ----------------------------------------------------------------------
WIN_SCORE = 10_000_000          # 已成六连
FIVE_OPEN = 500_000             # 五连且至少一端开放（下一手必胜）
FOUR_OPEN = 60_000              # 活四（两个成六点）
FOUR_SIMPLE = 20_000            # 冲四（一个成六点）：> 1.8×活三(10800)，与五子棋 S_RUSH4 一致
THREE_OPEN = 6_000              # 活三
THREE_SIMPLE = 900              # 眠三
TWO_OPEN = 450                  # 活二
TWO_SIMPLE = 80                 # 眠二

# 滑窗打分表：窗口内己方 k 子（对手 0 子）时的基础分
WINDOW_SCORE = {0: 0, 1: 2, 2: 24, 3: 620, 4: 8_400, 5: 120_000, 6: WIN_SCORE}


def _make_window_score(wc: int) -> dict:
    """按"获胜所需连子数"构造滑窗打分表（索引 k = 窗口内己方子数）。

    - wc == 6（六子棋）：沿用原始权重，5 连为"还差一子即胜"的大分，6 连即 WIN_SCORE；
    - wc == 5（五子棋）：把"还差一子即胜"的 4 连提到 120_000（与六子棋 5 连同量级），
      5 连即 WIN_SCORE，使评估器正确识别五连为终局胜。
    """
    if wc == 5:
        return {0: 0, 1: 2, 2: 24, 3: 620, 4: 120_000, 5: WIN_SCORE}
    # 默认（含 6）：原始映射
    return {0: 0, 1: 2, 2: 24, 3: 620, 4: 8_400, 5: 120_000, 6: WIN_SCORE}

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
    """找出 color 落一子即连成 win_count 的所有点（六子棋=六连，五子棋=五连）。"""
    pts = []
    n = board.size
    wc = getattr(board, "win_count", 6)
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
            if cnt >= wc:
                pts.append((x, y))
                break
    return pts


def _five_open_ends(board: Board, color: int) -> list[tuple[int, int]]:
    """color 已有"差一子即胜"的连续段（长度 win_count-1）且其空端点列表。

    对手下一手在任一空端点落子即可连成 win_count 而获胜，故这些端点是
    必须封堵的强制防守点（六子棋对应"活五"，五子棋对应"活四"）。
    """
    n = board.size
    wc = getattr(board, "win_count", 6)
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
                if seg != wc - 1:
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
# 棋形识别（逐方向、含跳形/空隙，攻防转换的核心依据）
# ----------------------------------------------------------------------
# 强制力等级：连五 5 > 活四 4 > 冲四 3 > 活三 2 > 眠三 1 > 活二 0.5 > 无 0。
# 关键：必须识别"跳形"（如 XX_X 三隔一、X_XXX 跳四），不能只看连续段，
# 否则对手连成三（活三）会被漏判，AI 误以为主动权在自己而只攻不守。
THREAT_FIVE, THREAT_LIVE4, THREAT_RUSH4, THREAT_LIVE3 = 5, 4, 3, 2
THREAT_SLEEP3, THREAT_LIVE2, THREAT_SLEEP2 = 1, 0.5, 0.25


def _direction_pattern(board: Board, x: int, y: int, dx: int, dy: int,
                       color: int):
    """以 (x,y) 为落点、沿 (dx,dy) 分析"若在此落 color"形成的棋形。

    返回 (cnt, gaps, open_ends)：
      cnt = 以 (x,y) 为中心、把"恰好一个内部空隙"（两侧都有己方子）并入后的己方子数；
      gaps = 是否含"真跳形"（空隙两侧都有己方子，如 XX_X）；
      open_ends = 连续段两端是否开放（0~2）。
    关键：空隙只有在"跳过它之后还能连到己方子"时才计入（真跳形），
    若空隙后面是空地/墙则不计，避免把"隔一格外的己方子"误连。
    """
    wc = getattr(board, "win_count", 5)
    n = board.size
    grid = board.grid

    def cell(i: int, j: int) -> int:
        if 0 <= i < n and 0 <= j < n:
            v = grid[j][i]
            return 1 if v == color else (0 if v == EMPTY else 2)
        return 2  # 墙

    # 连续段扫描（不含空隙）：从 (x,y) 向一端数连续己方子
    def run_len(sx, sy, sdx, sdy):
        cnt = 0
        i, j = sx, sy
        while 0 <= i < n and 0 <= j < n and cell(i, j) == 1:
            cnt += 1
            i += sdx; j += sdy
        return cnt, (i, j)  # 返回连续子数与停止位置

    cnt_pos, stop_pos = run_len(x + dx, y + dy, dx, dy)
    cnt_neg, stop_neg = run_len(x - dx, y - dy, -dx, -dy)

    # 真跳形检测：连续段停止处是"空"，且空之后一格是己方子（XX_X）
    def jump_after(i, j, sdx, sdy):
        # 停止处 (i,j)：若为空，且 (i+sdx,j+sdy) 为己方子 → 真跳，返回跳过后的连续子数
        if not (0 <= i < n and 0 <= j < n):
            return 0
        if cell(i, j) != 0:
            return 0
        ni, nj = i + sdx, j + sdy
        if not (0 <= ni < n and 0 <= nj < n) or cell(ni, nj) != 1:
            return 0
        # 从 ni,nj 继续数连续己方子
        c = 0
        ii, jj = ni, nj
        while 0 <= ii < n and 0 <= jj < n and cell(ii, jj) == 1:
            c += 1
            ii += sdx; jj += sdy
        return c

    jump_pos = jump_after(stop_pos[0], stop_pos[1], dx, dy)
    jump_neg = jump_after(stop_neg[0], stop_neg[1], -dx, -dy)

    cnt = 1 + cnt_pos + cnt_neg + jump_pos + jump_neg
    gaps = 1 if (jump_pos > 0 or jump_neg > 0) else 0

    # 开放端：真连续段/跳段最终停止处是否为空
    def final_stop(i, j, sdx, sdy):
        while 0 <= i < n and 0 <= j < n and cell(i, j) == 1:
            i += sdx; j += sdy
        # 跳过可能的单空隙后继续
        if 0 <= i < n and 0 <= j < n and cell(i, j) == 0:
            ni, nj = i + sdx, j + sdy
            if 0 <= ni < n and 0 <= nj < n and cell(ni, nj) == 1:
                i, j = ni, nj
                while 0 <= i < n and 0 <= j < n and cell(i, j) == 1:
                    i += sdx; j += sdy
        return (i, j)

    fs_pos = final_stop(x + dx, y + dy, dx, dy)
    fs_neg = final_stop(x - dx, y - dy, -dx, -dy)
    open_ends = (1 if cell(fs_pos[0], fs_pos[1]) == 0 else 0) + \
                (1 if cell(fs_neg[0], fs_neg[1]) == 0 else 0)

    return cnt, gaps, open_ends


def _shape_rank(cnt: int, gaps: int, open_ends: int, wc: int) -> float:
    """由 (子数, 跳形数, 开放端数) 给出棋形强制力等级。

    活三 = 连三且两端开放（或跳三且两端开放）；单端开放降为眠三级。
    """
    if cnt >= wc:
        return THREAT_FIVE
    if cnt == wc - 1:
        if gaps == 0:
            return THREAT_LIVE4 if open_ends >= 2 else (
                THREAT_RUSH4 if open_ends >= 1 else THREAT_SLEEP3)
        # 跳四：填隙即成五，另一端开放即冲四级
        return THREAT_RUSH4 if open_ends >= 1 else THREAT_SLEEP3
    if cnt == wc - 2:
        if open_ends >= 2:
            return THREAT_LIVE3 if gaps == 0 else THREAT_LIVE3
        if open_ends == 1:
            return THREAT_SLEEP3
        return 0.0
    if cnt == wc - 3:
        return THREAT_LIVE2 if open_ends >= 2 else (
            THREAT_SLEEP2 if open_ends >= 1 else 0.0)
    return 0.0


def _strongest_threat(board: Board, color: int) -> float:
    """color 的最强威胁强制力等级（逐方向、含跳形棋形识别，不搜索）。

    对每个己方子，用 _direction_pattern 以"该子为落点"反推其所在棋形，
    取最强等级。注意：这里传入的是"已有局面"，落点即己方子本身。
    """
    wc = getattr(board, "win_count", 5)
    n = board.size
    grid = board.grid
    best = 0.0
    for y in range(n):
        for x in range(n):
            if grid[y][x] != color:
                continue
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                cnt, gaps, open_ends = _direction_pattern(
                    board, x, y, dx, dy, color)
                r = _shape_rank(cnt, gaps, open_ends, wc)
                if r > best:
                    best = r
                    if best >= THREAT_FIVE:
                        return best
    return best


def _initiative(board: Board, color: int) -> str:
    """主动权判定：返回 'me' / 'foe' / 'move'（当前行棋方）/ 'fuzzy'。"""
    mine = _strongest_threat(board, color)
    foe = _strongest_threat(board, OPPOSITE[color])

    if mine >= THREAT_LIVE4:
        return "me"
    if foe >= THREAT_LIVE4:
        return "foe"
    if mine >= THREAT_RUSH4 and foe < THREAT_RUSH4:
        return "me"
    if foe >= THREAT_RUSH4 and mine < THREAT_RUSH4:
        return "foe"
    if mine >= THREAT_RUSH4 and foe >= THREAT_RUSH4:
        return "move"      # 双方都有冲四：先手先连五
    if mine >= THREAT_LIVE3 and foe >= THREAT_LIVE3:
        return "move"      # 双方都有活三：同级归当前行棋方
    if mine >= THREAT_LIVE3:
        return "me"
    if foe >= THREAT_LIVE3:
        return "foe"
    return "fuzzy"


# ----------------------------------------------------------------------
# 增量评估器（滑窗法）
# ----------------------------------------------------------------------
class _Eval:
    """以 6 格滑窗对每条线打分；place/undo 只重算受影响的线。"""

    DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))

    def __init__(self, board: Board, win_count: int | None = None):
        self.board = board
        self.n = board.size
        self.wc = win_count if win_count is not None else getattr(board, "win_count", 6)
        self.window_score = _make_window_score(self.wc)
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
        wc = self.wc
        m = len(pts)
        total = 0
        for s in range(m - (wc - 1)):
            mine = 0
            opp = 0
            for k in range(s, s + wc):
                v = grid[pts[k][1]][pts[k][0]]
                if v == color:
                    mine += 1
                elif v != EMPTY:
                    opp += 1
            if opp == 0:
                total += self.window_score[mine]
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
        """color 视角的局面分（行棋方动态防守系数）。

        设计铁律（2026-10 复盘）：防守系数按"行棋方"动态取——
            - 己方（color 视角，即轮到谁走谁为 self）进攻权重 ×1.2，
              鼓励 AI 主动发展己方活三/活四等威胁，而不是一直被动拆招；
            - 对手威胁权重 ×1.6（∈[1.5,1.8]），对手的成六/冲六威胁由
              外层强制防守逻辑兜底的同时，这里给予更高惩罚，绝不漏守致命威胁。
        """
        return int(self.score[color] * 1.2) - int(self.score[OPPOSITE[color]] * 1.6)


# ----------------------------------------------------------------------
# 主引擎
# ----------------------------------------------------------------------
class AlphaBetaEngine:
    """迭代加深 + PVS + 置换表 + 威胁空间搜索。"""

    def __init__(self, max_depth: int = 8, time_limit: float = 2.5,
                 candidate_limit: int = 14, pair_top: int = 6, seed=None,
                 root_vcf_depth: int = 14, root_vct_depth: int = 8,
                 leaf_vcf_depth: int = 10, leaf_vct_depth: int = 6,
                 leaf_kill_nodes: int = 120, gomoku_max_depth: int = 6):
        self.max_depth = max_depth
        self.time_limit = time_limit
        self.candidate_limit = candidate_limit
        self.pair_top = pair_top
        self.seed = seed
        # 稳定随机源：用于打破"并列打分取第一"的确定性偏差
        # （候选点按 (y,x) 升序，对称局面并列时若机械取首项会永远偏向
        #   左上角，导致 AI 每局固定往左上斜线冲）。随机源独立于主随机，
        #   可复现（同 seed 同棋路）。
        self._rng = random.Random(seed)
        self._tie_n = 1   # _pick_tie 的并列计数（每次打分循环前重置）
        self.nodes = 0
        self.deadline = 0.0
        self.tt: dict[int, tuple] = {}
        self.history: dict[tuple, int] = {}
        self.killers: dict[int, list] = {}
        self._stop = False
        self._tss_nodes = 0
        self.last_val = 0.0   # 最近一次搜索的根结点分值（供 GUI 胜率校正）

        # ---- 五子棋（win_count==5）算杀配置（随难度档位传入） ----
        # 根节点：VCF 连续冲四 + VCT 连续威胁；叶节点：浅层算杀复检截断；
        # 全局 Alpha-Beta 深度在五子棋下钳制（默认 6 层，hard 调到 8 层），
        # 省时给算杀、又保留足够全局视野。
        # 「困难」档使用完整设计值：VCF 18 / VCT 12，叶节点 14 / 10 / 240，全局 8 层。
        self._gomoku = False
        self._gomoku_max_depth = max(2, int(gomoku_max_depth))
        self._root_vcf_depth = max(4, int(root_vcf_depth))
        self._root_vct_depth = max(4, int(root_vct_depth))
        self._leaf_vcf_depth = max(2, int(leaf_vcf_depth))
        self._leaf_vct_depth = max(2, int(leaf_vct_depth))
        self._leaf_kill_nodes = max(20, int(leaf_kill_nodes))

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
        wc = getattr(board, "win_count", 6)
        self._gomoku = (wc == 5)
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

        # ---------- 3. TSS：冲四连击找强制胜（五子棋改用下方 VCF/VCT） ----------
        if not self._gomoku:
            seq = self._threat_search(board, color, stones_to_place)
            if seq:
                return seq[:stones_to_place]

        # ---------- 3.5 五子棋：根节点算杀（VCF 最高优先级 → VCT） ----------
        # 算杀成功即为客观必胜，直接返回走法，不再依赖启发式评估。
        if self._gomoku and stones_to_place == 1:
            mv = self._gomoku_kill_root(board, color)
            if mv is not None:
                self.last_val = WIN_SCORE
                return [mv]
            # 算杀失败（无必胜），进入"主动权驱动"的攻防转换层：
            # 按"谁被迫回应谁"选点（冲四压制 / 有反制堵点 / 攻防兼备），
            # 命中则直接返回；未命中才降级到 Alpha-Beta 启发式搜索。
            mv2 = self._initiative_decision(board, color)
            if mv2 is not None:
                return [mv2]

        # ---------- 4. 迭代加深 + PVS ----------
        if board.move_count == 0:
            c = board.size // 2
            self.last_val = 0.0
            return [(c, c)]

        pool = [p for p, _s in
                self._score_candidates(board, color, cands)[: self.candidate_limit * 3]]
        # 五子棋使用位棋盘棋形评估器（增量式，只重算受影响线）
        ev = GomokuEval(board) if self._gomoku else _Eval(board)
        best = None
        self.last_val = 0.0
        max_d = (self._gomoku_max_depth if self._gomoku
                 else self.max_depth)   # 五子棋全局搜索层数为可配置（hard=8）
        for depth in range(2, max_d + 1, 2):
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
    # 五子棋算杀集成（VCF / VCT）
    # ------------------------------------------------------------------
    def _gomoku_kill_root(self, board: Board, color: int):
        """根节点算杀：先 VCF（连续冲四，深度 16），再 VCT（连续威胁，深度 10）。

        预算：VCF 至多 35% 时限 / 4000 节点，VCT 至多 25% 时限 / 2400 节点；
        超限即放弃（返回 None），后续仍走 Alpha-Beta 全局搜索，宁缺毋滥。
        预算上限较旧版放宽（2000→4000 / 1200→2400）：困难档时限更长，
        更深算杀能在时限内完成，提升必胜判定覆盖率，使 AI 更难被击败。
        """
        now = time.monotonic()
        ks = KillSearch(board, color,
                        deadline=min(self.deadline, now + self.time_limit * 0.35),
                        max_nodes=4000)
        mv = ks.vcf(self._root_vcf_depth)
        if mv is not None:
            return mv
        ks2 = KillSearch(board, color,
                         deadline=min(self.deadline,
                                      time.monotonic() + self.time_limit * 0.25),
                         max_nodes=2400)
        return ks2.vct(self._root_vct_depth)

    # ------------------------------------------------------------------
    # 攻防转换中间层（根算杀失败后、Alpha-Beta 前）
    # ------------------------------------------------------------------
    def _initiative_decision(self, board: Board, color: int):
        """基于"主动权"的攻防转换决策，返回单步落点 (x, y) 或 None。

        仅用于五子棋（win_count==5）。根 VCF/VCT 已失败（无必胜）。
        决策优先级（自上而下，命中即返回）：
          1. 我能一手连五 → 赢；
          2. 对方活四（两端开放，一手连五）→ 必须堵；
          3. 对方冲四（一手连五）→ 必须堵；
          4. 按主动权分支：
             - me   → 走最强冲四/活三（连续施压，多方向）；
             - foe  → 选"能真正降低对方威胁"的堵点（严格优先堵，再谈反制）；
             - move/fuzzy → 攻防兼备点（Δ我方 − 1.2×Δ对方）。
        返回裸落点 (x, y)；None 则降级 Alpha-Beta。
        """
        opp = OPPOSITE[color]
        cands = board.get_candidates(radius=2)
        if not cands:
            cands = board.get_candidates(radius=4)
        if not cands:
            return None

        # 1) 我方一手连五 → 直接赢（外层已兜底，这里再保险）
        win_pts = _win_points(board, color, cands)
        if win_pts:
            return win_pts[0]

        # 2) 对方活四（两端开放的一手连五）→ 必须堵
        opp_five_ends = _five_open_ends(board, opp)
        if opp_five_ends:
            return opp_five_ends[0]

        # 3) 对方冲四（一手连五）→ 必须堵
        opp_win = _win_points(board, opp, cands)
        if opp_win:
            return opp_win[0]

        # 4) 威胁反制规则（Allis 威胁空间搜索）：对方活三 = 延迟迫着
        #    （delayed threat），不可置之不理；唯有我方能走出更严重的先手
        #    （落子即成四，含跳形填隙）时才允许先攻不防，否则强制先消除威胁。
        opp_lvl = _strongest_threat(board, opp)
        if opp_lvl >= THREAT_LIVE3 and not self._has_forcing_four(board, color, cands):
            mv = self._best_block_with_counter(board, color, cands)
            if mv is not None:
                return mv

        # 5) 主动权分支
        ctrl = _initiative(board, color)
        if ctrl == "me":
            mv = self._best_own_threat(board, color, cands)
            if mv is not None:
                return mv
        elif ctrl == "foe":
            mv = self._best_block_with_counter(board, color, cands)
            if mv is not None:
                return mv
        else:
            mv = self._best_dual_purpose(board, color, cands)
            if mv is not None:
                return mv

        # 兜底：攻防兼备
        return self._best_dual_purpose(board, color, cands)

    def _has_forcing_four(self, board: Board, color: int, cands) -> bool:
        """是否存在"落子即成四（冲四/活四，含跳形填隙）"的先手点。

        依据 Allis 威胁空间搜索的反制严重度规则：只有我方能走出比对
        方威胁（活三=延迟迫着）更严重的先手（成四）时，才允许无视对方
        活三继续进攻。只检查与己方棋子相邻（切比雪夫距离 ≤2）的空点。
        """
        n = board.size
        grid = board.grid
        for (x, y) in cands:
            if not board.is_empty(x, y):
                continue
            # 只看己方棋子附近的点（成四必须与己方子接触/跳接）
            touch = False
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    i, j = x + dx, y + dy
                    if 0 <= i < n and 0 <= j < n and grid[j][i] == color:
                        touch = True
                        break
                if touch:
                    break
            if not touch:
                continue
            board.place(x, y, color)
            lvl = _strongest_threat(board, color)
            board.undo()
            if lvl >= THREAT_RUSH4:
                return True
        return False

    def _best_own_threat(self, board: Board, color: int, cands):
        """我方主动：返回能形成冲四（优先）或活三的落点，否则 None。

        多方向评估：优先选"落子后多方向同时变强"的点（棋路多变，不只单线）。
        """
        best, best_s = None, -1
        self._tie_n = 1
        for (x, y) in cands:
            if not board.is_empty(x, y):
                continue
            board.place(x, y, color)
            lvl = _strongest_threat(board, color)
            gain = self._single_gain(board, color, (x, y))
            # 多方向连接价值：该点沿四方向各自能连成的连续子数之和
            connect = self._connectivity(board, color, x, y)
            board.undo()
            if lvl >= THREAT_RUSH4:
                s = lvl * 1_000_000 + gain + connect * 1000 \
                    + self._center_bias(board, x, y)
                best, best_s, _ = self._pick_tie(best, best_s, (x, y), s)
        if best is not None:
            return best
        # 无冲四，退而求活三（同样看多方向连接）
        self._tie_n = 1
        for (x, y) in cands:
            if not board.is_empty(x, y):
                continue
            board.place(x, y, color)
            lvl = _strongest_threat(board, color)
            gain = self._single_gain(board, color, (x, y))
            connect = self._connectivity(board, color, x, y)
            board.undo()
            if lvl >= THREAT_LIVE3:
                s = gain + connect * 1000 + self._center_bias(board, x, y)
                best, best_s, _ = self._pick_tie(best, best_s, (x, y), s)
        return best

    def _connectivity(self, board: Board, color: int, x: int, y: int) -> int:
        """(x,y) 落 color 后，沿四方向能连成的连续子数之和（衡量"连上前棋"）。"""
        grid = board.grid
        n = board.size
        total = 0
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
            total += cnt
        return total

    def _center_bias(self, board: Board, x: int, y: int) -> float:
        """距棋盘中心的切比雪夫距离惩罚（极轻，仅用于开局打破对称）。

        空盘/开局盘面高度对称时，各对称点打分完全并列，单纯靠并列随机
        仍可能出现"连走同一侧"。此偏置给靠近中心的点一个微小正分，
        使 AI 开局更自然地向中心铺开而非贴角。权重刻意压到不影响
        任何中盘正常棋感（中盘候选点本就聚集在棋子附近，差异远大于此）。
        """
        n = board.size
        cx = cy = (n - 1) / 2
        return -max(abs(x - cx), abs(y - cy)) * 1.0

    def _pick_tie(self, best: tuple, best_s: float, cand: tuple, s: float):
        """并列打分时的公平随机择优（水塘抽样）。

        当 s == best_s 时，以 1/n 概率（n=当前并列最优数）替换 best，
        保证所有并列最优点**等概率**被选中，消除"候选点按 (y,x) 升序、
        机械取首项导致永远偏向左上角/右下角"的确定性偏差。

        （不能用 `if s == best_s and rng.random() < 0.5`：那种写法对
        一批并列点会产生"越靠后越难胜出"的偏置，实测会集中到列表末尾。）
        """
        if s > best_s:
            return (cand, s, 1)
        if s == best_s:
            self._tie_n += 1
            if self._rng.random() < 1.0 / self._tie_n:
                return (cand, s, self._tie_n)
        return (best, best_s, self._tie_n)

    def _best_block_with_counter(self, board: Board, color: int, cands):
        """主动权在对方：找对方活四/冲四/活三的堵点，选堵完能反制的那个。

        逐方向识别对方跳形威胁（含三隔一）。堵点 = 能降低对方威胁等级的点。
        当对方有活三/冲四时，**严格优先堵点**（必须先消除威胁），
        再在"多个有效堵点"之间选"堵完能反制"的那个；绝不为贪己方做棋而漏堵。
        """
        opp = OPPOSITE[color]
        opp_lvl0 = _strongest_threat(board, opp)

        # 对方冲四的成五点（活四两端必堵，已由外层处理）
        rush_pts = _win_points(board, opp, cands)
        if rush_pts:
            best, best_s = None, -1
            self._tie_n = 1
            for p in rush_pts:
                if not board.is_empty(p[0], p[1]):
                    continue
                board.place(p[0], p[1], color)
                s = self._single_gain(board, color, p) + \
                    self._connectivity(board, color, p[0], p[1]) * 1000 + \
                    self._center_bias(board, p[0], p[1])
                board.undo()
                best, best_s, _ = self._pick_tie(best, best_s, p, s)
            if best is not None:
                return best

        # 枚举所有能"真正降低对方威胁等级"的堵点（含跳形填隙/堵端）
        block_cands = []
        for p in cands:
            if not board.is_empty(p[0], p[1]):
                continue
            board.place(p[0], p[1], color)
            opp_lvl = _strongest_threat(board, opp)
            board.undo()
            if opp_lvl < opp_lvl0:
                block_cands.append(p)

        if block_cands:
            # 多个有效堵点里，选"堵完己方威胁最强 / 能反制"的那个
            best, best_s = None, None
            self._tie_n = 1
            for p in block_cands:
                board.place(p[0], p[1], color)
                self_lvl = _strongest_threat(board, color)
                self_gain = self._single_gain(board, color, p)
                connect = self._connectivity(board, color, p[0], p[1])
                board.undo()
                s = self_lvl * 20_000 + self_gain + connect * 1000 + \
                    self._center_bias(board, p[0], p[1])
                if best_s is None:
                    best, best_s = p, s
                    self._tie_n = 1
                else:
                    best, best_s, _ = self._pick_tie(best, best_s, p, s)
            return best

        # 无直接堵点（对方威胁非活三/冲四级别）：退回"攻防兼备"
        return self._best_dual_purpose(board, color, cands)

    def _best_dual_purpose(self, board: Board, color: int, cands):
        """模糊/先手局面：攻防兼备点。

        净值 = 进攻增值 + 威胁消除奖励（落子使对方威胁降级）+ 多方向连接
        − 占点惩罚（该点若归对方其威胁增值，权重压低作参考）。
        走到这里时对方最强威胁 < 活三（更强威胁已在上方被强制处理）。
        """
        opp = OPPOSITE[color]
        opp_lvl0 = _strongest_threat(board, opp)
        best, best_s = None, None
        self._tie_n = 1
        for (x, y) in cands:
            if not board.is_empty(x, y):
                continue
            d_me = self._single_gain(board, color, (x, y))
            d_foe = self._single_gain(board, opp, (x, y))
            board.place(x, y, color)
            opp_after = _strongest_threat(board, opp)
            board.undo()
            denial = max(0.0, opp_lvl0 - opp_after)
            connect = self._connectivity(board, color, x, y)
            s = d_me + denial * 80_000 + connect * 300 - 0.25 * d_foe + \
                self._center_bias(board, x, y)
            if best_s is None:
                best, best_s = (x, y), s
                self._tie_n = 1
            else:
                best, best_s, _ = self._pick_tie(best, best_s, (x, y), s)
        return best

    def _leaf_kill_value(self, ev, color: int, ply: int):
        """叶节点算杀复检：VCF/VCT 找到必胜 → 返回极大值；否则 None（静态评估）。"""
        if not isinstance(ev, GomokuEval) or ev.quiet():
            return None                     # 无威胁棋形，跳过（quiet 剪枝）
        if time.monotonic() >= self.deadline:
            return None                     # 全局时限已到：立刻放弃，绝不拖慢搜索
        ks = KillSearch(ev.board, color, deadline=self.deadline,
                        max_nodes=self._leaf_kill_nodes)
        try:
            if ks.vcf(self._leaf_vcf_depth) is not None:
                return WIN_SCORE - ply
            if time.monotonic() >= self.deadline:
                return None
            if ks.vct(self._leaf_vct_depth) is not None:
                return WIN_SCORE - ply
        except KillTimeout:
            return None
        finally:
            ks.unwind()                     # 异常安全：保证棋盘还原
        return None

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
            # 五子棋：叶节点算杀复检（VCF/VCT），必胜即赋极大值截断，
            # 不再依赖启发式评估；无威胁棋形（quiet）直接走静态分。
            if self._gomoku:
                v = self._leaf_kill_value(ev, color, ply)
                if v is not None:
                    return v
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
        if self._tss(board, color, stones_to_place, 16, seq):
            return seq
        return None

    def _tss(self, board: Board, color: int, remain: int,
             budget: int, seq: list) -> bool:
        if budget <= 0 or self._tss_nodes > 12000:
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
        """在 p 落 color 一子沿四方向形成的棋型分。

        连子门槛随 win_count 平移（六子棋 6 连胜 / 五子棋 5 连胜），
        保证五子棋下"成五=必胜分、成四=冲四/活四分"的正确档位。
        """
        x, y = p
        n = board.size
        grid = board.grid
        wc = getattr(board, "win_count", 6)
        off = 6 - wc            # 档位平移量：eff = 落子后连子数 + off
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
            eff = cnt + off
            if eff >= 6:
                total += WIN_SCORE
            elif eff == 5:
                total += FIVE_OPEN if open_ends else FOUR_SIMPLE
            elif eff == 4:
                total += FOUR_OPEN if open_ends >= 2 else (
                    FOUR_SIMPLE if open_ends == 1 else 0)
            elif eff == 3:
                total += THREE_OPEN if open_ends >= 2 else (
                    THREE_SIMPLE if open_ends == 1 else 0)
            elif eff == 2:
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
    """难度封装：easy / medium / hard（两种棋共用同一套难度体系）。

    五子棋档位差异：
      easy   —— 浅层 + 随机（人情味，不做算杀）；
      medium —— 算杀降档（根 VCF14/VCT10，叶 12/8/140），全局 6 层；
      hard   —— **完整算杀设计**：根节点 VCF 连续冲四 18 层 + VCT 连续
                威胁 12 层，叶节点算杀截断（VCF14/VCT10/240 节点），
                8 层 Alpha-Beta 全局搜索，时限 9s，候选 28。
    """

    _PROFILES = {
        "easy": dict(cls=_EasyEngine),
        "medium": dict(cls=AlphaBetaEngine,
                       max_depth=8, time_limit=4.5,
                       candidate_limit=20, pair_top=8,
                       root_vcf_depth=14, root_vct_depth=10,
                       leaf_vcf_depth=12, leaf_vct_depth=8,
                       leaf_kill_nodes=140, gomoku_max_depth=6),
        "hard": dict(cls=AlphaBetaEngine,
                     max_depth=12, time_limit=9.0,
                     candidate_limit=28, pair_top=12,
                     # 完整算杀设计（与 kill_search 模块定稿参数一致）
                     root_vcf_depth=18, root_vct_depth=12,
                     leaf_vcf_depth=14, leaf_vct_depth=10,
                     leaf_kill_nodes=240, gomoku_max_depth=8),
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
