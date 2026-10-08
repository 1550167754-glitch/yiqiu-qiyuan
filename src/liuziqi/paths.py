# -*- coding: utf-8 -*-
"""
paths.py —— 资源路径解析（开发环境 / PyInstaller 打包环境通用）

开发时：资源根 = 项目根（src/liuziqi/../..）
打包后：exe 同目录 = 可写外部根（config / assets/music 等用户可修改资源），
        sys._MEIPASS = 只读内建资源（字体、图标、默认配置的兜底副本）。

约定：所有"可能被用户修改/写入"的资源（config、assets/music、assets/sounds）
优先解析到 exe 同目录；"只读展示"资源（字体、菜单图片、logo）直接解析到
内建（找不到时再回退外部）。
"""
from __future__ import annotations

import os
import sys
from os import path

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境。"""
    return bool(getattr(sys, "frozen", False))


def app_base() -> str:
    """外部可写根目录：打包后为 exe 同目录，开发时为项目根。"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return _PROJECT_ROOT


def bundled_base() -> str:
    """内建资源根：打包后为 _MEIPASS，开发时与 app_base 相同。"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", app_base())
    return app_base()


def first_existing(*paths: str) -> str:
    """取第一个存在的路径；都不存在时返回第一个（调用方自行降级）。"""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


def resource(*rel: str, writable: bool = False) -> str:
    """按优先级解析资源路径。

    rel      : 相对资源根的路径片段，如 ("assets", "music") 或 ("config",)
    writable : True 时优先外部（exe 同目录），否则优先内建（_MEIPASS）。
    """
    rel = os.path.join(*rel)
    bnd = os.path.join(bundled_base(), rel)
    ext = os.path.join(app_base(), rel)
    if writable:
        return first_existing(ext, bnd)
    return first_existing(bnd, ext)


def logs_dir() -> str:
    """统一日志目录（固定，不存在则创建一次）。

    所有运行期日志（看门狗 freeze_dump.log、异常堆栈等）都写到这里，
    避免每次启动在项目根目录散落文件；目录固定复用，不会重复新建。
    """
    d = os.path.join(app_base(), "logs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = app_base()
    return d


def data_dir() -> str:
    """统一数据目录（固定，不存在则创建一次）。

    数据库 / 记录相关的运行期产物（生成的数据库引导脚本、本地存档缓存等）
    统一放这里，保证始终复用同一个固定目录，不在启动时新建。
    """
    d = os.path.join(app_base(), "data")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = app_base()
    return d


def project_root() -> str:
    """兼容旧接口：返回项目根（开发环境）/ exe 同目录（打包环境）。"""
    return app_base()
