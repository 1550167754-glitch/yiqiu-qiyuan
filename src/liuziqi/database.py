# -*- coding: utf-8 -*-
"""
database.py —— PostgreSQL 数据库存取模块

功能：
    1. 读取 config/database.ini 中的连接配置并建立连接；
    2. 自动建表：players（棋手与战绩）、games（对局总表）、moves（逐手明细）；
    3. 对局存档：保存对局信息 + 全部落子（事务保证一致性）；
    4. 战绩查询：棋手胜/负/平统计、最近对局列表、对局棋谱回放。

健壮性设计（课程要求"程序对非法输入适当反应"）：
    - 未安装 psycopg / 数据库不可达 / 配置缺失时，connect() 返回 False，
      程序其余功能（界面、对战、AI）照常运行，仅"存档与战绩查询"
      功能不可用，并在界面状态栏给出明确提示。
    - 所有对外方法在未连接时安全返回默认值，不抛出异常。
"""
from __future__ import annotations

import configparser
import json
import os

from .paths import resource

DEFAULT_CONFIG = resource("config", "database.ini", writable=True)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    id      SERIAL PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL,          -- 棋手名（人机用"玩家"，AI 用 "AI-难度"）
    kind    TEXT NOT NULL DEFAULT 'human', -- 'human' / 'ai'
    wins    INT NOT NULL DEFAULT 0,
    losses  INT NOT NULL DEFAULT 0,
    draws   INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    id          SERIAL PRIMARY KEY,
    black_name  TEXT NOT NULL,             -- 黑方名称
    black_kind  TEXT NOT NULL DEFAULT 'human',
    white_name  TEXT NOT NULL,
    white_kind  TEXT NOT NULL DEFAULT 'human',
    result      TEXT NOT NULL,             -- BLACK / WHITE / DRAW / ABORT
    reason      TEXT,
    move_count  INT NOT NULL DEFAULT 0,
    record      JSONB,                     -- 完整棋谱（JSON）
    started_at  TIMESTAMPTZ DEFAULT now(),
    ended_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS moves (
    id      SERIAL PRIMARY KEY,
    game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seq     INT NOT NULL,                  -- 手序号（从 1 开始）
    color   INT NOT NULL,                  -- 1=黑 2=白
    x       INT NOT NULL,
    y       INT NOT NULL
);
"""


class Database:
    """PostgreSQL 存档管理器。

    用法：
        db = Database()
        if db.connect():          # 连接成功（含自动建表）
            db.save_game(record, moves)
            stats = db.get_stats()
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG):
        self.available = False
        self.config_path = config_path
        self.conn = None
        self.last_error = ""

    def connect(self) -> bool:
        try:
            import psycopg
        except ImportError:
            self.available = False
            self.last_error = "未安装 psycopg"
            return False
        try:
            params = self._read_config()
            self.conn = psycopg.connect(**params)
            self.available = True
            self._init_schema()
            return True
        except Exception as exc:
            self.available = False
            self.last_error = str(exc)
            return False

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = None
        self.available = False

    def _read_config(self) -> dict:
        cp = configparser.ConfigParser()
        cp.read(self.config_path, encoding="utf-8")
        d = cp["postgres"] if "postgres" in cp else cp["DEFAULT"]
        params = {
            "host": d.get("host", "localhost"),
            "port": int(d.get("port", 5432)),
            "dbname": d.get("dbname", d.get("database", "connect6")),
            "user": d.get("user", "postgres"),
            "password": d.get("password", ""),
            "connect_timeout": int(d.get("connect_timeout", 8)),
        }
        return params

    def _init_schema(self):
        with self.conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        self.conn.commit()

    def save_game(self, record: dict, moves: list[tuple[int, int, int]]) -> int | None:
        """保存一局棋（战绩 + 对局 + 逐手），返回对局 id；失败返回 None。

        参数：
            record : Game.to_record() 产出的棋谱字典
            moves  : [(x, y, color), ...] 落子序列
        """
        if not self.available:
            return None
        try:
            with self.conn.cursor() as cur:
                black = record["black"]
                white = record["white"]
                self._upsert_player(cur, black, record.get("black_kind", "human"))
                self._upsert_player(cur, white, record.get("white_kind", "human"))
                self._update_record(cur, black, white, record["result"])
                cur.execute(
                    "INSERT INTO games\n"
                    "  (black_name, black_kind, white_name, white_kind,\n"
                    "   result, reason, move_count, record)\n"
                    "  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)\n"
                    "  RETURNING id",
                    (black, record.get("black_kind", "human"),
                     white, record.get("white_kind", "human"),
                     record["result"],
                     record.get("reason", ""),
                     len(moves),
                     json.dumps(record, ensure_ascii=False)))
                game_id = cur.fetchone()[0]
                rows = [(game_id, i + 1, c, x, y)
                        for i, (x, y, c) in enumerate(moves)]
                cur.executemany(
                    "INSERT INTO moves (game_id, seq, color, x, y) "
                    "VALUES (%s,%s,%s,%s,%s)", rows)
            self.conn.commit()
            return game_id
        except Exception:
            try:
                self.conn.rollback()
            except Exception:
                pass
            return None

    def _upsert_player(self, cur, name: str, kind: str):
        """棋手不存在则创建（ON CONFLICT 保证幂等）。"""
        cur.execute(
            "INSERT INTO players (name, kind) VALUES (%s, %s)\n"
            "  ON CONFLICT (name) DO UPDATE SET kind = EXCLUDED.kind",
            (name, kind))

    def _update_record(self, cur, black: str, white: str, result: str):
        """按对局结果更新双方胜/负/平计数。"""
        if result == "BLACK":
            self._inc(cur, black, "wins")
            self._inc(cur, white, "losses")
        elif result == "WHITE":
            self._inc(cur, white, "wins")
            self._inc(cur, black, "losses")
        elif result == "DRAW":
            self._inc(cur, black, "draws")
            self._inc(cur, white, "draws")

    @staticmethod
    def _inc(cur, name: str, column: str):
        cur.execute(f"UPDATE players SET {column} = {column} + 1 WHERE name = %s",
                    (name,))

    def get_stats(self) -> list[dict]:
        """所有棋手战绩列表：name/kind/wins/losses/draws（按胜场降序）。"""
        if not self.available:
            return []
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT name, kind, wins, losses, draws\n"
                    "  FROM players ORDER BY wins DESC, name")
                cols = ("name", "kind", "wins", "losses", "draws")
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            return []

    def list_recent_games(self, limit: int = 10) -> list[dict]:
        """最近对局列表（每局元信息，不含逐手）。"""
        if not self.available:
            return []
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT id, black_name, white_name, result, reason,\n"
                    "       move_count, started_at\n"
                    "  FROM games ORDER BY id DESC LIMIT %s", (limit,))
                cols = ("id", "black_name", "white_name", "result",
                        "reason", "move_count", "started_at")
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            return []

    def get_game_record(self, game_id: int) -> dict | None:
        """按 id 取某局完整棋谱（含 record JSON 与逐手）；无则返回 None。"""
        if not self.available:
            return None
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT id, black_name, black_kind, white_name, white_kind,\n"
                    "       result, reason, record, started_at\n"
                    "  FROM games WHERE id = %s", (game_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                rec = dict(zip(("id", "black", "black_kind", "white", "white_kind",
                                "result", "reason", "record", "started_at"), row))
                cur.execute(
                    "SELECT seq, color, x, y FROM moves\n"
                    "  WHERE game_id = %s ORDER BY seq", (game_id,))
                rec["moves"] = [(c, x, y) for seq, c, x, y in cur.fetchall()]
                return rec
        except Exception:
            return None
