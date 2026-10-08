# -*- coding: utf-8 -*-
"""
winrate.py —— 胜率预测（本地评估，稳定平滑版）

组成：
    1. 本地评估（winrate_black）：基于局面评估分数，sigmoid 映射为黑方胜率。

稳定性设计（修复"数值不准 / 频繁乱跳"）：
    - sigmoid 温度 _SCALE 取 5000：活三(+1500) 约 57%、活四(+20000) 约
      98%、空盘 50%，曲线温和，不会因一两颗子的微小分差大幅跳变；
    - 概率钳制在 [0.02, 0.98]，不顶到 0/1 造成视觉突兀；
    - GUI 层再做指数平滑（EMA），双保险。

胜率约定：返回黑方胜率 (0.0, 1.0)。
"""
from __future__ import annotations

import math

from .board import Board, BLACK
from .ai import _Eval

_SCALE = 5000.0
_FLOOR = 0.02
_CEIL = 0.98


def winrate_black(board: Board) -> float:
    """本地评估：黑方胜率（0.0~1.0）。"""
    if board.move_count == 0:
        return 0.5
    score = _Eval(board).evaluate(BLACK)
    p = 1.0 / (1.0 + math.exp(-score / _SCALE))
    return max(_FLOOR, min(_CEIL, p))


def winrate_white(board: Board) -> float:
    """白方胜率。"""
    return 1.0 - winrate_black(board)
