# -*- coding: utf-8 -*-
"""
kill_search.py —— 五子棋本地算杀（VCF/VCT）与位棋盘棋形评估（不依赖模型训练）

组成：
    1. 位棋盘 + 棋形查表：
       每条线用整数位掩码表示黑白占位（GomokuEval），
       线上棋形由"运行段 + 单空隙分组"归类为 连五/活四/冲四/活三/眠三/活二/眠二，
       分类结果按 (win_count, 线内容) 记忆化到模块级查表 _LINE_TABLE，重复局面直接查表；
    2. GomokuEval：增量式评估器——落子/悔子只重算受影响的 ≤4 条线，
       并维护"威胁棋形计数"供叶节点快速判断是否需要算杀（quiet 剪枝）；
    3. KillSearch：VCF（连续冲四，最高优先级，深度 ≥12）与
       VCT（连续威胁，MAX 层只生成活三/冲四，MIN 层生成破坏威胁点+反击，深度约 8）
       的 AND-OR 搜索；节点预算 + 截止时间双保险，超限即放弃（宁可不算杀，不可误判）。

与 ai.py 的关系：本模块只依赖 board.py；由 ai.py 在 win_count==5（五子棋）时启用。
"""
from __future__ import annotations

import threading
import time

from .board import BLACK, EMPTY, OPPOSITE, WHITE

# ----------------------------------------------------------------------
# 棋形分值（win_count == 5）
# ----------------------------------------------------------------------
S_FIVE = 10_000_000          # 连五（终局）
S_LIVE4 = 500_000            # 活四（两个成五点，下一手必胜）
# 冲四：设计铁律要求 冲四 > 1.8×对方活三（1.8×8000=14400），故取 20000。
# 低于此值会导致"对方活三分高过己方冲四"，评估误判、算杀优先级错乱。
S_RUSH4 = 20_000             # 冲四（一个成五点）
S_LIVE3 = 8_000              # 活三（可成活四）
S_SLEEP3 = 700               # 眠三
S_LIVE2 = 350                # 活二
S_SLEEP2 = 60                # 眠二

# 棋形类别（递增=越强），用于 quiet 剪枝与统计
C_NONE, C_SLEEP2, C_LIVE2, C_SLEEP3, C_LIVE3, C_RUSH4, C_LIVE4, C_FIVE = range(8)
_THREAT_CLASS = C_SLEEP3     # ≥ 此类别视为"存在威胁"

DIRS4 = ((1, 0), (0, 1), (1, 1), (1, -1))

# 查表：key=(win_count, cells元组) -> (score, top_class)
# cells: 0=空 1=己方 2=挡（墙与对方子同属"挡"），未含墙 padding（函数内部补）
_LINE_TABLE: dict = {}
# 缓存上限：key 空间虽有限但仍设硬上限，避免长会话无界增长；
# 命中率极高、重建代价低，超出时整体清空即可（仅在极端长对局触发）。
_LINE_TABLE_CAP = 16384
# 跨线程保护：AI 搜索跑在后台线程，查表读写需串行化，避免 dict 并发损坏。
_LINE_TABLE_LOCK = threading.Lock()


def _find_groups(cells, wc: int):
    """把一条线拆成"棋形组"：单连续段，或仅隔 1 个空隙的两段联合。

    返回 [(a, b, gap, cnt)]：a/b 为 cells 下标（闭区间），gap=空隙数(0/1)，
    cnt=组内己方子数。一子最多归属两个组（自身段 + 与邻段联合）。
    """
    runs = []
    i, n = 0, len(cells)
    while i < n:
        if cells[i] == 1:
            j = i
            while j < n and cells[j] == 1:
                j += 1
            runs.append((i, j - 1))
            i = j
        else:
            i += 1
    groups = []
    for idx, (a, b) in enumerate(runs):
        groups.append((a, b, 0))
        # 铁律（2026-10-01 截图复盘）：联合两段的前提是中间那格真的是"空隙"
        # （cells==0）。旧版只看距离，把"隔着一个对方子"的两段误连成跳形
        # （如 X X 【挡】 X 被当成跳三）→ 假双三/假活四 → VCT 假必胜，
        # AI 面对对方跳活三拒不防守。
        if (idx + 1 < len(runs) and runs[idx + 1][0] - b == 2
                and cells[b + 1] == 0):
            groups.append((a, runs[idx + 1][1], 1))
    out = []
    for (a, b, gap) in groups:
        cnt = 0
        for t in range(a, b + 1):
            if cells[t] == 1:
                cnt += 1
        out.append((a, b, gap, cnt))
    return out


def _grade_group(cells, a: int, b: int, gap: int, cnt: int, wc: int):
    """给单个棋形组定级：返回 (score, class)。端点出界视为"挡"。"""
    n = len(cells)

    def is_open(t: int) -> bool:
        return 0 <= t < n and cells[t] == 0

    if gap == 0 and cnt >= wc:
        return (S_FIVE, C_FIVE)
    if gap == 1 and cnt >= wc:
        # 跨空隙已达 wc 子：填隙即超连，按活四级处理
        return (S_LIVE4, C_LIVE4)
    if cnt == wc - 1:                                   # 四
        if gap == 0:
            ol, orr = is_open(a - 1), is_open(b + 1)
            if ol and orr:
                return (S_LIVE4, C_LIVE4)               # 两端空 → 两个成五点
            if ol or orr:
                return (S_RUSH4, C_RUSH4)               # 单端空 → 冲四
            return (0, C_NONE)
        return (S_RUSH4, C_RUSH4)                       # 空隙四：填隙即五（1 个成五点）
    if cnt == wc - 2:                                   # 三
        if gap == 0:
            ol, orr = is_open(a - 1), is_open(b + 1)
            ext = is_open(a - 2) or is_open(b + 2)
            if ol and orr and ext:
                return (S_LIVE3, C_LIVE3)               # 能延伸成活四
            if ol or orr:
                return (S_SLEEP3, C_SLEEP3)
            return (0, C_NONE)
        ol, orr = is_open(a - 1), is_open(b + 1)
        if ol and orr:
            return (S_LIVE3, C_LIVE3)                   # 跳三（填隙成四）
        return (S_SLEEP3, C_SLEEP3)
    if cnt == wc - 3:                                   # 二
        if gap == 0:
            ol, orr = is_open(a - 1), is_open(b + 1)
            if ol and orr:
                return (S_LIVE2, C_LIVE2)
            if ol or orr:
                return (S_SLEEP2, C_SLEEP2)
            return (0, C_NONE)
        if is_open(a - 1) or is_open(b + 1):
            return (S_SLEEP2, C_SLEEP2)
        return (0, C_NONE)
    return (0, C_NONE)


def _classify_cells(cells, wc: int):
    """整条线（己方视角）→ (总分, 最高棋形类别)。查表 + 贪心去重计分。"""
    key = (wc, tuple(cells))
    with _LINE_TABLE_LOCK:
        hit = _LINE_TABLE.get(key)
    if hit is not None:
        return hit
    # 连五优先（不可与其它组重叠计分）
    res = (0, C_NONE)
    for (a, b, gap, cnt) in _find_groups(cells, wc):
        if gap == 0 and cnt >= wc:
            res = (S_FIVE, C_FIVE)
            break
    if res[1] != C_FIVE:
        groups = [_grade_group(cells, a, b, gap, cnt, wc) + (a, b)
                  for (a, b, gap, cnt) in _find_groups(cells, wc)]
        # 按分值降序贪心挑选互不重叠的组，避免同一组子被重复计分
        groups.sort(key=lambda t: -t[0])
        used: set = set()
        total = 0
        top = C_NONE
        for (s, cls, a, b) in groups:
            if s <= 0:
                continue
            span = set(range(a, b + 1))
            if span & used:
                continue
            used |= span
            total += s
            if cls > top:
                top = cls
        res = (total, top)
    with _LINE_TABLE_LOCK:
        if len(_LINE_TABLE) >= _LINE_TABLE_CAP:
            _LINE_TABLE.clear()
        _LINE_TABLE[key] = res
    return res


# ----------------------------------------------------------------------
# 增量式评估器（五子棋专用）
# ----------------------------------------------------------------------
class GomokuEval:
    """位棋盘增量评估：place/undo 只重算受影响的 ≤4 条线。

    接口与 ai._Eval 对齐（board / score / place / undo / evaluate），
    另提供 quiet()（双方均无 ≥眠三棋形 → 叶节点可跳过算杀检测）。
    """

    DIRS = DIRS4

    def __init__(self, board):
        self.board = board
        self.n = board.size
        self.wc = getattr(board, "win_count", 5)
        self._pts: list[list[tuple[int, int]]] = []
        self._cell_info: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self._build_lines()
        nl = len(self._pts)
        self._mine = {BLACK: [0] * nl, WHITE: [0] * nl}
        self._occ = [0] * nl
        self.score = {BLACK: 0, WHITE: 0}
        self._threat_cnt = {BLACK: 0, WHITE: 0}
        self._line_stat = {BLACK: [(0, C_NONE)] * nl, WHITE: [(0, C_NONE)] * nl}
        # 从当前局面初始化
        for y in range(self.n):
            for x in range(self.n):
                c = self.board.grid[y][x]
                if c != EMPTY:
                    self._apply(x, y, c, True)

    # ---- 线结构 ----
    def _build_lines(self):
        n = self.n
        for (dx, dy) in self.DIRS:
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
            for (sx, sy) in starts:
                pts = []
                i, j = sx, sy
                while 0 <= i < n and 0 <= j < n:
                    pts.append((i, j))
                    i += dx
                    j += dy
                lid = len(self._pts)
                self._pts.append(pts)
                for pos, (x, y) in enumerate(pts):
                    self._cell_info.setdefault((x, y), []).append((lid, pos))

    def _line_cells(self, lid: int, color: int) -> list[int]:
        mine = self._mine[color][lid]
        occ = self._occ[lid]
        out = []
        for pos in range(len(self._pts[lid])):
            if (mine >> pos) & 1:
                out.append(1)
            elif (occ >> pos) & 1:
                out.append(2)
            else:
                out.append(0)
        return out

    def _stat_line(self, lid: int, color: int):
        return _classify_cells(self._line_cells(lid, color), self.wc)

    def _apply(self, x: int, y: int, color: int, add: bool):
        info = self._cell_info.get((x, y)) or []
        if add:
            for (lid, pos) in info:
                self._mine[color][lid] |= (1 << pos)
                self._occ[lid] |= (1 << pos)
        else:
            for (lid, pos) in info:
                self._mine[color][lid] &= ~(1 << pos)
                self._occ[lid] &= ~(1 << pos)
        for (lid, _pos) in info:
            for c in (BLACK, WHITE):
                old_s, old_cls = self._line_stat[c][lid]
                new_s, new_cls = self._stat_line(lid, c)
                if new_s == old_s and new_cls == old_cls:
                    continue
                self.score[c] += new_s - old_s
                if old_cls >= _THREAT_CLASS and new_cls < _THREAT_CLASS:
                    self._threat_cnt[c] -= 1
                elif new_cls >= _THREAT_CLASS and old_cls < _THREAT_CLASS:
                    self._threat_cnt[c] += 1
                self._line_stat[c][lid] = (new_s, new_cls)

    # ---- 对外接口（与 ai._Eval 对齐）----
    def place(self, x: int, y: int, color: int):
        b = self.board
        b.grid[y][x] = color
        b.move_count += 1
        b.history.append((x, y, color))
        self._apply(x, y, color, True)

    def undo(self):
        b = self.board
        x, y, color = b.history.pop()
        b.grid[y][x] = EMPTY
        b.move_count -= 1
        self._apply(x, y, color, False)

    def evaluate(self, color: int) -> int:
        """color 视角局面分（行棋方动态防守系数）。

        设计铁律（2026-10 复盘）：防守系数须按"行棋方"动态取——
        己方（color 视角，即"轮到谁走谁为 self"）进攻权重 ×1.2，
        对方威胁权重 ×1.6（∈[1.5,1.8]）。在 negamax 下，对手威胁被
        更高倍数惩罚，使 AI 既不"只堵续命"也绝不漏守致命威胁，整体更难被攻破。
        """
        return int(self.score[color] * 1.2) - int(self.score[OPPOSITE[color]] * 1.6)

    def quiet(self) -> bool:
        """双方均无 ≥眠三棋形 → 无算杀价值，叶节点可直接静态评估。"""
        return self._threat_cnt[BLACK] == 0 and self._threat_cnt[WHITE] == 0


# ----------------------------------------------------------------------
# VCF / VCT 算杀
# ----------------------------------------------------------------------
class KillTimeout(Exception):
    """节点预算或时限耗尽（放弃本次算杀，宁可不算杀也不误判）。"""


class KillSearch:
    """五子棋算杀器（在快照棋盘上试着子，异常安全回滚）。

    vcf(depth) : 连续冲四搜索。己方仅生成冲四点，对手只可能堵成五点
                 （或反击冲四，我方下一层被强制堵回）。任一分支对手全部
                 应对皆败 → 必胜。终局条件：连五 / 活四（≥2 个成五点）。
    vct(depth) : 连续威胁搜索。MAX 层生成冲四 + 活三（含双威胁优先），
                 MIN 层生成破坏威胁点（成五点/活三破点）与对手反击
                 （对方冲四优先，其次活三），深度约 8。
    """

    def __init__(self, board, color: int, deadline: float | None = None,
                 max_nodes: int = 2000):
        self.board = board
        self.n = board.size
        self.wc = getattr(board, "win_count", 5)
        self.me = color
        self.foe = OPPOSITE[color]
        self.deadline = deadline
        self.max_nodes = max(50, int(max_nodes))
        self.nodes = 0
        self._stack: list[tuple[int, int]] = []

    # ---- 落子 / 回滚（带异常安全栈）----
    def _place(self, x: int, y: int, c: int):
        g = self.board.grid
        g[y][x] = c
        self.board.move_count += 1
        self.board.history.append((x, y, c))
        self._stack.append((x, y))

    def _undo1(self):
        x, y, _c = self.board.history.pop()
        self.board.grid[y][x] = EMPTY
        self.board.move_count -= 1
        self._stack.pop()

    def unwind(self):
        while self._stack:
            self._undo1()

    def _tick(self):
        self.nodes += 1
        if self.nodes > self.max_nodes:
            raise KillTimeout
        # 每节点都查时间：monotonic() 开销（~百纳秒）远小于单节点搜索成本，
        # 稀疏检查会让叶节点算杀在超时后仍整段跑完，拖垮全局时限。
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise KillTimeout

    # ---- 局部几何 ----
    def _strip(self, x: int, y: int, dx: int, dy: int) -> list[int]:
        """以 (x,y) 为中心、长 2wc-1 的方向条。中心下标 wc-1。

        编码：EMPTY=空、BLACK/WHITE=对应色、3=棋盘外墙体。
        墙体必须与任何棋色取值不同，否则白方视角会把"墙"误判为白子
        （黑=1、白=2，若墙也编码 2，白方窗口分析即出错——已踩坑并修复）。
        """
        wc = self.wc
        n = self.n
        g = self.board.grid
        out = []
        for k in range(-(wc - 1), wc):
            i, j = x + k * dx, y + k * dy
            if 0 <= i < n and 0 <= j < n:
                out.append(g[j][i])
            else:
                out.append(3)
        return out

    def _line_pts(self, x: int, y: int, dx: int, dy: int):
        """经过 (x,y) 的整条线坐标序列。"""
        n = self.n
        i, j = x, y
        while True:
            i2, j2 = i - dx, j - dy
            if 0 <= i2 < n and 0 <= j2 < n:
                i, j = i2, j2
            else:
                break
        pts = []
        while 0 <= i < n and 0 <= j < n:
            pts.append((i, j))
            i += dx
            j += dy
        return pts

    # ---- 威胁识别 ----
    def _five_points(self, color: int, cands) -> list[tuple[int, int]]:
        """已有棋形下，color 落一子即连成 wc 的空点（成五点）。"""
        wc = self.wc
        a = wc - 1
        pts = []
        for (x, y) in cands:
            if self.board.grid[y][x] != EMPTY:
                continue
            for dx, dy in DIRS4:
                s_ = self._strip(x, y, dx, dy)
                found = False
                for st in range(wc):
                    ok = True
                    for t in range(st, st + wc):
                        if t == a:
                            continue
                        if s_[t] != color:
                            ok = False
                            break
                    if ok:
                        found = True
                        break
                if found:
                    pts.append((x, y))
                    break
        return pts

    def _probe(self, x: int, y: int, color: int):
        """假想在空点 (x,y) 落 color。返回 (是否直接成五, 落后形成的成五点集)。

        只检查经过 (x,y) 的线（落子只影响这些线），窗口法 O(wc) 每方向。
        """
        wc = self.wc
        a = wc - 1
        g = self.board.grid
        g[y][x] = color                       # 临时（本方法保证还原）
        five = False
        fps: set = set()
        try:
            for dx, dy in DIRS4:
                s_ = self._strip(x, y, dx, dy)
                for st in range(wc):
                    own = 1                   # 中心己方
                    empt: list[int] = []
                    blocked = False
                    for t in range(st, st + wc):
                        if t == a:
                            continue
                        v = s_[t]
                        if v == color:
                            own += 1
                        elif v == EMPTY:
                            empt.append(t)
                        else:
                            blocked = True
                            break
                    if blocked:
                        continue
                    if own >= wc:
                        five = True
                    elif own == wc - 1 and len(empt) == 1:
                        k = empt[0] - a
                        fps.add((x + k * dx, y + k * dy))
        finally:
            g[y][x] = EMPTY
        return five, fps

    def _four_moves(self, color: int, cands):
        """冲四点生成：落子后形成"差一子成五"的点。返回 [(move, fps_set)]。"""
        moves = []
        for (x, y) in cands:
            if self.board.grid[y][x] != EMPTY:
                continue
            five, fps = self._probe(x, y, color)
            if five or not fps:
                continue                     # 直接成五另由 _five_points 处理
            moves.append(((x, y), fps))
        return moves

    def _makes_live_three(self, x: int, y: int, dx: int, dy: int) -> bool:
        """(x,y) 落己方后，该方向线是否出现含 (x,y) 的活三。

        铁律修复：己方子（含中心）一律记为 1（棋形的一部分），
        仅对方子/墙记为 2（挡）。旧实现把己方子也记成 2，导致新子
        永远无法与已有己方子连成三，n3 恒为 0，VCT 退化为"只追冲四"，
        算杀失去威胁构筑能力。
        """
        wc = self.wc
        pts = self._line_pts(x, y, dx, dy)
        idx = -1
        cells = []
        for t, (i, j) in enumerate(pts):
            v = self.board.grid[j][i]
            if i == x and j == y:
                idx = t
                cells.append(1)               # 假想落己方
            elif v == self.me:
                cells.append(1)               # 己方子计入棋形
            elif v == EMPTY:
                cells.append(0)
            else:
                cells.append(2)               # 对方/墙 = 挡
        if idx < 0:
            return False
        for (a, b, gap, cnt) in _find_groups(cells, wc):
            if cnt == wc - 2 and a <= idx <= b:
                _s, gcls = _grade_group(cells, a, b, gap, cnt, wc)
                if gcls == C_LIVE3:
                    return True
        return False

    def _threat_breaks(self, x: int, y: int, color: int) -> set:
        """(x,y) 落 color 新产生的活三的"破坏威胁点"（防守方可消除威胁的点）。

        与 _makes_live_three 同修：己方子记为 1，否则活三的形成与破点计算
        会漏掉与已有己方子相连的情形。
        """
        breaks: set = set()
        wc = self.wc
        for dx, dy in DIRS4:
            pts = self._line_pts(x, y, dx, dy)
            idx = -1
            cells = []
            for t, (i, j) in enumerate(pts):
                v = self.board.grid[j][i]
                if i == x and j == y:
                    idx = t
                    cells.append(1)
                elif v == self.me:
                    cells.append(1)
                elif v == EMPTY:
                    cells.append(0)
                else:
                    cells.append(2)
            if idx < 0:
                continue
            for (a, b, gap, cnt) in _find_groups(cells, wc):
                if cnt != wc - 2 or not (a <= idx <= b):
                    continue
                _s, gcls = _grade_group(cells, a, b, gap, cnt, wc)
                if gcls != C_LIVE3:
                    continue
                lo = max(0, a - 1)
                hi = min(len(cells), b + 2)
                for t in range(lo, hi):
                    if cells[t] == 0:
                        breaks.add(pts[t])
        return breaks

    # ---- VCF：连续冲四（最高优先级） ----
    def vcf(self, depth: int):
        try:
            return self._vcf(depth)
        except KillTimeout:
            return None
        finally:
            self.unwind()

    def _vcf(self, depth: int):
        self._tick()
        cands = self.board.get_candidates(radius=1)
        my5 = self._five_points(self.me, cands)
        if my5:
            return my5[0]                     # 直接连五
        if depth <= 0:
            return None
        foe5 = self._five_points(self.foe, cands)
        if foe5:
            # 对方双成五点（活四/双冲四）：一手堵不完 → 本节点必败，
            # 无 VCF 可言（旧实现允许"连堵两手"跳过对方回合 → 假算杀）。
            if len(foe5) >= 2:
                return None
            # 唯一成五点：强制堵；堵完后轮到对方，其反制冲四必须逐一验证。
            b = foe5[0]
            self._place(b[0], b[1], self.me)
            counters = [cm for (cm, _cf) in self._four_moves(self.foe, cands)[:4]
                        if cm != b]
            all_lose = True
            if counters:
                for cm in counters:
                    self._place(cm[0], cm[1], self.foe)
                    sub = self._vcf(depth - 2)
                    self._undo1()
                    if sub is None:
                        all_lose = False
                        break
            else:
                sub = self._vcf(depth - 1)   # 对方无反制：延续原递归（保守近似）
                all_lose = sub is not None
            self._undo1()
            if all_lose:
                return b
            return None
        moves = self._four_moves(self.me, cands)
        if not moves:
            return None
        moves.sort(key=lambda mv: -len(mv[1]))
        for (m, fps2) in moves[:20]:
            self._place(m[0], m[1], self.me)
            foe5b = self._five_points(self.foe, cands)
            if foe5b:
                self._undo1()                 # 我冲四但对方抢先连五 → 弃
                continue
            if len(fps2) >= 2:
                self._undo1()                 # 活四 / 双四：对手堵不完 → 必胜
                return m
            fp = next(iter(fps2))
            replies = [fp]
            for (cm, _cfps) in self._four_moves(self.foe, cands)[:4]:
                if cm != fp:
                    replies.append(cm)        # 对手反击冲四（我方下层强制堵）
            all_lose = True
            for r in replies[:6]:
                self._place(r[0], r[1], self.foe)
                sub = self._vcf(depth - 2)
                self._undo1()
                if sub is None:
                    all_lose = False
                    break
            self._undo1()
            if all_lose:
                return m
        return None

    # ---- VCT：连续威胁（第二优先级） ----
    def vct(self, depth: int):
        try:
            return self._vct(depth)
        except KillTimeout:
            return None
        finally:
            self.unwind()

    def _vct(self, depth: int):
        self._tick()
        cands = self.board.get_candidates(radius=2)
        my5 = self._five_points(self.me, cands)
        if my5:
            return my5[0]
        if depth <= 0:
            return None
        foe5 = self._five_points(self.foe, cands)
        if foe5:
            # 对方双成五点（活四/双冲四）：一手堵不完 → 本节点必败。
            # 旧实现"连堵两手"跳过对方回合，把对方的活四凭空化解 → 假算杀，
            # 导致 AI 在对方活三/活四在盘时仍"算杀成功"而拒不防守。
            if len(foe5) >= 2:
                return None
            # 唯一成五点：强制堵；堵完后对方的反制冲四必须逐一验证。
            b = foe5[0]
            self._place(b[0], b[1], self.me)
            counters = [cm for (cm, _cf) in self._four_moves(self.foe, cands)[:4]
                        if cm != b]
            all_lose = True
            if counters:
                for cm in counters:
                    self._place(cm[0], cm[1], self.foe)
                    sub = self._vct(depth - 2)
                    self._undo1()
                    if sub is None:
                        all_lose = False
                        break
            else:
                sub = self._vct(depth - 1)   # 对方无反制：延续原递归（保守近似）
                all_lose = sub is not None
            self._undo1()
            if all_lose:
                return b
            return None
        # MAX 层着法生成：冲四 + 活三（双威胁优先）
        # 对方"反手冲四"点（每节点只算一次，循环内复用）。
        # 铁律（2026-10-01 截图复盘）：只要对方存在"落子即成四"的反手，
        # 三三/四三捷径一律不成立——对方反四逼我方堵子、打断我方威胁链，
        # 我方的"必胜"是假的。旧版捷径跳过该验证 → 误判必胜 →
        # 面对对方跳活三拒不防守（走 (2,5)/(3,5) 而不堵 (6,5)）。
        foe_fours = self._four_moves(self.foe, cands)
        scored = []
        for (x, y) in cands:
            if self.board.grid[y][x] != EMPTY:
                continue
            five, fps = self._probe(x, y, self.me)
            s = 0
            if five:
                continue                      # 成五点已由 _five_points 覆盖
            if fps:
                s += 3000 * len(fps)
            n3 = 0
            for dx, dy in DIRS4:
                if self._makes_live_three(x, y, dx, dy):
                    n3 += 1
            s += 1000 * n3
            if s > 0:
                scored.append(((x, y), s, fps, n3))
        if not scored:
            return None
        scored.sort(key=lambda t: -t[1])
        for (m, _s, fps, n3) in scored[:16]:
            self._place(m[0], m[1], self.me)
            foe5b = self._five_points(self.foe, cands)
            if foe5b:
                self._undo1()
                continue
            if fps and len(fps) >= 2:
                self._undo1()                 # 活四/双四：我下一手连五比对方反四快 → 必胜
                return m
            if not foe_fours:
                if n3 >= 2:
                    self._undo1()             # 双活三且对方无反手四 → 对手堵不完 → 必胜
                    return m
                if fps and n3 > 0:
                    self._undo1()             # 四三且对方无反手四 → 必胜
                    return m
            replies: list = []
            if fps:
                replies.extend(list(fps)[:2])             # 堵成五点（强制）
            if n3:
                replies.extend(self._threat_breaks(m[0], m[1], self.me))
            # 对手反击：优先冲四，其次活三
            for (cm, _cfps) in foe_fours[:4]:
                replies.append(cm)
            seen: set = set()
            rr = []
            for r in replies:
                if r in seen or self.board.grid[r[1]][r[0]] != EMPTY:
                    continue
                seen.add(r)
                rr.append(r)
            rr = rr[:10]
            all_lose = bool(rr)
            for r in rr:
                self._place(r[0], r[1], self.foe)
                sub = self._vct(depth - 2)
                self._undo1()
                if sub is None:
                    all_lose = False
                    break
            self._undo1()
            if all_lose:
                return m
        return None
