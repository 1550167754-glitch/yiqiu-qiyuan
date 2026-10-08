"""
game.py —— 对局流程控制模块（状态机）

职责：
    1. 维护一局棋的完整状态：棋盘、双方棋手、轮次、本轮已落子数；
    2. 落子接口：落子 -> 胜负判定 -> 终局管理（胜 / 平 / 认输）；
    3. 轮次管理：黑第一手 1 子，此后每轮 1~2 子（符合六子棋规则）；
    4. 悔棋：按"轮"为单位撤销（一次撤销最近一整轮 1~2 子）；
    5. 支持三种对局模式：人机对战 / 人人对战 / 机机对战（AI 演示）。

规则回顾（Connect6）：
    - 黑方第一手只能下 1 子；
    - 之后双方每轮可下 1 子或 2 子；
    - 任一方向连成 6 子及以上即获胜。
"""
from __future__ import annotations

from .board import Board, BLACK, WHITE, OPPOSITE, COLOR_NAMES, SIZE, WIN_COUNT
from .ai import AI
from .llm_ai import LLMAI

MODE_HUMAN_AI = "human_ai"
MODE_HUMAN_HUMAN = "human_human"
MODE_AI_AI = "ai_ai"


class Player:
    """一名棋手（人类 / 本地 AI / 大模型 LLM）。

    属性：
        name       : 显示名（如 "玩家"、"AI-hard"、"千问(黑)"）
        kind       : 'human' / 'ai' / 'llm'
        difficulty : 本地 AI 难度（kind=='ai' 时有效）
        engine     : 落子引擎。本地 AI 为 AI 实例，LLM 为 LLMAI 实例，
                     两者接口一致：get_move(board, color, stones_to_place)。
    """

    def __init__(self, name: str = "玩家", kind: str = "human",
                 difficulty: str = "medium", llm: LLMAI | None = None):
        self.name = name
        self.kind = kind
        self.difficulty = difficulty
        if kind == "ai":
            self.engine = AI(difficulty=difficulty, seed=None)
        elif kind == "llm":
            self.engine = llm if llm is not None else LLMAI("qwen")
        else:
            self.engine = None

    @property
    def ai(self):
        """向后兼容：旧代码通过 player.ai 访问引擎。"""
        return self.engine

    def __repr__(self):
        return f"Player({self.name!r}, {self.kind})"


class Game:
    """一局六子棋的状态机。

    使用示例（人机对战，人执黑）：
        game = Game(black=Player("玩家"), white=Player("AI", kind="ai"))
        game.place(9, 9)          # 玩家落子（第一轮 1 子）
        game.end_round()          # 结束玩家本轮
        game.ai_turn()            # AI 出招（自动落 1~2 子并结束轮次）
    """

    def __init__(self, black: Player | None = None,
                 white: Player | None = None,
                 board: Board | None = None,
                 time_total: int = 1200,
                 time_per_move: int = 60,
                 variant: str = "connect6",
                 size: int = SIZE,
                 win_count: int = WIN_COUNT):
        if board is not None:
            self.board = board
        else:
            self.board = Board(size=size, win_count=win_count)
        self.variant = variant
        if black is None:
            black = Player("黑方")
        if white is None:
            white = Player("白方")
        self.players = {BLACK: black, WHITE: white}

        self.current = BLACK
        self.round_no = 1
        self.stones_this_round = 0
        self.max_stones = 1
        self.finished = False
        self.winner = None
        self.win_line = None
        self.reason = ""
        self.moves_log = []          # 每项: (x, y, color, round_no)
        self.last_ai_stones = []     # AI 本轮落下的子

        self.time_total = max(0, int(time_total))
        self.time_per_move = max(0, int(time_per_move))
        self.black_remain = float(self.time_total)
        self.white_remain = float(self.time_total)
        self.step_remain = float(self.time_per_move)
        self.timer_enabled = self.time_total > 0 or self.time_per_move > 0

    def current_player(self) -> Player:
        return self.players[self.current]

    def color_name(self, color: int) -> str:
        return COLOR_NAMES.get(color, "?")

    def place(self, x: int, y: int):
        """当前方在 (x, y) 落一子。

        返回 (是否成功, 提示信息, 获胜连线或 None)。
        落子后若连成六子，本方法直接置为终局。
        """
        if self.finished:
            return False, "对局已结束，请开始新对局", None
        if self.stones_this_round >= self.max_stones:
            return False, f"本轮已下满 {self.max_stones} 子，请结束回合", None

        color = self.current
        if not self.board.place(x, y, color):
            return False, "落子失败：该点已有棋子或坐标越界", None

        self.stones_this_round += 1
        self.moves_log.append((x, y, color, self.round_no))

        line = self.board.check_win(x, y)
        if line is not None:
            reason = self._win_reason()
            self._finish(color, reason, line)
            return True, f"{self.color_name(color)}获胜！({reason})", line

        if self.board.is_full():
            self._finish(None, "棋盘已满", None)
            return True, "平局：棋盘已满", None

        return True, "", None

    def end_round(self):
        """结束当前方本轮，切换到对方。

        注意：黑方第一轮只下 1 子；其余轮次双方最多 2 子。
        切换时刷新读秒：当前方步时重置为 time_per_move。
        """
        if self.finished:
            return
        self.current = OPPOSITE[self.current]
        self.round_no += 1
        self.stones_this_round = 0
        self.max_stones = self._max_stones_for(self.current)
        self.step_remain = float(self.time_per_move)

    def _max_stones_for(self, color: int) -> int:
        """计算某方在下一轮最多可下子数。

        - 五子棋：每轮固定 1 子；
        - 六子棋：黑方第 1 轮为 1，其余为 2。
        """
        if self.variant == "gomoku":
            return 1
        if color == BLACK and self.round_no == 1:
            return 1
        return 2

    def ai_turn(self, show_info: bool = False):
        """若当前轮到引擎棋手（本地 AI 或 LLM），自动落子并结束轮次。

        返回本轮落下的子（可能 1~2 个；人类轮次返回空列表）。
        """
        player = self.current_player()
        if player.kind == "human" or self.finished:
            return []

        stones = player.engine.get_move(self.board, self.current, self.max_stones)
        self.last_ai_stones = stones

        for x, y in stones:
            ok, msg, line = self.place(x, y)
            if line is not None:
                break

        self.end_round()

        if show_info:
            text = "、".join(f"({x},{y})" for x, y in stones)
            print(f"  {player.name} 落子：{text}")
        return stones

    def undo_round(self, to_human: bool = False):
        """撤销最近一整轮（1~2 子），回到该轮落子方重新行棋。

        to_human=True（人机模式悔棋）：连续撤销直到轮到人类棋手——一次
        撤销完整的"AI 一步 + 我方一步"，而不是只撤 AI（最近一轮）那步。
        双人/AI 互弈模式传 False，行为即"撤一轮"。
        若对局已终局，先解除终局状态再撤销（便于演示时回放）。
        返回撤销的子数（0 表示无可撤销）。
        """
        total = 0
        self.finished = False
        self.winner = None
        self.win_line = None
        self.reason = ""
        while self.moves_log:
            last_round = self.moves_log[-1][3]
            # 收集该轮全部落子（moves_log 已按时间先后排列，倒序收集同一轮号）
            removed = [m for m in reversed(self.moves_log) if m[3] == last_round]
            for _ in removed:
                self.board.undo()

            # 移除该轮的记录，保留其余
            self.moves_log = [m for m in self.moves_log if m[3] != last_round]

            self.round_no = last_round
            self.current = removed[-1][2]
            self.stones_this_round = 0
            self.max_stones = self._max_stones_for(self.current)
            self.step_remain = float(self.time_per_move)
            total += len(removed)

            if not to_human:
                break
            if self.current_player().kind == "human":
                break
            # 撤到的仍是 AI 轮（开局 AI 先行撤光时 current 停在 AI），
            # 由 GUI 的 _schedule_ai_turn 重新调度。
        return total

    def configure_timer(self, time_total: int, time_per_move: int):
        """配置双方总时间（秒）与每步限时（秒），<=0 表示不限。"""
        self.time_total = max(0, int(time_total))
        self.time_per_move = max(0, int(time_per_move))
        self.timer_enabled = self.time_total > 0 or self.time_per_move > 0

    def tick(self, dt: float):
        """扣减当前行棋方的时间。返回 None 或超时描述。

        每 250ms 由 GUI 调用一次；超时立即终局（对方获胜）。
        """
        if self.finished or not self.timer_enabled:
            return None

        loser = None

        if self.time_per_move > 0:
            self.step_remain = max(0.0, self.step_remain - dt)
            if self.step_remain <= 0:
                loser = self.current

        if self.time_total > 0:
            if self.current == BLACK:
                self.black_remain = max(0.0, self.black_remain - dt)
                if self.black_remain <= 0 and loser is None:
                    loser = BLACK
            else:
                self.white_remain = max(0.0, self.white_remain - dt)
                if self.white_remain <= 0 and loser is None:
                    loser = WHITE

        if loser is not None:
            winner = OPPOSITE[loser]
            self._finish(winner, f"{self.color_name(loser)}读秒超时", None)
            return f"{self.color_name(loser)}读秒超时"
        return None

    def current_remain(self) -> float:
        """当前行棋方的剩余总时间（秒）。"""
        return self.black_remain if self.current == BLACK else self.white_remain

    def time_str(self, seconds: float) -> str:
        """把秒数渲染为 mm:ss（总时间）或仅秒（步时较短时）。"""
        s = max(0, int(seconds + 0.5))
        return f"{s // 60}:{s % 60:02d}"

    def _finish(self, winner: int | None, reason: str,
                win_line: list | None = None):
        self.finished = True
        self.winner = winner
        self.reason = reason
        self.win_line = win_line

    def _win_reason(self) -> str:
        """获胜提示文案：随棋种（连六 / 连五）变化，供界面与兜底网统一引用。"""
        if self.variant == "connect6":
            return "连成六子"
        return f"连成{self.board.win_count}子"

    def resign(self):
        """当前方认输（CLI / GUI 均可调用）。"""
        if self.finished:
            return
        loser = self.current
        winner = OPPOSITE[loser]
        self._finish(winner, f"{self.color_name(loser)}认输", None)

    def result_text(self) -> str:
        """终局结果的展示文本。"""
        if self.winner is not None:
            return f"{self.color_name(self.winner)}获胜（{self.reason}）"
        if self.reason:
            return f"平局（{self.reason}）"
        return "对局进行中"

    def to_record(self) -> dict:
        """导出完整棋谱（JSON 友好结构），供 PostgreSQL 存档。"""
        moves = [[x, y, c] for x, y, c, _ in self.moves_log]
        if self.winner == BLACK:
            result = "BLACK"
        elif self.winner == WHITE:
            result = "WHITE"
        elif self.finished:
            result = "DRAW"
        else:
            result = "ABORT"
        return {
            "variant": self.variant,
            "size": self.board.size,
            "win_count": self.board.win_count,
            "round_no": self.round_no,
            "black": self.players[BLACK].name,
            "black_kind": self.players[BLACK].kind,
            "white": self.players[WHITE].name,
            "white_kind": self.players[WHITE].kind,
            "moves": moves,
            "result": result,
            "reason": self.reason,
        }
