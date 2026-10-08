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
    stone.mp3 : 落子声（用户提供的真实音效素材，优先使用；缺失时回退合成 stone.wav）
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

# 用户自定义音效素材（存在则优先使用，且绝不被程序化合成覆盖）。
# MP3 通过 MCI mpegvideo 设备播放，与 WAV(waveaudio) 共用同一套工作线程。
_CUSTOM_FILES = {"stone": "stone.mp3"}

# 音效专用 MCI 别名（与背景音乐 connect6_bgm 相互独立）
_SFX_ALIAS = "connect6_sfx"

# ---- 音效工作线程：所有 MCI 命令在独立线程执行，UI 主线程永不触碰 winmm ----
# **双轨队列**：waveaudio 的 play 在 MCI 命令串层是**同步阻塞**（实测播 255ms
# 的 wav 命令 309~460ms 才返回，notify 无效）——若与落子音效同队列串行，
# click/win/lose 会把落子音拖后 300ms+（"落子音效延迟"实测根因之一）。
# 故 mp3(mpegvideo，play 异步) 与 wav(waveaudio，play 阻塞) 分两轨各自串行。
# _SFX_QUEUE 仍是主队列（gui._sfx_health_check 监控它）。
_SFX_QUEUE: "queue.Queue" | None = None          # mp3 / 快速轨
_SFX_QUEUE_WAV: "queue.Queue" | None = None      # wav 轨（play 同步阻塞，隔离）
_SFX_WORKER_STARTED = False
_SFX_WORKER_LOCK = threading.Lock()
_SFX_QUEUE_MAX = 16

# 常驻 MCI alias（按文件缓存）：open 的设备初始化实测 15~45ms（mpegvideo
# 尤甚），常驻后重播只需 seek to start + play（~10ms）。seek 会停掉上一次
# 播放并归零，与旧实现"close 打断上一声"语义等价。
_ALIASES: dict[str, str] = {}
_ALIAS_SEQ = 0


def _sfx_worker_loop(q: "queue.Queue"):
    """音效工作线程：串行消费所在轨的播放任务。"""
    while True:
        try:
            task = q.get(timeout=0.3)
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
    global _SFX_QUEUE, _SFX_QUEUE_WAV, _SFX_WORKER_STARTED
    if os.name != "nt":
        return
    with _SFX_WORKER_LOCK:
        if _SFX_WORKER_STARTED:
            return
        _SFX_WORKER_STARTED = True
        try:
            _SFX_QUEUE = queue.Queue(maxsize=_SFX_QUEUE_MAX)
            _SFX_QUEUE_WAV = queue.Queue(maxsize=_SFX_QUEUE_MAX)
            threading.Thread(target=_sfx_worker_loop, args=(_SFX_QUEUE,),
                             name="sfx-worker-mp3", daemon=True).start()
            threading.Thread(target=_sfx_worker_loop, args=(_SFX_QUEUE_WAV,),
                             name="sfx-worker-wav", daemon=True).start()
        except Exception:
            _SFX_QUEUE = None


def _enqueue(task, q: "queue.Queue | None"):
    """投递任务到指定音效队列；满则丢弃最旧一条。永不阻塞。"""
    if q is None:
        return
    try:
        q.put_nowait(task)
    except queue.Full:
        try:
            q.get_nowait()
        except Exception:
            pass
        try:
            q.put_nowait(task)
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
    """落子声：清脆"嗒嗒嗒"三连击（石/玉质敲击）。

    每声"嗒" = 高频脆响(材质环) + 一点低_body(增质感) + 极短噪声瞬态(撞击感)，
    快速衰减；三声间距紧凑、音量递减、音高微扬，合成有质感的清脆落子 clack。
    """
    rng = random.Random(31)

    def _click(freq: float, dur: float, vol: float) -> list[float]:
        n = max(1, int(RATE * dur))
        out: list[float] = []
        for i in range(n):
            t = i / RATE
            env = math.exp(-t * 70.0)                       # 快衰减 → 脆
            tok = math.sin(2 * math.pi * freq * t)          # 材质环（清脆）
            thock = math.sin(2 * math.pi * (freq * 0.42) * t) * 0.35  # 低_body，增质感
            noise = (rng.random() * 2 - 1) * math.exp(-t * 220.0) * 0.5  # 撞击瞬态
            out.append((tok + thock + noise) * env * vol)
        return out

    clicks = [
        _click(2500.0, 0.045, 1.00),
        _click(2700.0, 0.040, 0.82),
        _click(2350.0, 0.045, 0.68),
    ]
    gaps = [int(RATE * 0.045), int(RATE * 0.050)]          # 紧凑间距
    out: list[float] = []
    pos = 0
    for k, ck in enumerate(clicks):
        while len(out) < pos:
            out.append(0.0)
        out.extend(ck)
        pos = len(out) + (gaps[k] if k < len(gaps) else 0)
    out.extend([0.0] * int(RATE * 0.03))                    # 收尾余韵
    peak = max((abs(v) for v in out), default=1e-6)
    scale = min(1.0, 0.95 / max(1e-6, peak))               # 软限幅防削波
    return [v * scale for v in out]


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
        # 自定义素材优先（如 stone.mp3）：存在即接管该音效，不再生成/覆盖
        self._custom: set[str] = set()
        for name, fname in _CUSTOM_FILES.items():
            p = os.path.join(sound_dir, fname)
            if os.path.exists(p):
                self.files[name] = p
                self._custom.add(name)
        self._ensure_files()
        _ensure_worker()

    def _ensure_files(self):
        """缺失的音效文件自动生成（幂等）；自定义素材（_custom）跳过。"""
        try:
            os.makedirs(self.sound_dir, exist_ok=True)
            for name, path in self.files.items():
                if name in self._custom or os.path.exists(path):
                    continue
                _write_wav(path, GENERATORS[name]())
        except OSError:
            self.files = {}

    def set_volume(self, volume: float) -> float:
        """设置全局音量（0.0 ~ 1.0）：重新生成合成 WAV 应用音量系数。

        自定义素材（如 stone.mp3）不做文件级改写，其音量在播放时
        通过 MCI setaudio 实时施加。返回实际生效的音量。
        """
        self.volume = max(0.0, min(1.0, float(volume)))
        try:
            for name, path in self.files.items():
                if name in self._custom:
                    continue
                _write_wav(path, GENERATORS[name](), self.volume)
        except (OSError, KeyError):
            pass
        return self.volume

    def _play_task(self, path: str):
        """音效工作线程内：常驻 alias + seek/play 事务（经 winmm 串行锁）。

        WAV 走 waveaudio 设备；MP3 走 mpegvideo 设备（Windows 内置
        MPEG-1 Layer-3 解码器），音量经 setaudio 实时施加（0~1000）。
        """
        ext = os.path.splitext(path)[1].lower()
        dev = "mpegvideo" if ext == ".mp3" else "waveaudio"
        with winmm.locked(1.0) as ok:
            if not ok:
                return
            alias = _ALIASES.get(path)
            if alias is None:
                global _ALIAS_SEQ
                _ALIAS_SEQ += 1
                alias = f"{_SFX_ALIAS}{_ALIAS_SEQ}"
                if winmm.raw_rc(
                        f'open "{path}" type {dev} alias {alias}') != 0:
                    return
                _ALIASES[path] = alias
            # seek 归零并打断上一声（等价旧 close 语义），锁内完成（瞬时）
            winmm.raw_rc(f"seek {alias} to start")
        # play 在锁外发：waveaudio 的 play 同步等播完（实测 300ms+，MCI
        # 命令串层无异步语义、notify 无效），持锁会卡背景音乐的控制命令；
        # 锁外播放只影响本轨串行（wav 轨独立，不拖累落子音效轨）。
        if dev == "mpegvideo" and self.volume < 1.0:
            winmm.raw_rc(
                f"setaudio {alias} volume to "
                f"{int(max(0.0, min(1.0, self.volume)) * 1000)}")
        winmm.raw_rc(f"play {alias}")

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
            # 分流：wav 走慢轨（play 同步阻塞，隔离），其余走主轨
            q = (_SFX_QUEUE_WAV
                 if os.path.splitext(path)[1].lower() == ".wav"
                 else _SFX_QUEUE)
            _enqueue(functools.partial(self._play_task, path), q)
        except Exception:
            pass

    def recover(self):
        """音效自愈：重建 winmm 全局锁并清空设备（供 GUI 定时调用）。

        背景：设备被其它程序独占或驱动异常时，``mciSendStringW`` 可能永久
        阻塞 → 工作线程卡死且永不释放全局锁，之后所有音效与背景音双双
        静默（"下到一半没音效"）。这里用 force_unlock 换一把新锁，
        代价是丢失被卡线程持有的那把旧锁，音频立即恢复正常。
        """
        try:
            winmm.force_unlock()
        except Exception:
            return
        # 关闭全部常驻 alias 并清缓存（下次 play 自动重新 open）
        for alias in list(_ALIASES.values()):
            try:
                winmm.send(f"close {alias}", 0.2)
            except Exception:
                pass
        _ALIASES.clear()

    def __repr__(self):
        return f"SoundManager(enabled={self.enabled}, files={len(self.files)})"
