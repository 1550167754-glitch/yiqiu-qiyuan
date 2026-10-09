# -*- coding: utf-8 -*-
r"""测试数据库连接.py —— 一条命令验完"数据库到底通不通"。

用法（项目根目录）：
    <venv>\Scripts\python.exe scripts\测试数据库连接.py

输出：配置文件路径 → 解析出的连接参数 → 真实连接结果 → 表记录数。
失败时打印原因与可执行建议（与程序内提示同源，见 database.Database.last_hint）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "src"))

from liuziqi.database import Database        # noqa: E402


def main() -> int:
    db = Database()
    print("配置文件 :", db.config_path)
    try:
        params = db._read_config()
    except Exception as exc:
        print("解析失败 :", type(exc).__name__, exc)
        print("建议     : 确认文件为 UTF-8（不带 BOM）且含 [postgres] 段")
        return 2
    safe = dict(params)
    safe["password"] = "*" * len(str(safe.get("password", ""))) or "(空)"
    print("连接参数 :", safe)

    if not db.connect():
        print("连接结果 : 失败")
        print("原因     :", db.last_error)
        print("建议     :", db.last_hint)
        return 3

    print("连接结果 : 成功（表结构已就绪）")
    with db.conn.cursor() as cur:
        for tbl in ("players", "games", "moves"):
            cur.execute(f"SELECT count(*) FROM {tbl}")
            print(f"  {tbl:<8} {cur.fetchone()[0]:>6} 行")
        cur.execute("SELECT id, black_name, white_name, result, move_count, ended_at\n"
                    "  FROM games ORDER BY id DESC LIMIT 5")
        rows = cur.fetchall()
    if rows:
        print("最近对局 :")
        for gid, b, w, res, mc, ended in rows:
            print(f"  #{gid} {b} vs {w} → {res}（{mc} 手）{ended}")
    else:
        print("最近对局 : 暂无（还没有存过对局）")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
