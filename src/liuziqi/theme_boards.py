"""
theme_boards.py —— 棋盘主题模块（5 种可选棋盘皮肤）

为什么用"程序化矢量绘制"而不是网上贴图：
    1. 矢量绘制在任意分辨率 / 任意缩放下都清晰锐利，不会出现网图
       放大后模糊、失真的问题（高分屏尤其明显）；
    2. 无版权风险、离线可用、体积为零。

自定义图片棋盘（可选扩展）：
    把 PNG / GIF 图片命名为 board_custom.png / board_custom.gif
    （第 6 号主题）放入 assets/boards/，程序会自动加载为额外主题
    （tkinter PhotoImage 原生支持 PNG/GIF；JPG 需安装 Pillow）。

每种主题参数：
    bg_a / bg_b : 背景渐变起止色
    line        : 网格线颜色
    star        : 星位颜色
    coord       : 坐标文字颜色
    grain       : 木纹颜色（None = 无纹理，如石板 / 墨玉）
    stone_edge  : 棋子描边微调（浅色盘用深边，深色盘用亮边）
"""
from __future__ import annotations
import os

THEME_NAMES = ["经典原木", "胡桃深木", "石板灰", "墨玉黑", "青瓷绿"]

THEME_PARAMS = {
    "经典原木": dict(bg_a="#EACD96", bg_b="#D8B276", line="#4A3B28",
                     star="#4A3B28", coord="#5A4A34", grain="#C89B5F",
                     stone_black_outline="#000000", stone_white_outline="#8A8A8A"),
    "胡桃深木": dict(bg_a="#8A5A33", bg_b="#6E4223", line="#3A2415",
                     star="#2E1D10", coord="#E8D8C0", grain="#5C3618",
                     stone_black_outline="#000000", stone_white_outline="#6A6A6A"),
    "石板灰": dict(bg_a="#B9BEC4", bg_b="#98A0A8", line="#4A5058",
                   star="#3E444C", coord="#3A4048", grain=None,
                   stone_black_outline="#000000", stone_white_outline="#707880"),
    "墨玉黑": dict(bg_a="#2E3440", bg_b="#22272F", line="#6E7A8A",
                  star="#8A98A8", coord="#9AA6B4", grain=None,
                  stone_black_outline="#000000", stone_white_outline="#C8D0DA"),
    "青瓷绿": dict(bg_a="#BFD8CC", bg_b="#9EBFAF", line="#3E5C50",
                   star="#32493F", coord="#38524A", grain="#8FB0A0",
                   stone_black_outline="#000000", stone_white_outline="#7A9A8C"),
}


def get_theme(name: str) -> dict:
    """按名称取主题参数；未知名称回退经典原木。"""
    return THEME_PARAMS.get(name, THEME_PARAMS[THEME_NAMES[0]])


def blend(c1: str, c2: str, ratio: float) -> str:
    """两个 #RRGGBB 颜色按比例混合（供渐变使用）。"""
    r = int(int(c1[1:3], 16) + (int(c2[1:3], 16) - int(c1[1:3], 16)) * ratio)
    g = int(int(c1[3:5], 16) + (int(c2[3:5], 16) - int(c1[3:5], 16)) * ratio)
    b = int(int(c1[5:7], 16) + (int(c2[5:7], 16) - int(c1[5:7], 16)) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


def custom_board_image(size_px: int = 0) -> str | None:
    """查找用户自定义棋盘图片（assets/boards/board_custom.png）。

    返回文件路径；不存在返回 None。
    """
    base = os.path.normpath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "assets", "boards"))
    for name in ("board_custom.png", "board_custom.gif"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None
