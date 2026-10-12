# -*- coding: utf-8 -*-
"""Rapfi 五子棋引擎（piskvork 协议子进程）回归测试。

覆盖：引擎探测、协议应答、战术必杀/必堵、AI 路由（仅五子棋 hard 档）、
六子棋不路由、禁用/失败回退内置引擎、stop 杀进程与自动重启。

引擎不可用（engine/rapfi/ 未放置或 config enabled=false）时，
协议相关用例 skip（Skipped：pytest 与 scripts/运行测试.py 均识别）；
回退用例始终执行（它们验证的正是"没有引擎"的路径）。
本文件不依赖 pytest——monkeypatch 改用手动存取复原。
"""
try:                                    # 让 pytest 也能正确显示 skip
    from _pytest.outcomes import Skipped as _PytestSkipped
except Exception:                       # pragma: no cover - 无 pytest 环境
    _PytestSkipped = Exception


class Skipped(_PytestSkipped):
    """引擎不可用时的跳过信号。"""


def _need_engine():
    if not rapfi_engine.available():
        raise Skipped("Rapfi 引擎不可用（engine/rapfi/ 或 config enabled=false）")


from liuziqi.ai import AI
from liuziqi.board import BLACK, WHITE, Board
from liuziqi import rapfi_engine


def _gomoku(stones):
    """构造五子棋棋盘：stones = [(x, y, color), ...]（黑先，按序落子）。"""
    bd = Board(size=15, win_count=5)
    for x, y, c in stones:
        assert bd.place(x, y, c), f"构造失败: {(x, y, c)}"
    return bd


def _side_to_move(bd):
    """按黑先规则推断当前行棋方（与 piskvork 子数奇偶一致）。"""
    n1 = sum(1 for _, _, c in bd.history if c == BLACK)
    n2 = sum(1 for _, _, c in bd.history if c == WHITE)
    return BLACK if n1 == n2 else WHITE


# ------------------------------------------------------------ 探测
def test_find_engine():
    _need_engine()
    exe = rapfi_engine.find_engine()
    assert exe and exe.lower().endswith(".exe")


# ------------------------------------------------------------ 协议与战术
def test_engine_opens_near_center():
    _need_engine()
    eng = rapfi_engine.RapfiEngine(time_limit_ms=800)
    try:
        bd = _gomoku([])
        mv = eng.best_move(bd, BLACK)
        assert mv is not None
        x, y = mv
        assert 0 <= x < 15 and 0 <= y < 15 and bd.grid[y][x] == 0
        # 首着应在天元附近（强引擎开局共识）
        assert abs(x - 7) <= 2 and abs(y - 7) <= 2
    finally:
        eng.close()


def test_engine_completes_five():
    """黑已有横四 (7,5)-(7,8) 且两端皆空 → 引擎执黑必须成五。"""
    _need_engine()
    eng = rapfi_engine.RapfiEngine(time_limit_ms=800)
    try:
        stones = [(7, 5, BLACK), (7, 6, BLACK), (7, 7, BLACK), (7, 8, BLACK),
                  (0, 0, WHITE), (0, 1, WHITE), (0, 2, WHITE), (0, 3, WHITE)]
        bd = _gomoku(stones)
        assert _side_to_move(bd) == BLACK
        mv = eng.best_move(bd, BLACK)
        assert mv in {(7, 4), (7, 9)}, f"应补成五，实际 {mv}"
    finally:
        eng.close()


def test_engine_blocks_live_four():
    """黑活四已成 → 引擎执白必须堵一端。"""
    _need_engine()
    eng = rapfi_engine.RapfiEngine(time_limit_ms=800)
    try:
        stones = [(7, 5, BLACK), (7, 6, BLACK), (7, 7, BLACK), (7, 8, BLACK),
                  (0, 0, WHITE), (1, 0, WHITE), (2, 0, WHITE)]
        bd = _gomoku(stones)
        assert _side_to_move(bd) == WHITE
        mv = eng.best_move(bd, WHITE)
        assert mv in {(7, 4), (7, 9)}, f"应堵活四，实际 {mv}"
    finally:
        eng.close()


def test_engine_rejects_inconsistent_side():
    """请求方颜色与 history 奇偶矛盾 → 返回 None（绝不落到错误颜色）。"""
    _need_engine()
    eng = rapfi_engine.RapfiEngine(time_limit_ms=800)
    try:
        bd = _gomoku([(7, 7, BLACK)])   # 该白走，却请求黑
        assert eng.best_move(bd, BLACK) is None
    finally:
        eng.close()


def test_engine_respawn_after_stop():
    """stop 杀进程后，下一次 best_move 自动重启并正常应答。"""
    _need_engine()
    eng = rapfi_engine.RapfiEngine(time_limit_ms=800)
    bd = _gomoku([(7, 7, BLACK), (8, 8, WHITE)])
    mv1 = eng.best_move(bd, BLACK)
    assert mv1 is not None
    eng.stop()
    assert not eng._alive()
    mv2 = eng.best_move(bd, BLACK)
    assert mv2 is not None and eng._alive()
    eng.close()


# ------------------------------------------------------------ AI 路由
def test_ai_hard_gomoku_routes_to_rapfi():
    """五子棋 hard：get_move 走 Rapfi，返回合法单点。"""
    _need_engine()
    ai = AI(difficulty="hard")
    bd = _gomoku([(7, 7, BLACK), (7, 8, WHITE)])
    mv = ai.get_move(bd, BLACK, 1)
    assert len(mv) == 1
    x, y = mv[0]
    assert bd.grid[y][x] == 0
    assert ai._rapfi is not None          # 确实走了 Rapfi 路径
    ai.stop()


def test_ai_hard_connect6_stays_builtin():
    """六子棋（win_count==6）不路由 Rapfi，走内置引擎。"""
    bd = Board(size=19, win_count=6)
    ai = AI(difficulty="hard")
    mv = ai.get_move(bd, BLACK, 1)        # 黑首回合只 1 子
    assert 1 <= len(mv) <= 2
    assert all(bd.grid[y][x] == 0 for x, y in mv)
    assert ai._rapfi is None              # 未触碰 Rapfi
    ai.stop()


def test_ai_fallback_when_engine_disabled():
    """Rapfi 不可用时 hard 档逐次回退内置引擎，仍返回合法着法。"""
    old = rapfi_engine.available
    rapfi_engine.available = lambda: False
    try:
        ai = AI(difficulty="hard")
        bd = _gomoku([(7, 7, BLACK), (7, 8, WHITE)])
        mv = ai.get_move(bd, BLACK, 1)
        assert len(mv) == 1 and bd.grid[mv[0][1]][mv[0][0]] == 0
        assert ai._rapfi is None
    finally:
        rapfi_engine.available = old
