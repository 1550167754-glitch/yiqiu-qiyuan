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

# ---------------------------------------------------------------- 配置段名兼容
# 历史原因：早期模板写的是 [postgresql]，而读取代码只看 [postgres]（或 [DEFAULT]），
# 两边不一致会让 connect() 直接抛 KeyError 并降级为"数据库不可用"。这里把两种
# 写法都认下来，用户按哪份文档写都能连上。
SECTION_ALIASES = ("postgres", "postgresql", "pgsql", "postgres_db")

# ---------------------------------------------------------------- 配置项别名
# 同一个含义的多种写法（dbname/database、user/username、pass/pwd…）统一归一。
KEY_ALIASES = {
    "dbname": ("dbname", "database", "db"),
    "user": ("user", "username", "usr"),
    "password": ("password", "passwd", "pwd", "pass"),
    "host": ("host", "hostaddr", "server"),
    "port": ("port",),
    "connect_timeout": ("connect_timeout", "timeout"),
    "sslmode": ("sslmode", "ssl_mode"),
}

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
        # 面向用户的可执行建议（由 _classify_error 生成，单独字段避免污染 last_error）
        self.last_hint = ""
        self.params: dict = {}

    def connect(self) -> bool:
        try:
            import psycopg
        except ImportError:
            self.available = False
            self.last_error = "未安装 psycopg"
            self.last_hint = ("当前 Python 环境缺少 PostgreSQL 驱动。"
                              "请运行：pip install \"psycopg[binary]\"")
            return False
        try:
            params = self._read_config()
            self.params = params
        except Exception as exc:
            self.available = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.last_hint = ("读取 config/database.ini 失败："
                              "请确认文件存在、为 UTF-8 编码，且含 "
                              "[postgres] 段（host/port/dbname/user/password）。")
            return False
        try:
            self.conn = psycopg.connect(**params)
            self.available = True
            self._init_schema()
            self.last_error = ""
            self.last_hint = ""
            return True
        except Exception as exc:
            self.available = False
            try:
                if self.conn:
                    self.conn.close()
            except Exception:
                pass
            self.conn = None
            self.last_error = " ".join(str(exc).split())
            self.last_hint = self._classify_error(self.last_error)
            return False

    def _classify_error(self, err: str) -> str:
        """把驱动报错翻译成用户能照着做的下一步。"""
        low = err.lower()
        target = (f"{self.params.get('user', '?')}@"
                  f"{self.params.get('host', '?')}:{self.params.get('port', '?')}"
                  f"/{self.params.get('dbname', '?')}")
        if "password" in low or "认证失败" in err or "authentication" in low:
            return (f"账号或密码不正确（{target}）。"
                    "请核对 config/database.ini 的 user / password；"
                    "改名或忘记密码可运行项目根目录的 "
                    "一键修复PostgreSQL.cmd（需管理员）。")
        if "does not exist" in low and "database" in low:
            return (f"数据库 {self.params.get('dbname')} 不存在。"
                    "请执行：CREATE DATABASE connect6;（或运行 "
                    "一键修复PostgreSQL.cmd 自动创建）")
        if "role" in low and "does not exist" in low:
            return (f"角色 {self.params.get('user')} 不存在。"
                    "请核对 ini 中的 user，或运行 一键修复PostgreSQL.cmd。")
        if "could not connect" in low or "connection refused" in low:
            return ("连不上 PostgreSQL 服务（端口未监听）。"
                    "请确认服务 postgresql-x64-18 已启动。")
        if "timeout" in low or "timed out" in low:
            return "连接超时：请检查 host/port 是否正确、服务是否在运行。"
        return "请检查 PostgreSQL 服务状态与 config/database.ini 连接参数。"

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = None
        self.available = False

    def _read_config(self) -> dict:
        """读取 ini 连接配置。

        【历史坑·必读】必须用 utf-8-sig 解码。
        本机 config/database.ini 由 Windows 记事本 / PowerShell Set-Content 生成时
        会在开头写入 UTF-8 BOM（EF BB BF）。configparser 用 'utf-8' 读取时首行变成
        '\\ufeff; 注释'，于是抛 MissingSectionHeaderError（报错原文
        "File contains no section headers"，极易被误读成"文件格式错"），
        connect() 里被 except 吞掉 → 整个数据库功能静默失效。
        utf-8-sig 会无条件剔除 BOM，对无 BOM 文件完全等价。
        """
        cp = configparser.ConfigParser()
        try:
            read_ok = cp.read(self.config_path, encoding="utf-8-sig")
        except configparser.MissingSectionHeaderError:
            # 容错：用户可能只写了键值对而漏掉 [postgres] 段头。
            # 这种"裸键值对"文件 configparser 一律拒收，这里补一个段头再解析，
            # 避免因为少写两行方括号就整体失联。
            with open(self.config_path, "r", encoding="utf-8-sig") as f:
                body = f.read()
            cp = configparser.ConfigParser()
            cp.read_string("[postgres]\n" + body)
            read_ok = [self.config_path]
        if not read_ok:
            raise FileNotFoundError(f"数据库配置文件不存在：{self.config_path}")
        # 段名：优先 [postgres]，再依次尝试历史别名，最后退回 [DEFAULT]/顶层键
        section = None
        for name in SECTION_ALIASES:
            if name in cp:
                section = cp[name]
                break
        if section is None and cp.sections():
            # 只配了一个段时，不管它叫什么名字都认——避免又因段名差异失联
            section = cp[cp.sections()[0]]
        if section is None:
            section = cp["DEFAULT"]

        def pick(key: str, default):
            for alias in KEY_ALIASES.get(key, (key,)):
                v = section.get(alias, None)
                if v is None:
                    v = cp["DEFAULT"].get(alias, None)
                if v is not None and str(v).strip() != "":
                    return str(v).strip()
            return default

        def as_int(key: str, default: int) -> int:
            try:
                return int(float(pick(key, default)))
            except (TypeError, ValueError):
                return default

        params = {
            "host": pick("host", "localhost"),
            "port": as_int("port", 5432),
            "dbname": pick("dbname", "connect6"),
            "user": pick("user", "postgres"),
            "password": pick("password", ""),
            "connect_timeout": max(1, as_int("connect_timeout", 8)),
        }
        # 客户端编码：程序与库表注释都是 UTF-8，显式指定可避免中文棋手名
        # 在 GBK 控制台下按本机编码写入后变乱码（psycopg 默认跟随客户端编码）。
        enc = pick("client_encoding", "")
        if enc:
            params["client_encoding"] = enc
        sslmode = pick("sslmode", "")
        if sslmode:
            params["sslmode"] = sslmode
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

        【注意】返回 None 表示**没有写进数据库**。调用方必须检查返回值，
        不能"调用完就当存上了"——历史上 GUI 正是这么干的，界面上弹
        「对局已存档」，数据库里其实一条记录都没有（参见 _db_save_worker）。
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
        except Exception as exc:
            try:
                self.conn.rollback()
            except Exception:
                pass
            # 记下失败原因（打印参数化，不含密码），不要只返回 None 让上层瞎猜
            self.last_error = " ".join(str(exc).split())
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
        # 计数必须真的落到某一行上：rowcount=0 说明 players 里没有该棋手，
        # 属于静默丢数据，宁可抛异常让上层回滚，也不要"看起来存上了"。
        if cur.rowcount != 1:
            raise RuntimeError(f"战绩更新失败：players 中找不到棋手 {name!r}")

    def probe(self) -> tuple[bool, str, str]:
        """只做"能不能真连上"的探测，不建表、不改数据。

        返回 (成功?, 错误摘要, 可执行建议)。
        用途：启动时判断"数据库是否真的可用"——只探端口是不够的，
        端口通但账号密码错时，程序仍会显示"数据库已就绪"，属于假就绪。
        """
        try:
            import psycopg
        except ImportError:
            return False, "未安装 psycopg", "pip install \"psycopg[binary]\""
        try:
            params = self._read_config()
        except Exception as exc:
            return (False, f"{type(exc).__name__}: {exc}",
                    "检查 config/database.ini 是否为 UTF-8 且含 [postgres] 段")
        self.params = params
        try:
            conn = psycopg.connect(**params)
            conn.close()
            self.last_error = ""
            self.last_hint = ""
            return True, "", ""
        except Exception as exc:
            self.last_error = " ".join(str(exc).split())
            self.last_hint = self._classify_error(self.last_error)
            return False, self.last_error, self.last_hint

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
