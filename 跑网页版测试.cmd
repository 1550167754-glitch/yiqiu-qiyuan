@echo off
rem ============================================================
rem  跑网页版测试.cmd —— 一条命令跑完网页版的全部回归
rem
rem  双击即可；只用系统里的 node。
rem  1) 重新打包引擎  2) 引擎逻辑回归  3) 胜负判定穷举对拍  4) 假DOM跑 app.js
rem ============================================================
chcp 936 >nul
title 弈趣棋苑 网页版 · 回归测试
cd /d "%~dp0"

set "ELECTRON_RUN_AS_NODE="

where node >nul 2>&1
if errorlevel 1 (
  echo [错误] 没找到 node。
  pause
  exit /b 1
)

set "FAILED=0"

echo ============================================================
echo [1/7] 重新打包引擎
echo ============================================================
node "web\build.js"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
echo [2/7] 引擎逻辑回归（board / game / ai）
echo ============================================================
node "web\tests\run.js"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
echo [3/7] 胜负判定穷举对拍（59 万组合）
echo ============================================================
node "web\tests\wincheck.js"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
echo [4/7] 中国象棋：攻击检测对拍 + 规则
echo ============================================================
node "web\tests\xqcheck.js"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
echo [5/7] 中国象棋：棋力抽检（杀棋/吃子/应将/搜索深度）
echo ============================================================
node "web\tests\xqstrength.js"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
echo [6/7] 假 DOM 真跑 app.js（三种棋的交互链路）
echo ============================================================
node "web\tests\apptest.js"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
echo [7/7] 跨语言对拍：桌面版(Python) 与 网页版(JS) 规则逐项比对
echo ============================================================
set "PYPATH=%USERPROFILE%\.workbuddy\venvs\liuziqi\Scripts\python.exe"
if not exist "%PYPATH%" set "PYPATH=python"
"%PYPATH%" "web\tests\parity.py"
if errorlevel 1 set "FAILED=1"

echo.
echo ============================================================
if "%FAILED%"=="0" (echo  全部测试通过) else (echo  有测试未通过，请看上面的 FAIL 行)
echo ============================================================
pause
exit /b %FAILED%
