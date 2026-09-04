"""
sounds.py —— 游戏音效模块（零第三方依赖）

设计说明：
    - 音效用 Python 标准库（wave / struct / math）**程序化合成**为 WAV 文件，
      首次运行时自动生成到 assets/sounds/ 目录；之后直接播放，无需联网、无版权问题。
    - 若要替换成真实音效素材：把同名 .wav（stone / win / lose / click）
      覆盖到 assets/sounds/ 即可，程序会优先使用已有文件。
    - 背景音乐由 music.py（MCI 播放器）负责，歌单在 assets/music/，
      此处不再合成 BGM。
    - 播放统一使用 MCI（winmm.dll mciSendStringW）异步播放，与背景音乐
      （music.py）共享 winmm.py 全局串行锁，避免并发命令互相等待。
    - 所有 MCI 命令在**独立音效工作线程**中执行（close→open→play 事务）。
      UI 主线程调用 play() 只入队、立即返回——即使音频设备异常导致 MCI
      卡死，也只会让音效静默，绝不冻结界面。这是与音乐引擎一致的架构。
    - 非 Windows 或播放失败时静默降级（不影响游戏）。

音效清单：
    stone.wav : 落子声（木质敲击，短促）
    win.wav   : 获胜音（上行琶音，欢快）
    lose.wav  : 失败音（下行音，低沉）
    click.wav : 按钮点击声（短哔）
"""
from __future__ import annotations
import functools
import math
import os
import queue
import random
import struct
import threading
import wave

from . import winmm
from .paths import resource

ASSETS_DIR = resource("assets", "sounds", writable=True)
RATE = 44100

# 音效专用 MCI 别名（与背景音乐 connect6_bgm 相互独立）
_SFX_ALIAS = "connect6_sfx"

# ---- 音效工作线程：所有 MCI 命令在独立线程执行，UI 主线程永不触碰 winmm ----
_SFX_QUEUE: "queue.Queue" | None = None
_SFX_WORKER_STARTED = False
_SFX_WORKER_LOCK = threading.Lock()
_SFX_QUEUE_MAX = 16


def _sfx_worker_loop():
    """音效工作线程：串行消费播放任务。"""
    global _SFX_QUEUE
    while True:
        try:
            task = _SFX_QUEUE.get(timeout=0.3) if _SFX_QUEUE else None
        except queue.Empty:
            continue
        except Exception:
            break
        if task is None:
            break
        try:
            task()
        except Exception:
            pass


def _ensure_worker():
    """惰性启动音效工作线程（幂等）。非 Windows 不启动。"""
    global _SFX_QUEUE, _SFX_WORKER_STARTED
    if os.name != "nt":
        return
    with _SFX_WORKER_LOCK:
        if _SFX_WORKER_STARTED:
            return
        _SFX_WORKER_STARTED = True
        try:
            _SFX_QUEUE = queue.Queue(maxsize=_SFX_QUEUE_MAX)
            threading.Thread(target=_sfx_worker_loop,
                             name="sfx-worker", daemon=True).start()
        except Exception:
            _SFX_QUEUE = None


def _enqueue(task):
    """投递任务到音效工作线程；满则丢弃最旧一条。永不阻塞。"""
    if _SFX_QUEUE is None:
        return
    try:
        _SFX_QUEUE.put_nowait(task)
    except queue.Full:
        try:
            _SFX_QUEUE.get_nowait()
        except Exception:
            pass
        try:
            _SFX_QUEUE.put_nowait(task)
        except Exception:
            pass
    except Exception:
        pass


def _write_wav(path: str, samples: list[float], volume: float = 1.0):
    """把采样列表写为 16bit 单声道 WAV 文件（volume 为全局音量系数）。"""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-32767.0, min(32767.0, s * volume)) * 32767))
            for s in samples)
        w.writeframes(frames)


def _tone(freq: float, dur: float, volume: float = 0.8) -> list[float]:
    """生成一个正弦波（带 5ms 淡入淡出防爆音）。"""
    n = int(RATE * dur)
    fade = int(RATE * 0.005)
    out: list[float] = []
    for i in range(n):
        t = i / RATE
        env = (min(1.0, i / max(1, fade))
               * min(1.0, (n - i) / max(1, fade)))
        out.append(math.sin(2 * math.pi * freq * t) * volume * env)
    return out


def _mix(tracks: list[float], dur: float | None = None) -> list[float]:
    """把多条等长轨道叠加（长度不足补零）。"""
    if tracks:
        length = max(len(t) for t in tracks)
    else:
        length = int(RATE * (dur or 0.5))
    out = [0.0] * length
    for tr in tracks:
        for i, v in enumerate(tr):
            out[i] += v
    return out


def _gen_stone() -> list[float]:
    """落子声：两个短促敲击频率 + 噪声头，快速衰减，像棋子落在木盘上。"""
    rng = random.Random(7)
    n = int(RATE * 0.07)
    out: list[float] = []
    for i in range(n):
        t = i / RATE
        env = math.exp(-t * 60)
        s = (math.sin(2 * math.pi * 880 * t) * 0.55
             + math.sin(2 * math.pi * 1380 * t) * 0.22)
        s += (rng.random() * 2 - 1) * 0.16 * math.exp(-t * 150)
        out.append(s * env * 0.9)
    return out


def _gen_win() -> list[float]:
    """获胜音：C5-E5-G5-C6 上行琶音 + 结尾高音长音，喜庆。"""
    notes = [523.25, 659.25, 783.99, 1046.5]
    track: list[float] = []
    gap = int(RATE * 0.02)
    for f in notes:
        track.extend(_tone(f, 0.15, 0.7))
        track.extend([0.0] * gap)
    track.extend(_tone(1568.0, 0.4, 0.35))
    return track


def _gen_lose() -> list[float]:
    """失败音：G3-E3-C3 下行，低沉。"""
    notes = [196.0, 164.81, 130.81]
    track: list[float] = []
    gap = int(RATE * 0.03)
    for f in notes:
        track.extend(_tone(f, 0.22, 0.55))
        track.extend([0.0] * gap)
    return track


def _gen_click() -> list[float]:
    """按钮点击声：短哔。"""
    return _tone(1200.0, 0.05, 0.6)


GENERATORS = {
    "stone": _gen_stone,
    "win": _gen_win,
    "lose": _gen_lose,
    "click": _gen_click,
}


class SoundManager:
    """游戏音效管理器。

    用法：
        sm = SoundManager()          # 首次调用会自动生成缺失的 WAV
        sm.play("stone")             # 异步播放音效
        sm.toggle()                  # 开/关音效，返回新状态
    """

    def __init__(self, enabled: bool = True, sound_dir: str = ASSETS_DIR):
        self.sound_dir = sound_dir
        self.enabled = enabled
        self.volume = 1.0
        self.files = {name: os.path.join(sound_dir, name + ".wav")
                      for name in GENERATORS}
        self._ensure_files()
        _ensure_worker()

    def _ensure_files(self):
        """缺失的音效文件自动生成（幂等）。"""
        try:
            os.makedirs(self.sound_dir, exist_ok=True)
            for name, path in self.files.items():
                if os.path.exists(path):
                    continue
                _write_wav(path, GENERATORS[name]())
        except OSError:
            self.files = {}

    def set_volume(self, volume: float) -> float:
        """设置全局音量（0.0 ~ 1.0）：重新生成全部 WAV 应用音量系数。

        返回实际生效的音量。生成失败时静默忽略（音量保持旧值文件）。
        """
        self.volume = max(0.0, min(1.0, float(volume)))
        try:
            for name, path in self.files.items():
                _write_wav(path, GENERATORS[name](), self.volume)
        except (OSError, KeyError):
            pass
        return self.volume

    def play(self, name: str):
        """异步播放指定音效（入队后立即返回，不触碰 MCI）。

        重要：音效与背景音乐统一走 MCI（winmm），**不得使用 winsound**。
        winsound.PlaySound 与 MCI waveaudio 分属两套音频通路，会争抢同一
        波形输出设备并互相等待（实测 mciSendStringW 永久阻塞 → 界面卡死）。
        所有 winmm 命令在独立音效工作线程执行并经 winmm 全局串行锁——
        即使设备异常导致命令卡死，也只影响音效线程（最多音效静默），
        UI 主线程调用本方法永远立即返回，不会卡死界面。
        """
        if not self.enabled or not self.files or name not in self.files:
            return
        path = self.files[name]
        if not os.path.exists(path):
            return
        if os.name != "nt" or _SFX_QUEUE is None:
            return
        try:
            _enqueue(functools.partial(self._play_task, path))
        except Exception:
            pass

    def _play_task(self, path: str):
        """音效工作线程内：close→open→play 事务（经 winmm 串行锁）。"""
        with winmm.locked(1.0) as ok:
            if not ok:
                return
            # 先关闭上一段（会打断未播完的同名音效，短音效可接受）
            winmm.raw_rc(f"close {_SFX_ALIAS}")
            if winmm.raw_rc(
                    f'open "{path}" type waveaudio alias {_SFX_ALIAS}') == 0:
                # play 立即返回，native 异步播放
                winmm.raw_rc(f"play {_SFX_ALIAS}")

    def toggle(self) -> bool:
        """切换音效开关状态，返回新状态。"""
        self.enabled = not self.enabled
        return self.enabled

    def __repr__(self):
        return f"SoundManager(enabled={self.enabled}, files={len(self.files)})"
