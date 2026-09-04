@echo off
rem 六子棋 Connect6 —— PyInstaller 打包脚本
rem 说明：本脚本把 源码 + 全部资源（fonts/sounds/music/icon）通过
rem       --add-data 打进 exe，产物 dist\六子棋\ 完全自包含、不丢失任何资源。
rem       打包完成后 assets\music（无损 Hi-Fi 音乐）也包含在内。
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\ASUS\.workbuddy\venvs\liuziqi\Scripts\python.exe
if not exist %PY% (
  echo [错误] 未找到 venv，请先运行 setup_dev.bat
  pause
  exit /b 1
)

echo [1/4] 清理旧构建...
if exist build rmdir /s /q build
if exist dist\六子棋 rmdir /s /q dist\六子棋
if exist run.spec del /q run.spec

echo [2/4] PyInstaller 打包（内嵌全部资源，含无损音乐，耗时较长）...
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
  --add-data "config;config" ^
  --hidden-import psycopg ^
  --exclude-module matplotlib ^
  --exclude-module PIL ^
  run.py

echo [3/4] 拷贝资源到 exe 同目录（供用户自定义音乐/音量配置用，与内建互补）...
if not exist "dist\六子棋\assets" xcopy /e /i /y "assets" "dist\六子棋\assets" >nul
if not exist "dist\六子棋\config" xcopy /e /i /y "config" "dist\六子棋\config" >nul

echo [4/4] 打包完成。产物：dist\六子棋\六子棋.exe（自包含全部资源）
pause
