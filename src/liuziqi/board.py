# -*- coding: utf-8 -*-
"""
board.py —— 六子棋棋盘数据结构与规则判定模块

本模块是整个程序的地基，负责：
    1. 棋盘的存储与初始化（19 x 19）；
    2. 落子、撤销、合法性检查（健壮性要求：非法落子返回失败而非异常）；
    3. 胜负判定：任一方向连成 6 子及以上即获胜，并返回获胜连线坐标
       （供界面高亮显示"致胜六连"，便于演示与答辩）；
    4. 为 AI 提供候选点生成（只搜索离已有棋子近的空点，大幅缩小搜索空间）。

存储结构说明（数据结构课程内容）：
    棋盘采用"二维数组"（逻辑结构为矩阵）存储，grid[y][x]：
        0 = 空(EMPTY)，1 = 黑(BLACK)，2 = 白(WHITE)
    落子历史用"栈"结构（history 列表）记录，支持一步撤销（悔棋 / AI 搜索回溯）。
"""
from __future__ import annotations

EMPTY = 0
BLACK = 1
WHITE = 2
SIZE = 19
WIN_COUNT = 6
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
COLOR_NAMES = {BLACK: "黑棋", WHITE: "白棋"}
OPPOSITE = {BLACK: WHITE, WHITE: BLACK}


class Board:
    """六子棋棋盘。

    属性：
        size       : 棋盘边长（默认 19）
        grid       : 二维数组 grid[y][x]，取值 EMPTY / BLACK / WHITE
        move_count : 当前已落子总数
        history    : 落子历史栈，元素为 (x, y, color)
    """

    def __init__(self, size: int = SIZE):
        self.size = size
        self.grid = [[EMPTY] * size for _ in range(size)]
        self.move_count = 0
        self.history: list[tuple[int, int, int]] = []

    def is_valid(self, x: int, y: int) -> bool:
        """坐标是否在棋盘范围内。"""
        return 0 <= x < self.size and 0 <= y < self.size

    def is_empty(self, x: int, y: int) -> bool:
        """坐标是否为空点（不在棋盘内也视为不空，保证健壮性）。"""
        return self.is_valid(x, y) and self.grid[y][x] == EMPTY

    def get(self, x: int, y: int) -> int:
        """取某点的颜色；越界返回 EMPTY（健壮性处理）。"""
        if not self.is_valid(x, y):
            return EMPTY
        return self.grid[y][x]

    def snapshot(self) -> "Board":
        """拷贝当前棋盘（深拷贝 grid / history / move_count）。

        用于后台线程读取局面（如 LLM 胜率评估），避免与主线程竞争。
        """
        b = Board(self.size)
        b.grid = [row[:] for row in self.grid]
        b.move_count = self.move_count
        b.history = list(self.history)
        return b

    def is_full(self) -> bool:
        """棋盘是否已下满（用于平局判定）。"""
        return self.move_count >= self.size * self.size

    def place(self, x: int, y: int, color: int) -> bool:
        """在 (x, y) 落一子。

        返回 True 表示成功；失败（越界 / 已有子 / 非法颜色）返回 False，
        程序对非法输入能"适当做出反应"，而非抛异常。
        """
        if not self.is_empty(x, y):
            return False
        if color not in (BLACK, WHITE):
            return False
        self.grid[y][x] = color
        self.move_count += 1
        self.history.append((x, y, color))
        return True

    def undo(self) -> tuple[int, int, int] | None:
        """撤销最后一手（悔棋 / AI 搜索回溯共用）。

        返回被撤销的 (x, y, color)；空棋盘时返回 None。
        """
        if not self.history:
            return None
        x, y, color = self.history.pop()
        self.grid[y][x] = EMPTY
        self.move_count -= 1
        return (x, y, color)

    def check_win(self, x: int, y: int) -> list[tuple[int, int]] | None:
        """判定 (x, y) 处刚落下的棋子是否已形成胜局。

        判定方法：以 (x, y) 为中心，沿四个方向（横 / 竖 / 两条斜线）
        分别向两端延伸，统计同色连续子数；任一方连续数 >= 6 即获胜。

        返回：
            - 获胜：该方向上整条连线的坐标列表（供界面高亮显示）
            - 未获胜：None
        """
        color = self.get(x, y)
        if color == EMPTY:
            return None
        for dx, dy in DIRECTIONS:
            line = [(x, y)]
            # 向正方向延伸
            i, j = x + dx, y + dy
            while self.is_valid(i, j) and self.grid[j][i] == color:
                line.append((i, j))
                i += dx
                j += dy
            # 向负方向延伸
            i, j = x - dx, y - dy
            while self.is_valid(i, j) and self.grid[j][i] == color:
                line.insert(0, (i, j))
                i -= dx
                j -= dy
            if len(line) >= WIN_COUNT:
                return line
        return None

    def scan_win(self):
        """全盘扫描胜负（兜底判定）。

        与 check_win(x, y) 的"只看最后一手"互为冗余：无论终局信号经由哪条
        路径丢失，只要盘面上客观存在 ≥6 连，这里都能把它找回来。
        只把每条同色线段的"起点"（前一格非同色）作为种子，复杂度 O(格数×4)。

        返回 (winner, line)；无胜局返回 (None, None)。
        """
        for y in range(self.size):
            for x in range(self.size):
                c = self.grid[y][x]
                if c == EMPTY:
                    continue
                for dx, dy in DIRECTIONS:
                    px, py = x - dx, y - dy
                    if self.is_valid(px, py) and self.grid[py][px] == c:
                        continue                     # 非线段起点，跳过
                    line = []
                    i, j = x, y
                    while self.is_valid(i, j) and self.grid[j][i] == c:
                        line.append((i, j))
                        i += dx
                        j += dy
                    if len(line) >= WIN_COUNT:
                        return c, line
        return None, None

    def get_candidates(self, radius: int = 2,
                       limit: int | None = None) -> list[tuple[int, int]]:
        """生成 AI 可落子的候选点。

        思路：棋盘上可落子的空点最多有 361 个，若全部参与搜索则搜索
        空间巨大。实际对局中，有价值的落点一定靠近已有棋子，因此只收集
        距任意已有棋子"切比雪夫距离 <= radius"的空点（典型 radius=2），
        可将候选点压缩到几十个，搜索效率大幅提升。

        返回：按 (y, x) 升序排序的候选点列表。
        """
        if self.move_count == 0:
            c = self.size // 2
            return [(x, y)
                    for y in range(c - 1, c + 2)
                    for x in range(c - 1, c + 2)
                    if self.is_empty(x, y)]
        occupied = set()
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] != EMPTY:
                    occupied.add((x, y))
        cands = set()
        for x, y in occupied:
            for j in range(y - radius, y + radius + 1):
                for i in range(x - radius, x + radius + 1):
                    if self.is_empty(i, j):
                        cands.add((i, j))
        result = sorted(cands, key=lambda p: (p[1], p[0]))
        if limit is not None:
            result = result[:limit]
        return result

    def display(self) -> str:
        """把棋盘打印成文本（CLI 模式 / 调试用）。

        列坐标用 A-S 表示，行坐标 1-19。黑子 'X'，白子 'O'，空点 '.'。
        """
        header = "   " + " ".join(chr(ord("A") + i) for i in range(self.size))
        lines = [header]
        for y in range(self.size):
            row = f"{y + 1:2d} "
            for x in range(self.size):
                c = self.grid[y][x]
                row += "X " if c == BLACK else "O " if c == WHITE else ". "
            lines.append(row.rstrip())
        return "\n".join(lines)
