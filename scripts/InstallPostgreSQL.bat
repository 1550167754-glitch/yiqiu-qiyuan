@echo off
chcp 65001 >nul
title 安装 PostgreSQL（六子棋存档所需）
echo ============================================
echo   六子棋 Connect6 需要 PostgreSQL 数据库
echo   请从官网下载安装包并完成安装
echo   官网: https://www.postgresql.org/download/windows/
echo ============================================
echo.
echo 安装完成后，请将 config/database.ini 中的连接信息
echo 改为你的实际数据库配置，然后重启本程序。
echo.
start https://www.postgresql.org/download/windows/
pause
