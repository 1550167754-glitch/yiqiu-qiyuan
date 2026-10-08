"""对局状态机（Game）回归测试：轮次规则与悔棋。

锁定 Connect6 关键规则：黑首轮仅 1 子，其余轮次最多 2 子；悔棋按"轮"撤销。
"""
from liuziqi.game import Game, Player
from liuziqi.board import EMPTY


def test_first_round_one_stone():
    g = Game(black=Player(), white=Player())
    assert g.max_stones == 1  # 黑方第一手只能下 1 子
    ok, _, _ = g.place(7, 7)
    assert ok is True
    assert g.stones_this_round == 1
    assert g.finished is False


def test_end_round_advances():
    g = Game(black=Player(), white=Player())
    g.place(7, 7)
    g.end_round()
    assert g.round_no == 2
    assert g.max_stones == 2  # 此后每轮最多 2 子


def test_undo_round():
    g = Game(black=Player(), white=Player())
    g.place(7, 7)
    g.end_round()
    assert g.round_no == 2
    removed = g.undo_round()
    assert removed >= 1
    assert g.round_no == 1
    assert g.board.grid[7][7] == EMPTY
