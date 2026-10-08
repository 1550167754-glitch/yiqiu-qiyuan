@echo off
rem 弈趣棋苑 Connect6 桌面应用 PyInstaller 打包脚本
rem 说明：打包源码 + 全部资源（fonts/sounds/music/icon），通过 --add-data 把资源
rem       一并打入 dist\六子棋\，保证运行时缺失任何资源时仍有兜底。
rem       打包完成后 assets\music 已是 Hi-Fi 无损，无需再次打包。
chcp 65001 >nul
cd /d "%~dp0.."

rem ---- 解析 python 解释器：优先用工程 venv，否则回退 PATH 上的 python ----
set "PY="
if exist "C:\Users\ASUS\.workbuddy\venvs\liuziqi\Scripts\python.exe" (
  set "PY=C:\Users\ASUS\.workbuddy\venvs\liuziqi\Scripts\python.exe"
) else (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] 未找到 python，请先运行 setup_dev.bat 创建 venv
  pause
  exit /b 1
)

echo [1/4] 清理旧构建...
if exist build rmdir /s /q build
if exist dist\六子棋 rmdir /s /q dist\六子棋
if exist run.spec del /q run.spec

echo [2/4] PyInstaller 打包（内嵌全部资源；临时忽略构建日志，打包后弹出）...
%PY% -m PyInstaller --noconfirm --clean ^
  --name "六子棋" ^
  --windowed ^
  --onedir ^
  --icon "assets\icon.ico" ^
  --paths "src" ^
  --add-data "src\liuziqi;src\liuziqi" ^
  --add-data "assets\fonts;assets\fonts" ^
  --add-data "assets\sounds;assets\sounds" ^
  --add-data "assets\music;assets\music" ^
  --add-data "assets\icon.ico;assets" ^
  --add-data "assets\icon64.png;assets" ^
  --add-data "assets\logo.png;assets" ^
  --add-data "config.example;config" ^
  --hidden-import psycopg ^
  --exclude-module matplotlib ^
  run.py

echo [3/4] 把资源同步到 exe 同目录（用户可随时修改/替换资源，不依赖重新打包）...
if not exist "dist\六子棋\assets" xcopy /e /i /y "assets" "dist\六子棋\assets" >nul
if not exist "dist\六子棋\config" xcopy /e /i /y "config.example" "dist\六子棋\config" >nul

echo [4/4] 完成！产物：dist\六子棋\六子棋.exe（已内嵌全部资源）
pause
