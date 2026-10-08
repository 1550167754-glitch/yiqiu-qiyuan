# -*- coding: utf-8 -*-
"""
pikafish_engine.py —— 皮卡鱼（Pikafish）UCI 引擎子进程封装

皮卡鱼是 Stockfish 象棋分支，内置 NNUE 神经网络评估，棋力远超自研 AlphaBeta。
本模块以 UCI 协议经 stdin/stdout 与引擎子进程通信，供象棋 GUI 做人机对战：
    - find_engine()：按候选路径自动探测 exe 与 NNUE 权重（可被 config/pikafish.ini 覆盖）；
    - set_difficulty()：简单/中等/困难 → Skill Level（0-20）+ 搜索深度；
    - best_move()：position(fen 或 startpos+moves) → go → 解析 bestmove 与评分；
    - 线程约定：best_move 为阻塞调用，**必须在工作线程中执行**，GUI 侧用队列轮询。
引擎启动失败/不可用时调用方须明确提示并回退人人对战，禁止静默降级。
"""

from __future__ import annotations

import os
import subprocess
import threading

# 难度 → (Skill Level, 搜索深度)。Skill 0-20；深度控制思考强度与耗时。
DIFFICULTY_PRESETS = {
    "easy": (3, 6),
    "medium": (12, 10),
    "hard": (20, 14),
}

# 候选安装位置（按序探测）；config/pikafish.ini 的 [pikafish] exe/nnue 可覆盖。
def _candidate_homes():
    homes = []
    try:
        from .paths import project_root
        root = project_root()
        homes.append(os.path.join(root, "assets", "pikafish"))
        # 归类后的标准位置：engine/Pikafafish皮卡鱼*/
        eng_dir = os.path.join(root, "engine")
        if os.path.isdir(eng_dir):
            for name in sorted(os.listdir(eng_dir)):
                homes.append(os.path.join(eng_dir, name))
        # 兼容：引擎目录直接放在项目根
        homes.append(root)
    except Exception:
        pass
    # 兼容：桌面独立放置
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    for name in sorted(os.listdir(desktop)) if os.path.isdir(desktop) else []:
        if name.lower().startswith("pikafish"):
            homes.append(os.path.join(desktop, name))
    return homes


def _config_override():
    """config/pikafish.ini: [pikafish] exe=... nnue=...（均可选）。"""
    try:
        import configparser
        from .paths import project_root
        p = os.path.join(project_root(), "config", "pikafish.ini")
        if not os.path.exists(p):
            return None, None
        cp = configparser.ConfigParser()
        cp.read(p, encoding="utf-8")
        exe = cp.get("pikafish", "exe", fallback=None)
        nnue = cp.get("pikafish", "nnue", fallback=None)
        return (exe or None), (nnue or None)
    except Exception:
        return None, None


def find_engine():
    """探测 (exe_path, nnue_path)；任一缺失返回 (None, None)。"""
    exe_cfg, nnue_cfg = _config_override()
    for home in _candidate_homes():
        exe = exe_cfg or _find_one(home, ("Pikafish-Windows-x86-64-universal.exe",
                                          "pikafish.exe", "Pikafish.exe"))
        nnue = nnue_cfg or _find_one(home, ("pikafish.nnue",))
        if exe and nnue and os.path.exists(exe) and os.path.exists(nnue):
            return exe, nnue
        if exe_cfg and nnue_cfg and os.path.exists(exe_cfg) and os.path.exists(nnue_cfg):
            return exe_cfg, nnue_cfg
    return None, None


def _find_one(folder, names):
    if not os.path.isdir(folder):
        return None
    for n in names:
        p = os.path.join(folder, n)
        if os.path.exists(p):
            return p
    return None


def available() -> bool:
    exe, nnue = find_engine()
    return exe is not None and nnue is not None


class PikafishEngine:
    """UCI 子进程封装。方法（除 best_move/close）须在创建线程中调用；
    best_move 为阻塞式，供工作线程调用；close 可从任意线程调用。"""

    def __init__(self, exe: str, nnue: str, hash_mb: int = 64, threads: int = 1):
        self._exe = exe
        self._nnue = nnue
        self._proc = None
        self._lock = threading.Lock()
        self._skill = 20
        self._hash_mb = hash_mb
        self._threads = threads
        self._start()

    # ------------------------------------------------------------ 生命周期
    def _start(self):
        self._proc = subprocess.Popen(
            [self._exe],
            cwd=os.path.dirname(self._nnue),   # 引擎默认在 cwd 找 pikafish.nnue
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._send("uci")
        self._wait_for("uciok")
        self._send(f"setoption name EvalFile value {self._nnue}")
        self._send(f"setoption name Threads value {self._threads}")
        self._send(f"setoption name Hash value {self._hash_mb}")
        self._send(f"setoption name Skill Level value {self._skill}")
        self._send("isready")
        self._wait_for("readyok")

    def _send(self, cmd: str):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(cmd + "\n")
                self._proc.stdin.flush()
            except Exception:
                pass

    def _readline(self):
        if not self._proc or self._proc.stdout is None:
            return ""
        try:
            return self._proc.stdout.readline()
        except Exception:
            return ""

    def _wait_for(self, token: str, max_lines: int = 400):
        for _ in range(max_lines):
            line = self._readline()
            if not line:
                continue
            if token in line:
                return True
        return False

    # ------------------------------------------------------------ 配置
    def set_difficulty(self, name: str):
        """easy/medium/hard → Skill Level。"""
        skill, _depth = DIFFICULTY_PRESETS.get(name, (12, 10))
        self._skill = skill
        self._send(f"setoption name Skill Level value {skill}")

    def new_game(self):
        self._send("ucinewgame")
        self._send("isready")
        self._wait_for("readyok")

    # ------------------------------------------------------------ 搜索
    def best_move(self, moves_uci: list, *, depth: int = 10,
                  movetime_ms: int | None = None, fen: str | None = None):
        """阻塞搜索（工作线程调用）。

        moves_uci: 本局着法序列（UCCI 坐标字符串列表）；fen 可选自定义局面
        （此时 moves 附加于 fen 之后）。
        返回 (uci_str, score_cp)；无着法/异常返回 (None, None)。
        """
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                return None, None
            if fen:
                pos = f"position fen {fen}"
                if moves_uci:
                    pos += " moves " + " ".join(moves_uci)
            else:
                pos = ("position startpos"
                       + (" moves " + " ".join(moves_uci) if moves_uci else ""))
            self._send(pos)
            if movetime_ms:
                self._send(f"go movetime {int(movetime_ms)}")
            else:
                self._send(f"go depth {int(depth)}")

            best, score = None, None
            while True:
                line = self._readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("info") and " score " in line:
                    score = self._parse_score(line)
                elif line.startswith("bestmove"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] not in ("(none)", "0000"):
                        best = parts[1]
                    break
            return best, score

    @staticmethod
    def _parse_score(info_line: str):
        """从 info 行提取 cp/mate 分值（返回 Centipawn 数；mate 记为大分）。"""
        try:
            parts = info_line.split()
            i = parts.index("score")
            kind, val = parts[i + 1], int(parts[i + 2])
            if kind == "cp":
                return val
            if kind == "mate":
                return (100000 - abs(val) * 100) * (1 if val > 0 else -1)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------ 关闭
    def close(self):
        try:
            self._send("quit")
        except Exception:
            pass
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
