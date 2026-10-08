"""
music.py —— 背景音乐播放系统（歌单 + 播放控制，零第三方依赖）

架构（音频引擎线程模式）：
    - 播放引擎使用 Windows 多媒体命令接口（winmm.dll 的 mciSendStringW），
      背景音乐（music.py）与音效（sounds.py）统一走 MCI，并共享
      winmm.py 的全局串行锁——任何时刻至多一条 MCI 命令在执行。
    - **所有 MCI 命令只在独立的音乐引擎线程中执行**。主线程（tkinter UI）
      的公开接口一律是"入队投递 + 立即返回"，通过读取引擎缓存的状态
      （poll_state）感知播放进度。因此即使底层音频设备异常导致 MCI 命令
      卡死，也只影响引擎线程（表现为音乐静默），界面主线程永不阻塞。
    - 此前版本把 MCI 全部放在主线程串行访问，虽然消除了多线程竞争，却把
      "音频设备挂起"的风险架在 UI 心脏上：只要一条 mciSendStringW 卡住，
      整个窗口就冻结（点不动、关不掉）。引擎线程模式从架构上根治此问题。
    - 播放模式：列表循环（loop）/ 单曲循环（single）/ 随机播放（shuffle），
      曲目播完由引擎空闲巡检自动接续。
    - 非 Windows 或无音频设备时静默降级（不影响游戏）。

线程模型：
    - 引擎线程：消费命令队列，串行执行全部 MCI 操作；空闲每 0.5s 巡检
      一次播放状态并在曲目结束时自动切歌。
    - 主线程：play_index / play_current / toggle_play / next / prev / stop /
      set_volume 均为非阻塞投递；position_ms / duration_ms / status_mode /
      poll_state 只读引擎缓存，绝不发送 MCI 命令。
"""
from __future__ import annotations

import functools
import os
import queue
import random
import threading

from . import winmm
from .paths import resource

MUSIC_DIR = resource("assets", "music", writable=True)
SOUNDS_DIR = resource("assets", "sounds", writable=True)

MODE_LOOP = "loop"
MODE_SINGLE = "single"
MODE_SHUFFLE = "shuffle"
MODE_NAMES = {MODE_LOOP: "列表循环", MODE_SINGLE: "单曲循环", MODE_SHUFFLE: "随机播放"}

_ALIAS = "connect6_bgm"

SUPPORTED_EXTS = (".wav", ".flac", ".mp3", ".ogg")

# 命令队列上限：防高频操作（如拖动音量滑杆）无界堆积
_QUEUE_MAX = 64


def _to_int(s: str, default: int = 0) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


class MusicPlayer:
    """歌单 + 播放控制（引擎线程模式，所有方法对主线程非阻塞）。

    用法：
        mp = MusicPlayer()
        mp.play_index(0)          # 播放第一首（投递，立即返回）
        mp.toggle_play()          # 播放 / 暂停
        mp.next() / mp.prev()     # 切歌
        mp.set_volume(60)         # 音量 0~100
        mp.mode = "single"        # 切换播放模式
        st = mp.poll_state()      # 读取播放状态缓存（主线程轮询用）
    """

    def __init__(self, music_dir: str = MUSIC_DIR):
        self.music_dir = music_dir
        self.tracks: list[dict] = []       # 每项: {'name': 曲名, 'path': 绝对路径}
        self.index = 0
        self.mode = MODE_LOOP
        self.playing = False               # 期望播放态（引擎线程校正）
        self._volume = 60

        self._mci_ok = winmm.available()
        self._refresh_tracks()

        # ---- 引擎缓存：仅引擎线程写入，主线程只读（GIL 下简单属性原子） ----
        self._mode_cache = ""              # playing / paused / stopped / ""
        self._pos_ms = 0
        self._dur_ms = 0

        # ---- 引擎线程与命令队列 ----
        self._cmd_q: "queue.Queue" = queue.Queue(maxsize=_QUEUE_MAX)
        self._alive = True
        self._engine = threading.Thread(
            target=self._engine_loop, name="music-engine", daemon=True)
        self._engine.start()

    # ---------------------------------------------------------------- 引擎 ----
    def _engine_loop(self):
        """引擎主循环：串行执行命令；空闲时巡检状态并自动接续。"""
        while self._alive:
            try:
                fn = self._cmd_q.get(timeout=0.5)
            except queue.Empty:
                # 空闲巡检：刷新状态缓存 + 曲目播完自动接续
                try:
                    self._refresh_state()
                    self._auto_advance()
                except Exception:
                    pass
                continue
            except Exception:
                break
            try:
                fn()
            except Exception:
                pass
            try:
                self._refresh_state()
            except Exception:
                pass

    def _post(self, fn, *args):
        """把一条任务投递给引擎线程（满则丢弃最旧一条再入队）。永不阻塞。"""
        if not self._alive:
            return
        task = functools.partial(fn, *args) if args else fn
        try:
            self._cmd_q.put_nowait(task)
        except queue.Full:
            try:
                self._cmd_q.get_nowait()
            except Exception:
                pass
            try:
                self._cmd_q.put_nowait(task)
            except Exception:
                pass
        except Exception:
            pass

    # ---- 引擎线程内执行的 MCI 原语 ----
    def _mci(self, cmd: str) -> str:
        """引擎线程内发送一条 MCI 命令（经 winmm 全局锁与音效串行）。"""
        if not self._mci_ok:
            return ""
        return winmm.send(cmd)

    def _refresh_state(self):
        """刷新播放状态缓存（引擎线程）。"""
        if not self._mci_ok or not self.playing:
            return
        mode = self._mci(f"status {_ALIAS} mode")
        self._mode_cache = mode
        if mode in ("playing", "paused"):
            self._pos_ms = _to_int(self._mci(f"status {_ALIAS} position"))
            self._dur_ms = _to_int(self._mci(f"status {_ALIAS} length"))
        elif mode == "stopped":
            # 播完：position 停在末尾，交给 _auto_advance 接续
            if not self._dur_ms:
                self._dur_ms = _to_int(self._mci(f"status {_ALIAS} length"))

    def _auto_advance(self):
        """曲目结束自动接续（单曲重播 / 列表或随机下一首）。"""
        if not self._mci_ok or not self.playing or not self.tracks:
            return
        mode = self._mode_cache
        if mode == "paused":
            return
        pos, dur = self._pos_ms, self._dur_ms
        if mode == "stopped" or (dur > 0 and pos >= dur - 300):
            if self.mode == MODE_SINGLE:
                self._open_and_play(self.index)
            else:
                self._open_and_play(self._pick_next_index())

    # ------------------------------------------------------------ 引擎任务 ----
    def _cmd_play_index(self, i: int):
        """引擎任务：打开并播放第 i 首。"""
        self._open_and_play(i)

    def _cmd_toggle(self, want: bool):
        """引擎任务：把播放状态置为 want。"""
        if want:
            mode = self._mci(f"status {_ALIAS} mode")
            if mode == "paused":
                self._mci(f"resume {_ALIAS}")
                self.playing = True
                self._mode_cache = "playing"
                return
            # 未开设备 / 已停止 → 重新打开当前曲目播放
            self._open_and_play(self.index)
        else:
            self._mci(f"pause {_ALIAS}")
            self.playing = False
            self._mode_cache = "paused"

    def _cmd_stop(self):
        """引擎任务：停止并释放设备。"""
        self._mci(f"stop {_ALIAS}")
        self._mci(f"close {_ALIAS}")
        self.playing = False
        self._mode_cache = ""
        self._pos_ms = 0
        self._dur_ms = 0

    def _cmd_volume(self, v: int):
        """引擎任务：应用音量（MCI setaudio + 波形输出音量）。"""
        self._mci(f"setaudio {_ALIAS} volume to {int(v * 10)}")
        self._apply_wave_volume()

    def _open_and_play(self, i: int):
        """引擎线程内：打开第 i 首并播放。"""
        if not self.tracks or not self._mci_ok:
            self.playing = False
            return
        i = i % len(self.tracks)
        self.index = i
        path = self.tracks[i]["path"]

        # 先释放上一个设备，避免 MCI 别名占用导致错乱
        self._mci(f"close {_ALIAS}")

        playable, mtype = self._resolve_playable(path)
        if playable and winmm.send_rc(
                f'open "{playable}" type {mtype} alias {_ALIAS}') == 0:
            self._mci(f"setaudio {_ALIAS} volume to {int(self._volume * 10)}")
            self._apply_wave_volume()
            self._mci(f"play {_ALIAS}")
            self.playing = True
            self._mode_cache = "playing"
            self._pos_ms = 0
            self._dur_ms = 0
            return
        self.playing = False
        self._mode_cache = ""

    def _apply_wave_volume(self):
        """把音量写入本进程波形输出会话（0~100 → 0x0000~0xFFFF）。"""
        if not self._mci_ok:
            return
        try:
            v = int(max(0, min(100, self._volume)) * 0xFFFF / 100)
            dw = (v & 0xFFFF) | ((v & 0xFFFF) << 16)   # 左右声道
            import ctypes
            ctypes.windll.winmm.waveOutSetVolume(
                ctypes.c_uint(0xFFFFFFFF), ctypes.c_uint(dw))  # WAVE_MAPPER
        except Exception:
            pass

    def _pick_next_index(self) -> int:
        """按播放模式选择下一首索引。"""
        n = len(self.tracks)
        if n <= 1:
            return self.index
        if self.mode == MODE_SHUFFLE:
            others = [i for i in range(n) if i != self.index]
            return random.choice(others)
        return (self.index + 1) % n

    # ------------------------------------------------------------ 歌单管理 ----
    def _refresh_tracks(self):
        """扫描歌单目录；为空时复制内置《高山流水》。"""
        try:
            os.makedirs(self.music_dir, exist_ok=True)
        except OSError:
            self.music_dir = SOUNDS_DIR
            try:
                os.makedirs(self.music_dir, exist_ok=True)
            except OSError:
                pass

        try:
            files = sorted(f for f in os.listdir(self.music_dir)
                           if f.lower().endswith(SUPPORTED_EXTS))
        except OSError:
            files = []
        self.tracks = [{"name": os.path.splitext(f)[0],
                        "path": os.path.join(self.music_dir, f)}
                       for f in files]
        if self.index >= len(self.tracks):
            self.index = 0

    @property
    def current(self) -> dict | None:
        if not self.tracks:
            return None
        return self.tracks[self.index % len(self.tracks)]

    # ------------------------------------------------------- 主线程公开接口 ----
    def play_index(self, i: int):
        """播放指定歌单位置（投递后立即返回）。"""
        if not self.tracks or not self._mci_ok:
            return
        i = i % len(self.tracks)
        self.index = i
        self.playing = True
        self._post(self._cmd_play_index, i)

    def play_current(self):
        """重新播放当前曲目（投递后立即返回）。"""
        if not self.tracks or not self._mci_ok:
            return
        self.playing = True
        self._post(self._cmd_play_index, self.index)

    def toggle_play(self) -> bool:
        """播放 / 暂停切换，返回目标播放状态（乐观值，引擎随后执行）。"""
        if not self.tracks:
            return False
        if not self._mci_ok:
            return False
        self.playing = not self.playing
        self._post(self._cmd_toggle, self.playing)
        return self.playing

    def next(self) -> dict | None:
        """下一首（按播放模式选择；投递后立即返回）。"""
        if not self.tracks or not self._mci_ok:
            return None
        nxt = self._pick_next_index()
        self.index = nxt
        self.playing = True
        self._post(self._cmd_play_index, nxt)
        return self.current

    def prev(self) -> dict | None:
        """上一首（投递后立即返回）。"""
        if not self.tracks or not self._mci_ok:
            return None
        nxt = (self.index - 1) % len(self.tracks)
        self.index = nxt
        self.playing = True
        self._post(self._cmd_play_index, nxt)
        return self.current

    def stop(self):
        """停止并释放设备（投递后立即返回，不等待）。"""
        self.playing = False
        self._post(self._cmd_stop)

    def shutdown(self):
        """停用引擎线程（进程退出时兜底；正常退出无需调用）。"""
        self._alive = False
        try:
            self._cmd_q.put_nowait(lambda: None)
        except Exception:
            pass

    def set_volume(self, volume: int) -> int:
        """设置音量（0~100），返回设定值（投递后立即返回）。

        对 WAV 曲目 waveaudio 设备不支持 MCI setaudio，改用
        waveOutSetVolume（Vista+ 等效本进程应用音量）真正生效。
        """
        self._volume = max(0, min(100, int(volume)))
        self._post(self._cmd_volume, self._volume)
        return self._volume

    # ---- 状态读取：只读缓存，主线程安全、绝无 MCI 命令 ----
    def status_mode(self) -> str:
        """当前设备状态缓存：playing / paused / stopped / ""。"""
        return self._mode_cache

    def position_ms(self) -> int:
        """当前播放位置（毫秒，缓存值）。"""
        return self._pos_ms

    def duration_ms(self) -> int:
        """当前曲目总时长（毫秒，缓存值）。"""
        return self._dur_ms

    def poll_state(self) -> dict:
        """给 UI 轮询的状态快照（纯内存读取，绝不触碰 MCI）。

        返回: {playing, mode, pos, dur, index, volume, ok}
            playing: 期望播放态；mode: 设备实际状态；ok: 引擎可用性。
        """
        return {
            "playing": self.playing,
            "mode": self._mode_cache,
            "pos": self._pos_ms,
            "dur": self._dur_ms,
            "index": self.index,
            "volume": self._volume,
            "ok": self._mci_ok,
        }

    # ---------------------------------------------------------------- 私有 ----
    def _resolve_playable(self, path: str) -> tuple[str | None, str | None]:
        """返回可被 MCI 播放的 (文件路径, 设备类型)。引擎线程内调用。

        - wav：waveaudio 直接播；
        - mp3：mpegvideo（DirectShow）直接播（Windows 自带解码器）；
        - flac：先尝试 mpegvideo 直开；失败则用 soundfile 转 wav 缓存。
        """
        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav":
            return path, "waveaudio"

        # mp3 / ogg / flac 先尝试 DirectShow 直开
        if winmm.send_rc(f'open "{path}" type mpegvideo alias {_ALIAS}') == 0:
            winmm.send_rc(f"close {_ALIAS}")
            return path, "mpegvideo"

        if ext == ".flac":
            wav = self._convert_to_wav(path)
            if wav:
                return wav, "waveaudio"

        return None, None

    def _convert_to_wav(self, src: str) -> str | None:
        """FLAC → WAV（16bit PCM，保持原采样率），缓存到歌单目录 .cache/。"""
        try:
            import soundfile
        except ImportError:
            return None
        try:
            cache = os.path.join(self.music_dir, ".cache")
            os.makedirs(cache, exist_ok=True)
            dst = os.path.join(cache, os.path.splitext(os.path.basename(src))[0] + ".wav")
            if os.path.exists(dst):
                return dst
            data, sr = soundfile.read(src, dtype="float32")
            soundfile.write(dst, data, sr, subtype="PCM_16")
            return dst
        except Exception:
            return None

    @property
    def volume(self) -> int:
        return self._volume

    def __repr__(self):
        cur = self.current["name"] if self.current else "-"
        return (f"MusicPlayer(mode={self.mode}, playing={self.playing}, "
                f"current={cur!r}, tracks={len(self.tracks)})")
