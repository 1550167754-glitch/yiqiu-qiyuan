@echo off
rem 六子棋 Connect6 —— 一键搭建开发环境（创建 venv + 安装依赖，无需管理员）
chcp 65001 >nul
cd /d "%~dp0"
set BASE=C:\Users\ASUS\.workbuddy\venvs\liuziqi
set PY=C:\Users\ASUS\.workbuddy\binaries\python\versions\3.13.12\python.exe

if not exist "%PY%" set PY=python

echo [1/3] 创建虚拟环境...
if not exist "%BASE%\Scripts\python.exe" (
  "%PY%" -m venv "%BASE%"
)

echo [2/3] 安装依赖...
"%BASE%\Scripts\python.exe" -m pip install --upgrade pip >nul
"%BASE%\Scripts\python.exe" -m pip install psycopg[binary] soundfile numpy pyinstaller

echo [3/3] 完成。可用 启动六子棋.bat 源码运行，或用 build_exe.bat 打包。
pause
