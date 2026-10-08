"""棋盘模型（Board）回归测试：候选点、非法落子、胜负判定与悔棋。

check_win / scan_win 是刻意冗余的双判定实现，二者一致性是重要不变量。
"""
from liuziqi.board import Board, BLACK, WHITE, EMPTY


def test_empty_board_candidates():
    bd = Board(size=15, win_count=5)
    # 空盘候选点为中心 3x3 = 9
    assert len(bd.get_candidates(2)) == 9


def test_one_stone_candidates():
    bd = Board(size=15, win_count=5)
    bd.place(7, 7, BLACK)
    # 落一子后候选点扩展为半径 2 的 5x5 环 = 24
    assert len(bd.get_candidates(2)) == 24


def test_place_invalid_returns_false():
    bd = Board(size=15, win_count=5)
    assert bd.place(20, 20, BLACK) is False
    assert bd.place(7, 7, BLACK) is True
    assert bd.place(7, 7, WHITE) is False  # 已有子
    assert bd.grid[7][7] == BLACK
    assert bd.move_count == 1


def test_win_detection():
    bd = Board(size=15, win_count=5)
    for x in range(5):
        bd.place(x, 0, BLACK)
    line = bd.check_win(2, 0)
    assert line is not None
    assert bd.scan_win() is not None


def test_no_win_is_none():
    bd = Board(size=15, win_count=5)
    assert bd.scan_win() == (None, None)


def test_undo_restores():
    bd = Board(size=15, win_count=5)
    bd.place(7, 7, BLACK)
    bd.undo()
    assert bd.grid[7][7] == EMPTY
    assert bd.move_count == 0


def test_win_double_check_consistency():
    # 在同一点落子时，局部 check_win 与全局 scan_win 对"是否有胜"应当一致
    bd = Board(size=15, win_count=5)
    for x in range(5):
        bd.place(x, 0, BLACK)
    has_local = bd.check_win(2, 0) is not None
    has_global = bd.scan_win() is not None
    assert has_local == has_global
