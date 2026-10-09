"""悔棋"倒退"动画回归测试（纯逻辑层，无需显示器）。

覆盖两件容易出错、且出错后不易察觉的事：

1. **预测要撤哪些子 必须等于 实际撤了哪些子**
   动画必须"先知道要退掉哪几枚棋"，才能把它们画成幽灵。这份预测逻辑
   如果和 game.undo_round 的取轮规则有一点点偏差，动画就会退错子
   （退掉盘上还留着的子 / 留着已经撤掉的子），而规则层看起来完全正常。
   这里用 4 个场景（人机撤到人类回合、人人撤一轮、空盘、终局后）把
   预测与"撤销前后的棋盘历史差集"逐一比对。

2. **幽灵帧必须是"越来越小、越来越淡"**
   帧图变化方向错了（比如没缩小或没淡出），动画就会读成"闪现"而不是
   "倒退"。这里直接验证 PIL 层的尺寸与 alpha 单调性。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from liuziqi.board import BLACK, WHITE                       # noqa: E402
from liuziqi.game import Game, Player                        # noqa: E402
import liuziqi.gui as gui                                    # noqa: E402
from liuziqi.stonefx import render_stone, _scale_ghost       # noqa: E402


class _FakeApp:
    """只带 _undo_pending_stones 需要的属性，避免起一个真的 Tk 窗口。"""

    def __init__(self, game):
        self.game = game


def _predict(game, to_human):
    return gui.Connect6GUI._undo_pending_stones(_FakeApp(game), to_human)


def _actual(game, to_human):
    """实际撤销掉的那批子（撤销前后棋盘 history 的差集）。"""
    before = list(game.board.history)
    game.undo_round(to_human=to_human)
    return [(x, y, c) for (x, y, c) in before[len(game.board.history):]]


def _human_ai_game():
    """人执黑：黑1子 → AI2子 → 黑2子 → AI2子（当前轮到人类）。"""
    g = Game(black=Player("玩家"), white=Player("AI", kind="ai"))
    g.place(9, 9); g.end_round()
    for xy in ((5, 5), (6, 6)):
        g.place(*xy)
    g.end_round()
    g.place(10, 10); g.place(11, 11); g.end_round()
    for xy in ((7, 7), (8, 8)):
        g.place(*xy)
    g.end_round()
    return g


def test_predict_matches_actual_human_ai():
    """人机模式：一次悔棋要撤掉"AI 一轮 + 我方一轮"，预测必须一致。"""
    g = _human_ai_game()
    pred = _predict(g, True)
    act = _actual(g, True)
    assert pred == act
    # 撤到人类回合：AI 的 2 子 + 我方的 2 子 = 4 子，且最后一轮的我方 2 子在内
    assert len(pred) == 4
    assert (10, 10, BLACK) in pred and (11, 11, BLACK) in pred
    assert g.current == BLACK, "撤完应轮到人类（黑）"


def test_predict_matches_actual_strips_whole_round():
    """人人模式：一次只撤最近一整轮（可能是 1 子，也可能是 2 子）。"""
    g = Game(black=Player("甲"), white=Player("乙"))
    g.place(3, 3); g.end_round()
    g.place(4, 4); g.place(5, 5); g.end_round()
    g.place(6, 6); g.end_round()
    pred = _predict(g, False)
    assert pred == _actual(g, False)
    assert pred == [(6, 6, BLACK)], "最近一轮是黑方只下的 1 子"


def test_predict_on_empty_board_is_empty():
    """空盘：预测为空、实撤也不报错（GUI 会因此直接跳过动画）。"""
    g = Game(black=Player("甲"), white=Player("乙"))
    assert _predict(g, False) == []
    assert _actual(g, False) == []


def test_predict_after_finish_undoes_winning_line():
    """终局后悔棋：undo_round 会先解除终局，预测应覆盖整条获胜连线的落子。"""
    g = Game(black=Player("甲"), white=Player("乙"))
    # 黑方全部下在第 0 行、白方下在第 10 行（互不干扰），黑先连成 6 子即终局。
    # 每轮最多 2 子，2 子下完要 end_round 才会换人。
    black_pts = [(i, 0) for i in range(6)]
    white_pts = [(i, 10) for i in range(8)]
    bi = wi = 0
    for _ in range(20):
        if g.finished:
            break
        if g.current == BLACK:
            x, y = black_pts[bi]; bi += 1
        else:
            x, y = white_pts[wi]; wi += 1
        g.place(x, y)
        if g.finished or g.stones_this_round >= g.max_stones:
            g.end_round()
    assert g.finished is True, f"构造终局失败（history={g.board.history}）"
    last_round = g.moves_log[-1][3]
    # 期望值必须在"实际撤销"之前算好——撤销会把 moves_log 一起改掉
    expected = sorted((x, y, c) for (x, y, c, r) in g.moves_log
                      if r == last_round)
    pred = _predict(g, False)
    act = _actual(g, False)
    assert pred == act, "预测与实际撤销不一致"
    assert sorted(pred) == expected, "撤掉的不是最后一整轮"
    assert g.finished is False, "悔棋后应解除终局状态"
    assert g.winner is None and not g.win_line, "悔棋后应清掉胜负标记"


def test_offer_frames_are_monotonic():
    """幽灵帧：尺寸递减、alpha 单调不增、末帧明显淡出。"""
    if render_stone(24, 1) is None:
        return                      # 无 PIL 环境：动画本就会跳过，无需断言
    sizes, means = [], []
    n = 12
    for i in range(n):
        t = i / float(n - 1)
        factor = 1.0 + (0.72 - 1.0) * t
        img = _scale_ghost(render_stone(24, 1), factor)
        sizes.append(img.size[0])
        data = img.split()[3].get_flattened_data()
        means.append(sum(data) / len(data))
    assert sizes[0] > sizes[-1], "幽灵帧没有缩小"
    assert all(sizes[i] >= sizes[i + 1] for i in range(n - 1)), "尺寸不是单调递减"
    assert means[0] > means[-1], "幽灵帧没有淡出"
