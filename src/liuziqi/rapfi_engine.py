# -*- coding: utf-8 -*-
r"""
rapfi_engine.py —— Rapfi 五子棋引擎（piskvork 协议子进程封装）

Rapfi 是 GomoCup 2024 冠军五子棋引擎（Botzone 520 引擎榜首，CPU 版较
Katagomo 高约 400 Elo），采用 αβ 搜索 + NNUE 神经网络评估，权重为从 CNN
蒸馏出的"模式码本 + 增量更新"轻量网络（论文：arXiv:2503.13178）。
其算法谱系可追溯至 Allis 等人的威胁空间搜索（Go-Moku Solved by New
Search Techniques, AAAI Fall Symposium 1993）与 Wagner & Virágh 的
freeness 评估（2001），是当前公开可得的五子棋引擎棋力标杆之一。

本模块以 piskvork 标准协议经 stdin/stdout 与引擎子进程通信，供五子棋
"困难"档做人机对战（与象棋侧 PikafishEngine 走 UCI 完全同构）：
    - find_engine()：按 CPU 指令集能力自动探测 exe（avx512vnni→…→sse，
      逐个功能性验证，首个可用者胜出），可被 config/rapfi.ini 覆盖；
    - get_shared_engine()：进程级单例（NNUE 权重只加载一次，跨局复用）；
    - best_move()：把整盘 history 以 BOARD/DONE 全量发送（无状态协议，
      天然免疫悔棋/重开导致的状态漂移），解析 "x,y" 应答；
    - 线程约定：best_move 为阻塞调用，必须在工作线程中执行（GUI 的
      _ai_worker 线程），主线程只经队列轮询结果；
    - 引擎不可用/超时/进程死亡/应答非法一律返回 None，由调用方回退到
      内置 AlphaBeta+VCF/VCT 引擎，禁止静默降级为烂着。

协议要点（实测自 pbrain-rapfi 250615）：
    - 坐标 0 基，"x,y"（如 7,7 即天元）；颜色 1=黑 2=白（与 board.py 一致）；
    - BOARD 逐行 "x,y,color" + DONE 后，引擎按子数奇偶推断行棋方并应答；
    - INFO timeout_turn <ms> 控制每步思考时限（精确生效）；
    - 应答混杂 MESSAGE/ERROR/OK 行，需按 "^\d+,\d+$" 过滤；
    - INFO exact5 / renju 不被识别（freestyle 只需 INFO rule 0）。
"""

from __future__ import annotations

import atexit
import os
import queue
import re
import subprocess
import threading
import time

# 引擎可执行文件名候选：按指令集能力从高到低排列，探测时逐一功能性验证。
# （Rapfi 官方发布包同时提供 SSE/AVX2/AVXVNNI/AVX512/AVX512VNNI 五套 Windows 二进制）
_EXE_CANDIDATES = (
    "pbrain-rapfi-windows-avx512vnni.exe",
    "pbrain-rapfi-windows-avx512.exe",
    "pbrain-rapfi-windows-avxvnni.exe",
    "pbrain-rapfi-windows-avx2.exe",
    "pbrain-rapfi-windows-sse.exe",
)

DEFAULT_TIME_MS = 3000          # 困难档每步思考时限（该时限下棋力已远超内置引擎）
_PROBE_BUDGET_S = 8.0           # 单个候选 exe 的功能性探测预算
_MOVE_SLACK_S = 1.5             # best_move 等待应答的宽松余量（引擎自身限时 + 进程调度）

_MOVE_RE = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\s*$")

_exe_cache: str | None = None
_exe_tried = False
_shared: "RapfiEngine | None" = None
_shared_lock = threading.Lock()


# ------------------------------------------------------------ 探测与配置
def _candidate_homes() -> list[str]:
    """引擎可能所在目录（按序探测）。"""
    homes: list[str] = []
    try:
        from .paths import project_root
        root = project_root()
        homes.append(os.path.join(root, "engine", "rapfi"))
        eng_dir = os.path.join(root, "engine")
        if os.path.isdir(eng_dir):
            for name in sorted(os.listdir(eng_dir)):
                homes.append(os.path.join(eng_dir, name))
        homes.append(root)
    except Exception:
        pass
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(desktop):
        for name in sorted(os.listdir(desktop)):
            low = name.lower()
            if "rapfi" in low:
                homes.append(os.path.join(desktop, name))
    return homes


def _config() -> dict:
    """config/rapfi.ini: [rapfi] enabled / exe / time_ms（均可选）。"""
    cfg = {"enabled": True, "exe": None, "time_ms": DEFAULT_TIME_MS}
    try:
        import configparser
        from .paths import project_root
        p = os.path.join(project_root(), "config", "rapfi.ini")
        if not os.path.exists(p):
            return cfg
        cp = configparser.ConfigParser()
        cp.read(p, encoding="utf-8")
        if cp.has_option("rapfi", "enabled"):
            cfg["enabled"] = cp.getboolean("rapfi", "enabled", fallback=True)
        if cp.has_option("rapfi", "exe"):
            exe = (cp.get("rapfi", "exe", fallback="") or "").strip()
            cfg["exe"] = exe or None
        if cp.has_option("rapfi", "time_ms"):
            try:
                cfg["time_ms"] = max(200, int(float(cp.get("rapfi", "time_ms"))))
            except Exception:
                pass
    except Exception:
        pass
    return cfg


def _probe(exe: str) -> bool:
    """功能性探测：起进程、发一个最小局面，能在预算内应答合法着法即为可用。

    这是必要的——AVX512 二进制在旧 CPU 上会直接非法指令崩溃，只看文件
    存在与否不够；且探测本身会加载 NNUE 权重，顺带验证权重文件齐全。
    """
    if not (os.path.isfile(exe) and exe.lower().endswith(".exe")):
        return False
    proc = None
    try:
        proc = subprocess.Popen(
            [exe],
            cwd=os.path.dirname(exe) or ".",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        proc.stdin.write("INFO timeout_turn 300\nSTART 15\nBOARD\n7,7,1\nDONE\n")
        proc.stdin.flush()
        t0 = time.monotonic()
        while time.monotonic() - t0 < _PROBE_BUDGET_S:
            line = proc.stdout.readline()
            if not line:
                break
            if _MOVE_RE.match(line):
                return True
        return False
    except Exception:
        return False
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass


def find_engine() -> str | None:
    """返回可用的引擎 exe 路径；探测结果缓存（整进程一次）。"""
    global _exe_cache, _exe_tried
    cfg = _config()
    if not cfg["enabled"]:
        return None
    if _exe_tried:
        return _exe_cache
    _exe_tried = True
    if cfg["exe"] and os.path.isfile(cfg["exe"]) and _probe(cfg["exe"]):
        _exe_cache = cfg["exe"]
        return _exe_cache
    homes = _candidate_homes()
    for name in _EXE_CANDIDATES:          # 先看指令集优先级，再看目录
        for home in homes:
            if not os.path.isdir(home):
                continue
            exe = os.path.join(home, name)
            if os.path.isfile(exe) and _probe(exe):
                _exe_cache = exe
                return _exe_cache
    return None


def available() -> bool:
    """Rapfi 是否可用（配置启用 + 引擎可运行）。"""
    try:
        return find_engine() is not None
    except Exception:
        return False


def configured_time_ms() -> int:
    return int(_config().get("time_ms", DEFAULT_TIME_MS))


# ------------------------------------------------------------ 引擎封装
class RapfiEngine:
    """piskvork 子进程封装。

    方法约定与 PikafishEngine 一致：构造/close 尽量在同一线程；
    best_move 为阻塞式，供工作线程调用；stop 可从任意线程调用
    （杀进程让搜索立即结束，下一次 best_move 会自动重启进程）。
    """

    def __init__(self, exe: str | None = None, time_limit_ms: int | None = None):
        self._exe = exe or find_engine()
        if not self._exe:
            raise FileNotFoundError("Rapfi 引擎不存在（engine/rapfi/ 未找到可用 exe）")
        self._time_ms = int(time_limit_ms or configured_time_ms())
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue = queue.Queue()
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._start()

    # ------------------------------------------------------------ 生命周期
    def _start(self) -> None:
        self._proc = subprocess.Popen(
            [self._exe],
            cwd=os.path.dirname(self._exe) or ".",   # 引擎在 cwd 找 config.toml 与 NNUE 权重
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # freestyle 五子棋握手（实测：exact5/renju 不被识别，勿发）
        self._send("INFO timeout_match 300000")
        self._send(f"INFO timeout_turn {self._time_ms}")
        self._send("INFO time_left 290000")
        self._send("INFO game_type 1")
        self._send("INFO rule 0")
        self._send("START 15")

    def _read_loop(self) -> None:
        proc = self._proc
        try:
            assert proc is not None and proc.stdout is not None
            for line in proc.stdout:
                self._lines.put(line)
        except Exception:
            pass
        finally:
            self._lines.put(None)          # EOF 哨兵

    def _send(self, cmd: str) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            assert proc.stdin is not None
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
        except Exception:
            pass

    def _drain(self) -> None:
        """清空积压行（MESSAGE/ERROR/OK 与上一次的残余），只认着法行。"""
        while True:
            try:
                self._lines.get_nowait()
            except queue.Empty:
                return

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _ensure(self) -> bool:
        if self._closed:
            return False
        if not self._alive():
            try:
                self._start()
            except Exception:
                return False
        return True

    def stop(self) -> None:
        """请求中止当前搜索（杀进程；下一次 best_move 自动重启）。"""
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    def close(self) -> None:
        """结束引擎进程（应用退出时调用）。"""
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.poll() is None and proc.stdin is not None:
                    proc.stdin.write("END\n")
                    proc.stdin.flush()
            except Exception:
                pass
            try:
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

    # ------------------------------------------------------------ 着法
    def best_move(self, board, color: int) -> tuple[int, int] | None:
        """返回引擎为 color 选出的 (x, y)；任何失败返回 None（调用方回退）。

        board: liuziqi.board.Board（只用 size/grid/history/win_count）。
        协议按整盘 history 全量发送，行棋方由子数奇偶推断——与 color 不一致
        （history 与请求矛盾）时直接放弃，绝不把着法落到错误的颜色上。
        """
        with self._lock:
            if not self._ensure():
                return None
            try:
                return self._best_move_locked(board, color)
            except Exception:
                self.stop()
                return None

    def _best_move_locked(self, board, color: int) -> tuple[int, int] | None:
        size = board.size
        n_black = n_white = 0
        payload = ["BOARD"]
        for hx, hy, hc in board.history:
            if hc == 1:
                n_black += 1
            elif hc == 2:
                n_white += 1
            payload.append(f"{hx},{hy},{hc}")
        payload.append("DONE")
        # 黑先：子数相等→黑走；黑多一子→白走。与请求方颜色不符即状态矛盾。
        side_ok = (n_black == n_white) if color == 1 else (n_black == n_white + 1)
        if not side_ok:
            return None
        self._drain()
        self._send("\n".join(payload))
        deadline = time.monotonic() + self._time_ms / 1000.0 + _MOVE_SLACK_S
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                self.stop()
                return None
            try:
                line = self._lines.get(timeout=remain)
            except queue.Empty:
                self.stop()
                return None
            if line is None:                      # 进程 EOF（崩了）
                self.stop()
                return None
            m = _MOVE_RE.match(line)
            if not m:
                continue                          # MESSAGE/ERROR/OK 行
            x, y = int(m.group(1)), int(m.group(2))
            if not (0 <= x < size and 0 <= y < size):
                continue                          # 越界应答，忽略继续等
            if board.grid[y][x] != 0:
                continue                          # 占用点，忽略继续等
            return (x, y)


# ------------------------------------------------------------ 进程级单例
def get_shared_engine() -> RapfiEngine:
    """跨局复用的单例（NNUE 权重只加载一次）。"""
    global _shared
    with _shared_lock:
        if _shared is None or _shared._closed:
            _shared = RapfiEngine()
        return _shared


def close_shared_engine() -> None:
    global _shared
    with _shared_lock:
        if _shared is not None:
            try:
                _shared.close()
            except Exception:
                pass
            _shared = None


atexit.register(close_shared_engine)
