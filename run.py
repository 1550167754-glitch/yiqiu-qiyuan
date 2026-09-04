# -*- coding: utf-8 -*-
"""
run.py —— 六子棋（Connect6）统一入口

用途：
    1. PyInstaller 打包入口（见 build_exe.bat）；
    2. 开发调试入口：python run.py
启动图形界面；若图形界面异常则自动降级到文字菜单，保证程序始终可用。
"""
import sys
import os

# 打包后 src 包已内嵌；源码运行从这里可正确解析 src 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        from src.liuziqi.gui import run
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"[提示] 图形界面启动失败：{exc}")
        print("[提示] 切换到文字菜单模式。")
        try:
            from src.liuziqi.main import run_cli_menu
            run_cli_menu()
        except Exception as e2:  # noqa: BLE001
            print(f"[错误] 文字模式也失败：{e2}")
            input("按回车退出…")
            sys.exit(1)


if __name__ == "__main__":
    main()
