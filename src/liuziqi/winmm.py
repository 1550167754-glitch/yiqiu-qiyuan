"""
winmm.py —— MCI（winmm.dll mciSendStringW）线程安全访问层

背景音乐（music.py）与游戏音效（sounds.py）都经此模块访问 MCI。
全局串行锁保证任意时刻至多一条 mciSendStringW 在执行——MCI 非线程安全，
此前多线程并发查询与主线程切歌/关窗互相等待，曾造成 mciSendStringW
永久阻塞、界面卡死。

本模块把所有 winmm 调用收口到单点串行化：
    - 正常情况：单条命令 <1ms；
    - 极端情况（设备被占用 / 驱动异常）：单条命令持锁卡死，只会阻塞
      "音频调用方线程"，与 UI 主线程完全隔离。

因此调用方必须遵守架构约束：**本模块只允许在非 UI 线程中使用**
（music 引擎线程 / sounds 工作线程）。UI 主线程一律经 music/sounds 的
"投递 + 状态轮询"接口交互，绝不直接调用本模块——这是"音频故障不冻结
界面"的根本保证。

接口：
    available() -> bool        winmm 是否可用（非 Windows 返回 False）
    raw(cmd) -> str            不加锁发送单条命令，返回响应文本（须已持有锁）
    raw_rc(cmd) -> int         不加锁发送单条命令，返回 MCI 返回码（0=成功）
    send(cmd) -> str           加锁发送单条命令，返回响应文本；超时/异常返回 ""
    send_rc(cmd) -> int        加锁发送单条命令，返回 MCI 返回码（0=成功）
    locked(timeout)            上下文管理器：持锁执行多步事务（如 close→open→play）；
                               拿不到锁时 yield False，块内命令自动全部跳过

注意：open/close/play 等命令成功时往往**没有输出文本**（返回空串），
与失败无法靠文本区分；需要判断命令是否成功时必须用 raw_rc / send_rc
（返回码 0 表示成功）。
"""
from __future__ import annotations

import ctypes
import os
import threading
from contextlib import contextmanager

_LOCK = threading.Lock()
_WINMM = None
_WINMM_CHECKED = False


def _winmm():
    """惰性加载 winmm.dll；非 Windows / 加载失败返回 None。"""
    global _WINMM, _WINMM_CHECKED
    if not _WINMM_CHECKED:
        _WINMM_CHECKED = True
        try:
            if os.name == "nt":
                _WINMM = ctypes.windll.winmm
            else:
                _WINMM = None
        except Exception:
            _WINMM = None
    return _WINMM


def available() -> bool:
    """winmm 是否可用。"""
    return _winmm() is not None


def raw(cmd: str) -> str:
    """不加锁发送单条 MCI 命令，返回响应文本（仅用于 status/position 等）。

    注意：open/close/play 等命令成功时通常无输出文本，需判断成败请用 raw_rc。
    仅在已持有 winmm 全局锁（locked() 块内）或引擎独占时调用。
    失败返回 ""。绝不抛异常。
    """
    wm = _winmm()
    if wm is None:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        ret = wm.mciSendStringW(cmd, buf, 256, None)
        return buf.value if ret == 0 else ""
    except Exception:
        return ""


def raw_rc(cmd: str) -> int:
    """不加锁发送单条 MCI 命令，返回 MCI 返回码（0=成功，负值/非 0=失败）。

    仅在已持有锁（locked() 块内）或引擎独占时调用。异常返回 -1。
    """
    wm = _winmm()
    if wm is None:
        return -1
    try:
        buf = ctypes.create_unicode_buffer(256)
        return wm.mciSendStringW(cmd, buf, 256, None)
    except Exception:
        return -1


def send(cmd: str, timeout: float = 1.0) -> str:
    """加锁发送单条 MCI 命令。

    获取锁超时（默认 1s）则放弃本条命令返回 ""。任何情况下调用线程
    不会被永久阻塞（最坏等待 timeout 秒后返回）。绝不抛异常。
    """
    if not available():
        return ""
    try:
        if not _LOCK.acquire(timeout=timeout):
            return ""
    except Exception:
        return ""
    try:
        return raw(cmd)
    finally:
        try:
            _LOCK.release()
        except Exception:
            pass


def send_rc(cmd: str, timeout: float = 1.0) -> int:
    """加锁发送单条 MCI 命令，返回 MCI 返回码（0=成功）。

    获取锁超时（默认 1s）则放弃本条命令返回 -1。任何情况下调用线程
    不会被永久阻塞（最坏等待 timeout 秒后返回）。绝不抛异常。
    """
    if not available():
        return -1
    try:
        if not _LOCK.acquire(timeout=timeout):
            return -1
    except Exception:
        return -1
    try:
        return raw_rc(cmd)
    finally:
        try:
            _LOCK.release()
        except Exception:
            pass


@contextmanager
def locked(timeout: float = 1.0):
    """持锁执行多步 MCI 事务。

    用法：:

        with winmm.locked(1.0) as ok:
            if not ok:
                return            # 拿不到锁，静默放弃整段事务
            winmm.raw("close a")
            if winmm.raw('open "..." type waveaudio alias a'):
                winmm.raw("play a")

    事务块内用 raw() 免锁发送，保证 close→open→play 不被其它线程的命令
    插队打断。
    """
    got = False
    if available():
        try:
            got = _LOCK.acquire(timeout=timeout)
        except Exception:
            got = False
    try:
        yield got
    finally:
        if got:
            try:
                _LOCK.release()
            except Exception:
                pass


def force_unlock() -> bool:
    """逃生口：释放/重建全局锁，用于调用方线程被 MCI 卡死后的自愈。

    背景：``locked()`` 的 timeout 只限制**等待拿锁**的时间。一旦拿到锁后
    ``mciSendStringW`` 本身卡死（设备被其它程序独占、驱动异常），
    ``finally`` 永远不会执行，锁被永久持有 → 音效与音乐双双哑掉且无法恢复。

    这里先尝试正常释放；失败（锁已被死线程持有）则**换成一把新锁**，
    让后续调用立即恢复正常。旧锁随死线程的引用最终被回收。
    返回 True 表示走了重建路径（调用方应记录一次异常）。
    """
    global _LOCK
    rebuilt = False
    try:
        _LOCK.release()
    except Exception:
        pass
    try:
        # 探测旧锁是否仍被占用：能立刻 acquire 说明其实没被持有
        if _LOCK.acquire(blocking=False):
            _LOCK.release()
        else:
            rebuilt = True
    except Exception:
        rebuilt = True
    if rebuilt:
        try:
            _LOCK = threading.Lock()
        except Exception:
            pass
    return rebuilt
