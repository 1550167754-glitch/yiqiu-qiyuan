@echo off
rem ============================================================
rem  本地预览网页版.cmd —— 启一个本地小服务器并自动打开浏览器
rem
rem  双击即可；只用系统里的 node，不联网、不装任何东西。
rem  为什么不直接双击 index.html：浏览器对 file:// 下的脚本有额外限制，
rem  用 http:// 打开最稳（本地服务器就是为此存在的）。
rem ============================================================
chcp 936 >nul
title 弈趣棋苑 网页版 · 本地预览
cd /d "%~dp0"

rem 某些 Electron/IDE 环境会残留这个变量，会让 node 行为异常，先清掉
set "ELECTRON_RUN_AS_NODE="

where node >nul 2>&1
if errorlevel 1 (
  echo [错误] 没找到 node。
  echo         替代办法：把 index.html 直接拖进浏览器（基本功能可用）。
  pause
  exit /b 1
)

if not exist "web\index.html" (
  echo [错误] 找不到 web\index.html，请确认在项目根目录运行本脚本。
  pause
  exit /b 1
)

echo 正在启动本地预览（浏览器会自动打开）...
echo 关闭这个黑窗口即可停止服务。
echo.
node "web\serve.js" %1
pause
exit /b 0
