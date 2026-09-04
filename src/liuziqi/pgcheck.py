# -*- coding: utf-8 -*-
"""
pgcheck.py —— PostgreSQL 环境检测与引导

职责（所有需要执行的操作都必须先经用户确认，本模块只提供能力，决策在 GUI）：
    1. 检测当前环境状态：
       - running           : 服务运行中（5432 端口可连通）
       - installed_stopped : 本机已安装但服务未启动
       - not_installed     : 未检测到安装
    2. 启动服务：以管理员权限（UAC 弹窗由系统确认）运行 net start <服务名>；
    3. 生成安装引导脚本 InstallPostgreSQL.bat（引导用户到官网下载安装）。

检测策略：
    - 运行中：socket 快速探测 localhost:5432（超时 1 秒，不拖慢启动）；
    - 已安装：注册表 HKLM\\SOFTWARE\\PostgreSQL\\Installations 或
      服务列表中含 "postgres" 的服务；
    - 服务名：通过 sc query 枚举（如 postgresql-x64-17）。
"""
from __future__ import annotations

import os
import socket
import subprocess

STATUS_RUNNING = "running"
STATUS_STOPPED = "installed_stopped"
STATUS_MISSING = "not_installed"

INSTALL_BAT_NAME = "InstallPostgreSQL.bat"


def _port_open(host: str = "localhost", port: int = 5432, timeout: float = 1.0) -> bool:
    """快速探测端口是否可连。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_services() -> list[str]:
    """枚举本机含 "postgres" 的 Windows 服务名（如 postgresql-x64-17）。"""
    names: list[str] = []
    if os.name == "nt":
        try:
            # 用 bytes 捕获再手动解码：sc 输出为 OEM/GBK 编码，text=True 在
            # UTF-8 模式下会对中文字节抛 UnicodeDecodeError 导致服务识别失败
            out = subprocess.run(
                ["sc", "query", "type=", "service", "state=", "all"],
                capture_output=True, timeout=10, creationflags=0x08000000)
            text = out.stdout.decode("utf-8", errors="ignore")
            for line in text.splitlines():
                if "SERVICE_NAME:" in line:
                    name = line.split(":", 1)[1].strip()
                    if name and "postgres" in name.lower():
                        names.append(name)
        except Exception:
            pass
        # 注册表补充
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\PostgreSQL\Installations")
            i = 0
            while True:
                try:
                    names.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception:
            pass
    else:
        try:
            out = subprocess.run(["pg_lsclusters"], capture_output=True, text=True, timeout=5)
            names = [n for n in out.stdout.splitlines() if "online" not in n]
        except Exception:
            pass
    # 去重保序
    seen = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def check_status() -> str:
    """检测 PostgreSQL 当前状态。"""
    if _port_open():
        return STATUS_RUNNING
    if _find_services():
        return STATUS_STOPPED
    return STATUS_MISSING


def start_service(service_name: str) -> bool:
    """尝试启动指定服务（可能触发 UAC）。返回是否启动成功。"""
    if os.name == "nt":
        cmd = ["net", "start", service_name]
    else:
        cmd = ["sudo", "systemctl", "start", service_name]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def first_service() -> str | None:
    """返回第一个可用服务名；无则 None。"""
    svcs = _find_services()
    return svcs[0] if svcs else None


def generate_install_bat(target_dir: str) -> str:
    """生成安装引导脚本，返回脚本完整路径。"""
    path = os.path.join(target_dir, INSTALL_BAT_NAME)
    script = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "title 安装 PostgreSQL（六子棋存档所需）\r\n"
        "echo ============================================\r\n"
        "echo   六子棋 Connect6 需要 PostgreSQL 数据库\r\n"
        "echo   请从官网下载安装包并完成安装\r\n"
        "echo   官网: https://www.postgresql.org/download/windows/\r\n"
        "echo ============================================\r\n"
        "echo.\r\n"
        "echo 安装完成后，请将 config/database.ini 中的连接信息\r\n"
        "echo 改为你的实际数据库配置，然后重启本程序。\r\n"
        "echo.\r\n"
        "start https://www.postgresql.org/download/windows/\r\n"
        "pause\r\n"
    )
    try:
        with open(path, "w", encoding="gbk", errors="ignore") as f:
            f.write(script)
    except Exception:
        pass
    return path
