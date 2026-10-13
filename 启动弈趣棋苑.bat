@echo off
rem 弈趣棋苑 从源码启动脚本（使用 venv；venv 不存在时回退到 PATH 上的 python）
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON="
if exist "C:\Users\ASUS\.workbuddy\venvs\liuziqi\Scripts\python.exe" (
  set "PYTHON=C:\Users\ASUS\.workbuddy\venvs\liuziqi\Scripts\python.exe"
) else (
  where python >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON (
  echo [ERROR] 未找到 python，请先运行 scripts\setup_dev.bat 创建 venv
  pause
  exit /b 1
)

%PYTHON% run.py
if errorlevel 1 pause
