"""中国象棋规则引擎回归测试。

覆盖初始局面不变量、悔棋往返、UCI 坐标往返、飞将照面判定。
这些不变量正是 10-01 几个算杀/规则修复的回归锚点，改动引擎时必须保持。
"""
import copy

from liuziqi.xiangqi import XiangqiBoard, RED, BLACK, KING


def test_initial_legal_moves():
    b = XiangqiBoard()
    # 标准开局红方/黑方合法着法均为 44（单车双炮九兵 + 两马/两相/两士活动）
    assert len(b.legal_moves(RED)) == 44
    assert len(b.legal_moves(BLACK)) == 44


def test_apply_undo_roundtrip():
    b = XiangqiBoard()
    snap = copy.deepcopy(b.grid)
    move = b.legal_moves(RED)[0]
    b.apply(move[0], move[1])
    assert b.turn == BLACK
    b.undo()
    assert b.grid == snap
    assert b.turn == RED
    assert b.game_over is False
    assert b.winner is None


def test_uci_roundtrip():
    b = XiangqiBoard()
    for move in b.legal_moves(RED)[:8]:
        uci = b.uci_move(move[0], move[1])
        parsed = XiangqiBoard.parse_uci_move(uci)
        assert parsed == move, f"UCI 往返失败: {move} -> {uci} -> {parsed}"


def test_flying_general_in_check():
    # 构造只有将帅隔列对望的局面：飞将规则下双方互为被将
    b = XiangqiBoard()
    b.reset()
    b.grid = [[None] * 9 for _ in range(10)]
    b.grid[9][4] = (RED, KING)
    b.grid[0][4] = (BLACK, KING)
    b.turn = RED
    assert b.in_check(RED) is True
    assert b.in_check(BLACK) is True
