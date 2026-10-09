@echo off
rem ============================================================
rem  一键修复PostgreSQL.cmd  (弈趣棋苑 · 数据库修复/初始化)
rem
rem  做四件事（全部在本机完成，不联网）：
rem    1. 重新设置 postgres 账号的密码，并写出 config\database.ini
rem    2. 建好存放战绩的数据库 connect6
rem    3. 自动建表 players / games / moves
rem    4. 用程序真正连一次，确认能连上、能写进数据
rem
rem  需要管理员权限（改 PostgreSQL 认证配置 + 重载配置）。
rem  双击后会自动弹 UAC；也可以右键「以管理员身份运行」。
rem ============================================================
chcp 936 >nul
title 一键修复 PostgreSQL（弈趣棋苑）
cd /d "%~dp0"

rem 若从某些 Electron/IDE 环境启动，环境里可能残留 ELECTRON_RUN_AS_NODE=1，
rem 会让 powershell.exe 被当成 Node 执行（表现为秒退、什么都不做），这里清掉。
set "ELECTRON_RUN_AS_NODE="

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 正在请求管理员权限...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

if not exist "%~dp0_修复PostgreSQL.ps1" (
  echo [错误] 缺少同目录下的 _修复PostgreSQL.ps1，请确认两个文件在一起。
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_修复PostgreSQL.ps1"
set "RC=%errorlevel%"
echo.
echo ============================================================
if "%RC%"=="0" (echo  完成：数据库已就绪，可以启动程序对局了。) else (echo  未完成，请看上面的提示。)
echo ============================================================
echo.
pause
exit /b %RC%
