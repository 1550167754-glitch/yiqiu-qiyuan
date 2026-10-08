# -*- coding: utf-8 -*-
"""
xiangqi.py —— 中国象棋（Xiangqi）棋盘模型与完整规则引擎

设计目标：
    - 纯逻辑、无 GUI 依赖，便于单元测试与后续接入 AI；
    - 完整实现中国象棋规则：将/士/象/马/车/炮/兵七种棋子走法，
      含马蹩腿、象塞眼、炮隔子吃、兵过河、将帅不可照面（飞将）；
    - 将军 / 将死 / 困毙（无合法着法即判负）判定；
    - apply / undo 支持悔棋；人人可玩，暂不内置 AI。

坐标约定：
    - 棋盘 9 列 × 10 行，square = (x, y)，x∈[0,8] 左→右，y∈[0,9] 上→下；
    - 黑方（black）居上（y=0 为底线的将），红方（red）居下（y=9 为底线的帅），
      红方先行（与传统一致）；红向前 = y 减小，黑向前 = y 增大。
"""

from __future__ import annotations

RED = "r"
BLACK = "b"

KING = "K"       # 帅 / 将
ADVISOR = "A"    # 仕 / 士
ELEPHANT = "E"   # 相 / 象
HORSE = "H"      # 马
CHARIOT = "R"    # 车
CANNON = "C"     # 炮 / 砲
PAWN = "P"       # 兵 / 卒

# 棋子字形：**红方用繁体（車馬將砲），黑方用简体（车马将炮）**，
# 与传统象棋实物一致，也让双方在棋盘上一眼可辨。
# 相/仕/士/兵/卒 繁简同形，无需区分。
PIECE_CHAR = {
    (RED, KING): "帥", (BLACK, KING): "将",
    (RED, ADVISOR): "仕", (BLACK, ADVISOR): "士",
    (RED, ELEPHANT): "相", (BLACK, ELEPHANT): "象",
    (RED, HORSE): "馬", (BLACK, HORSE): "马",
    (RED, CHARIOT): "車", (BLACK, CHARIOT): "车",
    (RED, CANNON): "砲", (BLACK, CANNON): "炮",
    (RED, PAWN): "兵", (BLACK, PAWN): "卒",
}

COLOR_CN = {RED: "红", BLACK: "黑"}

_COLS = 9
_ROWS = 10


def opp(color: str) -> str:
    return BLACK if color == RED else RED


def _in_palace(x: int, y: int, color: str) -> bool:
    if not (3 <= x <= 5):
        return False
    return (7 <= y <= 9) if color == RED else (0 <= y <= 2)


def _crossed_river(y: int, color: str) -> bool:
    """兵/卒是否已过河（位于对方半场）。"""
    return y <= 4 if color == RED else y >= 5


def initial_grid():
    """返回标准开局 10×9 网格（grid[y][x] = (color, kind) 或 None）。"""
    g = [[None] * _COLS for _ in range(_ROWS)]
    back = [CHARIOT, HORSE, ELEPHANT, ADVISOR, KING, ADVISOR, ELEPHANT, HORSE, CHARIOT]
    for x in range(_COLS):
        g[0][x] = (BLACK, back[x])
        g[9][x] = (RED, back[x])
    g[2][1] = (BLACK, CANNON)
    g[2][7] = (BLACK, CANNON)
    g[7][1] = (RED, CANNON)
    g[7][7] = (RED, CANNON)
    for x in (0, 2, 4, 6, 8):
        g[3][x] = (BLACK, PAWN)
        g[6][x] = (RED, PAWN)
    return g


class XiangqiBoard:
    """中国象棋规则引擎。人人可玩，提供合法着法生成、将军/将死判定、悔棋。"""

    def __init__(self):
        self.reset()

    # --------------------------------------------------------------- 基础
    def reset(self):
        self.grid = initial_grid()
        self.turn = RED
        self.history: list = []          # (fx, fy, tx, ty, captured)
        self.game_over = False
        self.winner: str | None = None

    def piece(self, x: int, y: int):
        if 0 <= x < _COLS and 0 <= y < _ROWS:
            return self.grid[y][x]
        return None

    @staticmethod
    def inside(x: int, y: int) -> bool:
        return 0 <= x < _COLS and 0 <= y < _ROWS

    # ----------------------------------------------------- 单子着法生成
    def _piece_moves(self, x: int, y: int, p):
        """返回棋子 p（位于 x,y）的伪合法目标格列表（含吃子，未校验将帅安全）。"""
        color, kind = p
        res: list = []

        if kind == KING:
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = x + dx, y + dy
                if _in_palace(nx, ny, color):
                    t = self.piece(nx, ny)
                    if t is None or t[0] != color:
                        res.append((nx, ny))
            # 飞将：同列且中间无子，可"吃"掉对方将/帅（合法制胜着法）
            ek = self._find_king(opp(color))
            if ek:
                ex, ey = ek
                if ex == x:
                    step = 1 if ey > y else -1
                    clear = True
                    yy = y + step
                    while yy != ey:
                        if self.piece(x, yy) is not None:
                            clear = False
                            break
                        yy += step
                    if clear:
                        res.append((ex, ey))

        elif kind == ADVISOR:
            for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                nx, ny = x + dx, y + dy
                if _in_palace(nx, ny, color):
                    t = self.piece(nx, ny)
                    if t is None or t[0] != color:
                        res.append((nx, ny))

        elif kind == ELEPHANT:
            for dx, dy in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
                nx, ny = x + dx, y + dy
                if not self.inside(nx, ny):
                    continue
                if color == RED and ny < 5:
                    continue
                if color == BLACK and ny > 4:
                    continue
                if self.piece(x + dx // 2, y + dy // 2) is not None:  # 塞象眼
                    continue
                t = self.piece(nx, ny)
                if t is None or t[0] != color:
                    res.append((nx, ny))

        elif kind == HORSE:
            # (走法, 蹩腿相对位置)
            legs = [
                ((2, 1), (1, 0)), ((2, -1), (1, 0)),
                ((-2, 1), (-1, 0)), ((-2, -1), (-1, 0)),
                ((1, 2), (0, 1)), ((1, -2), (0, -1)),
                ((-1, 2), (0, 1)), ((-1, -2), (0, -1)),
            ]
            for (dx, dy), (lx, ly) in legs:
                if self.piece(x + lx, y + ly) is not None:  # 蹩马腿
                    continue
                nx, ny = x + dx, y + dy
                if not self.inside(nx, ny):
                    continue
                t = self.piece(nx, ny)
                if t is None or t[0] != color:
                    res.append((nx, ny))

        elif kind == CHARIOT:
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = x + dx, y + dy
                while self.inside(nx, ny):
                    t = self.piece(nx, ny)
                    if t is None:
                        res.append((nx, ny))
                    else:
                        if t[0] != color:
                            res.append((nx, ny))
                        break
                    nx += dx
                    ny += dy

        elif kind == CANNON:
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = x + dx, y + dy
                # 非吃子：滑行至第一个棋子之前
                while self.inside(nx, ny) and self.piece(nx, ny) is None:
                    res.append((nx, ny))
                    nx += dx
                    ny += dy
                # 隔一子（炮架）后，落于第一个敌子
                if self.inside(nx, ny):
                    sx, sy = nx, ny
                    nx += dx
                    ny += dy
                    while self.inside(nx, ny):
                        t = self.piece(nx, ny)
                        if t is not None:
                            if t[0] != color:
                                res.append((nx, ny))
                            break
                        nx += dx
                        ny += dy

        elif kind == PAWN:
            fwd = -1 if color == RED else 1
            nx, ny = x, y + fwd
            if self.inside(nx, ny):
                t = self.piece(nx, ny)
                if t is None or t[0] != color:
                    res.append((nx, ny))
            if _crossed_river(y, color):  # 过河后可平移
                for dx in (1, -1):
                    nx, ny = x + dx, y
                    if self.inside(nx, ny):
                        t = self.piece(nx, ny)
                        if t is None or t[0] != color:
                            res.append((nx, ny))

        return res

    # ----------------------------------------------------- 全局着法枚举
    def moves_of(self, color):
        for y in range(_ROWS):
            for x in range(_COLS):
                p = self.grid[y][x]
                if p is None or p[0] != color:
                    continue
                for to in self._piece_moves(x, y, p):
                    yield (x, y, to[0], to[1])

    def legal_moves(self, color=None):
        """返回当前（或指定）一方的全部合法着法：[(from), (to)] 列表。"""
        if color is None:
            color = self.turn
        legal = []
        for (fx, fy, tx, ty) in self.moves_of(color):
            moving = self.grid[fy][fx]
            captured = self.grid[ty][tx]
            self.grid[ty][tx] = moving
            self.grid[fy][fx] = None
            safe = not self.in_check(color)
            self.grid[fy][fx] = moving
            self.grid[ty][tx] = captured
            if safe:
                legal.append(((fx, fy), (tx, ty)))
        return legal

    # ----------------------------------------------------- 将军 / 攻击判定
    def _find_king(self, color: str):
        for y in range(_ROWS):
            for x in range(_COLS):
                p = self.grid[y][x]
                if p and p[0] == color and p[1] == KING:
                    return (x, y)
        return None

    def in_check(self, color: str) -> bool:
        """color 方的主帅是否处于被攻击（含被飞将照面）状态。"""
        kpos = self._find_king(color)
        if kpos is None:
            return True  # 主帅已被吃，等价于被将死
        enemy = opp(color)
        return self.square_attacked(kpos[0], kpos[1], enemy)

    def square_attacked(self, tx: int, ty: int, by_color: str) -> bool:
        for y in range(_ROWS):
            for x in range(_COLS):
                p = self.grid[y][x]
                if p is None or p[0] != by_color:
                    continue
                if (tx, ty) in self._piece_moves(x, y, p):
                    return True
        return False

    # ----------------------------------------------------- 落子 / 悔棋
    def apply(self, frm, to):
        """执行一着（前提：已确认合法）。返回被吃棋子或 None。"""
        fx, fy = frm
        tx, ty = to
        moving = self.grid[fy][fx]
        captured = self.grid[ty][tx]
        self.history.append((fx, fy, tx, ty, captured))
        self.grid[ty][tx] = moving
        self.grid[fy][fx] = None

        if captured is not None and captured[1] == KING:
            self.game_over = True
            self.winner = moving[0]
            return captured

        self.turn = opp(self.turn)
        if not self.legal_moves(self.turn):
            # 无合法着法：将死或困毙，均判负（中国象棋规则）
            self.game_over = True
            self.winner = moving[0]
        return captured

    def undo(self):
        if not self.history:
            return
        fx, fy, tx, ty, captured = self.history.pop()
        moving = self.grid[ty][tx]
        self.grid[fy][fx] = moving
        self.grid[ty][tx] = captured
        self.turn = opp(self.turn)
        self.game_over = False
        self.winner = None

    # ----------------------------------------------------- FEN 导出
    # 皮卡鱼（Stockfish 象棋分支）字母约定：K将帅 A仕士 B相象 N马 R车 C炮 P兵卒，
    # 大写=红（先手方 w）、小写=黑；首行是黑方底线（y=0）。
    _FEN_CHAR = {KING: "K", ADVISOR: "A", ELEPHANT: "B",
                 HORSE: "N", CHARIOT: "R", CANNON: "C", PAWN: "P"}

    def uci_move(self, frm, to) -> str:
        """(x,y) → 皮卡鱼 UCI 坐标（file a-i = x，rank 0-9 = 9-y）。"""
        return (chr(ord("a") + frm[0]) + str(9 - frm[1])
                + chr(ord("a") + to[0]) + str(9 - to[1]))

    @staticmethod
    def parse_uci_move(s: str):
        """皮卡鱼 bestmove（如 h2e2）→ ((x,y),(x,y))；非法返回 None。"""
        s = s.strip()
        if len(s) < 4:
            return None
        try:
            fx = ord(s[0]) - ord("a")
            fy = 9 - int(s[1])
            tx = ord(s[2]) - ord("a")
            ty = 9 - int(s[3])
        except (ValueError, IndexError):
            return None
        if not (0 <= fx < _COLS and 0 <= tx < _COLS
                and 0 <= fy < _ROWS and 0 <= ty < _ROWS):
            return None
        return ((fx, fy), (tx, ty))
