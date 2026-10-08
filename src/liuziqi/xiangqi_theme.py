"""
xiangqi_theme.py —— 中国象棋棋盘/棋子主题（5 套联动配色）

设计原则
--------
1. **棋盘与棋子成对切换**：浅色棋盘配深字棋子，深色棋盘必须换浅字棋子，
   否则红黑字在深底上会糊成一片（对比度不足）。故每套主题同时给出
   board（棋盘）与 piece（棋子）两套参数，而不是各自独立可选。
2. **全部程序化矢量绘制**：任意 DPI 清晰、无版权风险、离线可用。
3. 每套主题字段：
   board : bg_a/bg_b(底色渐变) / line(网格线) / river(河界文字) / mark(星位与兵炮标记)
   piece : face_a/face_b(棋子盘面上下) / edge(棋子描边) / glyph_red / glyph_black
           / glyph_red_soft（可选：红字在浅底上的柔和版）
4. shadow : 棋子落影颜色（随棋盘明度调整，避免深底上出现脏边）
"""
from __future__ import annotations

THEME_NAMES = ["素雅木纹", "青花瓷", "墨玉宣纸", "红木金线", "夜弈玄石"]


def _t(bg_a, bg_b, line, river, mark, face_a, face_b, edge,
       g_red, g_black, shadow, name=""):
    """棋子统一为圆形（用户要求保持圆形），故不再有 shape 字段。"""
    return dict(name=name, bg_a=bg_a, bg_b=bg_b, line=line, river=river,
                mark=mark, face_a=face_a, face_b=face_b, edge=edge,
                glyph_red=g_red, glyph_black=g_black, shadow=shadow)


# 五套主题：棋盘配色 × 棋子配色成对定义
THEMES = {
    # 1) 素雅木纹：胡桃木浅底 + 象牙木片棋子（默认，接近实物棋子）
    "素雅木纹": _t("#EBD3A6", "#DCBE8C", "#5C3F22", "#7A5A2E", "#6B4A26",
                  "#FBF3E2", "#F0E1C0", "#A8763C", "#B3271E", "#1C1C1C",
                  (48, 34, 16)),
    # 2) 青花瓷：淡青瓷底 + 白瓷棋子，朱红/靛青字
    "青花瓷": _t("#DCE9E4", "#C2D5CD", "#3F5F57", "#4A6E64", "#3A5A52",
                 "#F6FBF9", "#E2EDE9", "#7FA096", "#B3271E", "#1F3A57",
                 (36, 58, 54)),
    # 3) 墨玉宣纸：深墨底 + 浅玉棋子（浅底浅棋需高对比描边）
    "墨玉宣纸": _t("#3B4149", "#2C3138", "#8A94A0", "#A8B2BE", "#96A0AC",
                   "#F2E9D6", "#DCCFB4", "#9A8A6A", "#FF8A4A", "#F6F1E4",
                   (12, 14, 18)),
    # 4) 红木金线：深红木底 + 米金棋子，金线棋盘
    "红木金线": _t("#8C3B2E", "#6E2A20", "#F0D49A", "#F6E2B4", "#F0D49A",
                  "#FBEFD2", "#EDD9A8", "#C9A24E", "#B3271E", "#241608",
                  (36, 14, 10)),
    # 5) 夜弈玄石：近黑青石底 + 冷灰棋子，适合夜间对弈
    "夜弈玄石": _t("#262C33", "#1B2026", "#7A8794", "#8FA0AE", "#78879A",
                  "#C6D0DC", "#A4B0BE", "#5E6A78", "#C0392B", "#1E252E",
                  (8, 10, 14)),
}

DEFAULT_THEME = THEME_NAMES[0]


def get_theme(name: str) -> dict:
    """按名称取主题参数；未知名称回退默认主题。"""
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def mix_hex(c1: str, c2: str, ratio: float) -> str:
    """两个 #RRGGBB 颜色按比例混合（0=c1, 1=c2）。"""
    r = int(int(c1[1:3], 16) + (int(c2[1:3], 16) - int(c1[1:3], 16)) * ratio)
    g = int(int(c1[3:5], 16) + (int(c2[3:5], 16) - int(c1[3:5], 16)) * ratio)
    b = int(int(c1[5:7], 16) + (int(c2[5:7], 16) - int(c1[5:7], 16)) * ratio)
    return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"


def shadow_rgb(theme: dict) -> tuple:
    """按棋盘明度选择落影色：深底用近黑，浅底用暖褐。"""
    bg = theme["bg_a"]
    lum = (int(bg[1:3], 16) * 299 + int(bg[3:5], 16) * 587 +
           int(bg[5:7], 16) * 114) / 1000
    return theme.get("shadow") or ((12, 14, 18) if lum < 110 else (48, 34, 16))
