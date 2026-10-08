# -*- coding: utf-8 -*-
"""
main.py —— 六子棋程序入口

支持两种运行方式：
    1. 图形界面（默认）：python -m src.main
    2. 文字菜单界面：    python -m src.main --cli

CLI 额外参数：
    --mode human_ai|human_human|ai_ai   直接指定对局模式
    --side black|white                  人机模式下人的执色
    --difficulty easy|medium|hard       AI 难度
    --engine local|qwen                 机机(观战)对战的落子引擎

设计要点：
    - 图形界面无法启动时自动回退到文字菜单（健壮性）；
    - 文字界面提供主菜单、坐标输入（A1~S19）、非法输入重试、战绩查询。
"""
from __future__ import annotations

import argparse

from .board import BLACK, WHITE, COLOR_NAMES
from .game import Game, Player, MODE_HUMAN_AI, MODE_HUMAN_HUMAN, MODE_AI_AI
from .llm_ai import LLMAI


def _menu() -> str:
    print("\n===== 六子棋 Connect6 =====")
    print(" 1. 人机对战")
    print(" 2. 人人对战")
    print(" 3. 机机对战（观战）")
    print(" 4. 战绩查询")
    print(" 0. 退出")
    s = input("请选择：").strip()
    return s


def _ask_difficulty() -> str:
    print("请选择 AI 难度：easy / medium / hard")
    while True:
        d = input("难度：").strip().lower()
        if d in ("easy", "medium", "hard"):
            return d
        print("无效输入，请重新输入。")


def _ask_side() -> int:
    print("请选择执色：black（先手）/ white")
    while True:
        s = input("执色：").strip().lower()
        if s in ("black", "white"):
            return BLACK if s == "black" else WHITE
        print("无效输入，请重新输入。")


def parse_move(text: str, board) -> list:
    """把 "K10" 或 "K10,J11" 解析为落点列表；非法返回空列表。"""
    parts = text.strip().replace(" ", "").split(",")
    if not parts:
        return []
    out = []
    for p in parts:
        if len(p) < 2:
            return []
        col_ch, row_s = p[0].upper(), p[1:]
        if not ("A" <= col_ch <= "S") or not row_s.isdigit():
            return []
        x, y = ord(col_ch) - ord("A"), int(row_s) - 1
        if not board.is_valid(x, y) or not board.is_empty(x, y):
            return []
        out.append((x, y))
    return out


def _make_ai_player(name, side, difficulty):
    if difficulty.startswith("local"):
        return Player(name, kind="ai", difficulty=difficulty.split("_")[1])
    return Player(name, kind="llm", llm=LLMAI(difficulty.split("_")[0]))


def run_cli_game(mode: str, side: str, difficulty: str):
    from .database import Database
    db = None
    try:
        db = Database(); db.connect()
    except Exception:
        db = None

    if mode == MODE_AI_AI:
        black = _make_ai_player("AI黑", BLACK, "local_medium")
        white = _make_ai_player("AI白", WHITE, "local_medium")
    elif mode == MODE_HUMAN_HUMAN:
        black, white = Player("玩家1"), Player("玩家2")
    else:
        human = BLACK if side == "black" else WHITE
        if human == BLACK:
            black, white = Player("玩家"), _make_ai_player("AI", WHITE, difficulty)
        else:
            black, white = _make_ai_player("AI", BLACK, difficulty), Player("玩家")

    game = Game(black=black, white=white)
    while not game.finished:
        print("\n" + game.board.display())
        print(f"轮到 {game.current_player().name}（{COLOR_NAMES[game.current]}），最多下 {game.max_stones} 子")
        cur = game.current_player()
        if cur.kind != "human":
            stones = game.ai_turn(show_info=True)
            if not stones:
                break
            continue
        s = input("输入落点（如 K10 或 K10,J11；q=认输；u=悔棋）：").strip().lower()
        if s == "q":
            game.resign()
            break
        if s == "u":
            # 人机模式：撤到轮到自己（撤整轮 = AI 一步 + 我方一步）；
            # 双人模式：撤一轮
            kinds = {p.kind for p in game.players.values()}
            game.undo_round(to_human=("human" in kinds and "ai" in kinds))
            continue
        pts = parse_move(s, game.board)
        if len(pts) < 1 or len(pts) > game.max_stones:
            print("非法输入，请重新输入。")
            continue
        for x, y in pts:
            ok, msg, line = game.place(x, y)
            if not ok:
                print(msg)
                break
            if line is not None:
                break
        game.end_round()

    print("\n" + game.result_text())
    if db:
        try:
            db.save_game(game.to_record(), [[x, y, c] for x, y, c, _ in game.moves_log])
            db.close()
        except Exception:
            pass


def show_stats_cli(db):
    try:
        stats = db.get_stats()
        print("\n=== 战绩 ===")
        print(f"{'棋手':<8}{'胜':>4}{'负':>4}{'平':>4}")
        for s in stats:
            print(f"{s.get('name', '?'):<8}"
                  f"{s.get('wins', 0):>4}{s.get('losses', 0):>4}{s.get('draws', 0):>4}")
    except Exception as exc:
        print(f"战绩查询失败：{exc}")
        print("  提示：请检查 config/database.ini 配置与 PostgreSQL 服务。")


def run_cli_menu(default_engine: str = "local"):
    from .database import Database
    db = None
    try:
        db = Database(); db.connect()
        print("数据库连接成功。")
    except Exception:
        print("（未连接数据库，战绩功能不可用）")

    while True:
        ch = _menu()
        if ch == "1":
            side = _ask_side()
            diff = _ask_difficulty()
            run_cli_game(MODE_HUMAN_AI, "black" if side == BLACK else "white", diff)
        elif ch == "2":
            run_cli_game(MODE_HUMAN_HUMAN, "black", "medium")
        elif ch == "3":
            run_cli_game(MODE_AI_AI, "black", "medium")
        elif ch == "4":
            if db:
                show_stats_cli(db)
            else:
                print("未连接数据库。")
        elif ch == "0":
            break
        else:
            print("无效选择。")
    if db:
        try:
            db.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="六子棋 Connect6 计算机博弈程序")
    parser.add_argument("--cli", action="store_true", help="使用文字菜单界面（默认启动图形界面）")
    parser.add_argument("--mode", choices=[MODE_HUMAN_AI, MODE_HUMAN_HUMAN, MODE_AI_AI],
                        default=MODE_HUMAN_AI, help="对局模式（--cli 时生效）")
    parser.add_argument("--side", choices=["black", "white"], default="black",
                        help="人机模式下人的执色（--cli 时生效）")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="medium",
                        help="AI 难度")
    parser.add_argument("--engine", choices=["local", "qwen"], default="local",
                        help="机机(观战)对战的落子引擎：本地AI / 千问")
    args = parser.parse_args()

    if args.cli:
        run_cli_menu(default_engine=args.engine)
        return

    # 默认图形界面；失败自动回退文字菜单
    try:
        from .gui import run
        run()
    except Exception as exc:
        print(f"[提示] 图形界面启动失败：{exc}")
        print("[提示] 自动切换到文字菜单模式。")
        run_cli_menu()


if __name__ == "__main__":
    main()
