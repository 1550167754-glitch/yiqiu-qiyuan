@echo off
rem 六子棋 Connect6 —— 源码运行脚本（使用 venv）
chcp 65001 >nul
cd /d "%~dp0"
set PYTHON="C:\Users\ASUS\.workbuddy\venvs\liuziqi\Scripts\python.exe"
if not exist %PYTHON% (
  echo [错误] 未找到 venv：%PYTHON%
  echo 请先执行 setup_dev.bat 创建虚拟环境并安装依赖。
  pause
  exit /b 1
)
%PYTHON% run.py
if errorlevel 1 pause
