"""
fonts.py —— 艺术字体加载与切换

程序启动时把 assets/fonts/*.ttf 全部通过 Windows GDI
AddFontResourceExW(FR_PRIVATE) 私有注册，避免污染系统字体表。
GUI 顶部「字体」菜单列出可选项，点击即切换全局艺术字体
（只影响标题、按钮、菜单等品牌元素；正文仍用 Microsoft YaHei
 保证清晰度，符合用户"不要改变字体清晰度"的要求）。

依赖：仅 Windows。其它平台 fallback 到默认字体。
"""
from __future__ import annotations
import os
import sys

from .paths import resource

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS_DIR = resource("assets", "fonts")

AVAILABLE = {
    "马善政（毛笔楷书）": "MaShanZheng.ttf",
    "指芒星（手写行书）": "ZhiMangXing.ttf",
    "龙藏（古典草书）": "LongCang.ttf",
    "站酷小薇（宋体韵味）": "ZCOOLXiaoWei.ttf",
}
DEFAULT_LABEL = "马善政（毛笔楷书）"
FALLBACK_FAMILY = "Microsoft YaHei UI"

_FNAME_FAMILY = {
    "MaShanZheng.ttf": "Ma Shan Zheng",
    "ZhiMangXing.ttf": "Zhi Mang Xing",
    "LongCang.ttf": "Long Cang",
    "ZCOOLXiaoWei.ttf": "ZCOOL XiaoWei",
}

_FR_PRIVATE = 0x10


class FontManager:
    """字体管理器：注册 + 查询当前艺术字体。"""

    def __init__(self):
        self._registered: list[str] = []
        self._label_to_family: dict[str, str] = {}
        self.current_label = DEFAULT_LABEL
        self.current_family = FALLBACK_FAMILY
        self._available = (sys.platform == "win32")
        self.font_scale = 1.0
        if self._available:
            self._register_all()

    def _register_all(self):
        """扫描 FONTS_DIR 下的所有 TTF 并私有注册。"""
        if not os.path.isdir(FONTS_DIR):
            return
        try:
            import ctypes
            import ctypes.wintypes
            gdi32 = ctypes.windll.gdi32
            gdi32.AddFontResourceExW.restype = ctypes.c_int
            gdi32.AddFontResourceExW.argtypes = [
                ctypes.wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_void_p]

            for label, fname in AVAILABLE.items():
                path = os.path.join(FONTS_DIR, fname)
                if not os.path.exists(path):
                    continue
                try:
                    n = gdi32.AddFontResourceExW(path, _FR_PRIVATE, 0)
                    if n <= 0:
                        continue
                    self._registered.append(path)
                    self._label_to_family[label] = self._fname_to_family(fname)
                except Exception:
                    continue
        except Exception:
            self._available = False
            return

        if self._label_to_family:
            self.current_family = self._label_to_family.get(self.current_label,
                                                            FALLBACK_FAMILY)
        if self.current_family == FALLBACK_FAMILY and self._label_to_family:
            self.current_family = next(iter(self._label_to_family.values()))

    @staticmethod
    def _fname_to_family(fname: str) -> str:
        """根据 TTF 文件名推断注册后的 family 名称（与 Google Fonts 一致）。"""
        return _FNAME_FAMILY.get(fname, FALLBACK_FAMILY)

    def labels(self) -> list[str]:
        """返回已成功注册且家族名解析到的字体菜单项。"""
        if not self._available:
            return []
        return [k for k in AVAILABLE if k in self._label_to_family]

    def set_current(self, label: str) -> str:
        """切换当前艺术字体；返回对应的家族名（GUI 立即可用）。"""
        if label in self._label_to_family:
            self.current_label = label
            self.current_family = self._label_to_family[label]
        return self.current_family

    def make_font(self, size: int, bold: bool = False) -> tuple:
        """构造一个 Tk font：(family, size, weight)。

        优先使用艺术字体；若当前家族不可用，回退到 FALLBACK_FAMILY。
        字号乘以全局 font_scale 系数（用户可调，与 DPI SCALE 分开）。
        """
        family = self.current_family or FALLBACK_FAMILY
        weight = "bold" if bold else "normal"
        return (family, max(7, int(size * self.font_scale)), weight)

    def make_ui_font(self, size: int, bold: bool = False) -> tuple:
        """UI 正文 / 标签字体：始终清晰（保持用户原文要求）。"""
        weight = "bold" if bold else "normal"
        return (FALLBACK_FAMILY, max(7, int(size * self.font_scale)), weight)

    def cleanup(self):
        """程序退出前反向注销（私有注册进程结束后自动释放，留作兜底）。"""
        if not self._available or not self._registered:
            return
        try:
            import ctypes
            import ctypes.wintypes
            gdi32 = ctypes.windll.gdi32
            gdi32.RemoveFontResourceExW.restype = ctypes.c_int
            gdi32.RemoveFontResourceExW.argtypes = [
                ctypes.wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_void_p]
            for path in self._registered:
                try:
                    gdi32.RemoveFontResourceExW(path, _FR_PRIVATE, 0)
                except Exception:
                    continue
        except Exception:
            pass
