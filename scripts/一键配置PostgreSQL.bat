@echo off
:: ==================================================================
::  六子棋 Connect6 —— PostgreSQL 一键配置脚本（Windows 10 / 11）
:: ------------------------------------------------------------------
::  功能总览：
::    [1/7] 检测本机是否已安装 PostgreSQL（PATH / 安装目录 / 服务 / 注册表）
::    [2/7] 图形弹窗询问监听端口与数据库密码
::    [3/7] 检测服务状态，未运行则弹窗引导 UAC 授权并自动启动、验证结果
::    [4/7] 用 psql 验证账号密码（错误可重试 3 次）
::    [5/7] 检查并自动创建应用数据库 connect6
::    [6/7] 检查并创建战绩 / 回放数据目录，同步更新 config\database.ini
::    [7/7] 检查 PATH 环境变量，未包含 psql 目录则写入用户 PATH
::    附加：可选将服务设为开机自启
::
::  编码要求（重要）：
::    本文件必须以 GBK（ANSI）编码保存；脚本内已执行 chcp 936 与之
::    配合，中文命令行输出与弹窗均不会乱码。请勿另存为 UTF-8。
::
::  运行方式：直接双击运行。全程图形化交互，无需手动执行任何命令。
:: ==================================================================
setlocal enableextensions
chcp 936 >nul
title 六子棋 - PostgreSQL 一键配置
cd /d "%~dp0.."

:: ---------------- 全局参数（与应用 config\database.ini 保持一致） ----------------
:: PGHOST  数据库地址（应用默认本机）
:: PGUSER  数据库用户（PostgreSQL 安装时的超级用户）
:: PGDB    应用使用的库名（database.ini 中 dbname）
set "PGHOST=127.0.0.1"
set "PGUSER=postgres"
set "PGDB=connect6"
set "CFG=%~dp0..config\database.ini"

:: ---------------- 读取现有 database.ini 的端口/密码，作为弹窗预填默认值 ----------------
set "INI_PORT="
set "INI_PWD="
if exist "%CFG%" (
    for /f "usebackq tokens=1* delims==" %%a in (`findstr /i /b /c:"port " "%CFG%"`) do for /f "tokens=* delims= " %%b in ("%%a") do set "INI_PORT=%%b"
    for /f "usebackq tokens=1* delims==" %%a in (`findstr /i /b /c:"password " "%CFG%"`) do for /f "tokens=* delims= " %%b in ("%%a") do set "INI_PWD=%%b"
)
set "PORT=%INI_PORT%"
if not defined PORT set "PORT=5432"
set "PGPASS=%INI_PWD%"
if not defined PGPASS set "PGPASS=123456"

:: ==================================================================
::  [1/7] 检测是否已安装 PostgreSQL
:: ==================================================================
echo [1/7] 正在检测 PostgreSQL 是否已安装（PATH / 安装目录 / 服务 / 注册表）...

:: ---- 1a) 先看 PATH 中能否直接找到 psql.exe ----
set "PGBIN="
for /f "delims=" %%i in ('where psql 2^>nul') do if not defined PGBIN set "PGBIN=%%~dpi"

:: ---- 1b) 扫描常见安装目录（64 位 / 32 位 / 用户级安装） ----
if not defined PGBIN for /d %%d in ("%ProgramFiles%\PostgreSQL\*") do if exist "%%d\bin\psql.exe" if not defined PGBIN set "PGBIN=%%d\bin\"
if not defined PGBIN for /d %%d in ("%ProgramFiles(x86)%\PostgreSQL\*") do if exist "%%d\bin\psql.exe" if not defined PGBIN set "PGBIN=%%d\bin\"
if not defined PGBIN for /d %%d in ("%LocalAppData%\Programs\PostgreSQL\*") do if exist "%%d\bin\psql.exe" if not defined PGBIN set "PGBIN=%%d\bin\"

:: ---- 1c) 扫描 Windows 服务名（如 postgresql-x64-17） ----
set "PGSVC="
for /f "tokens=2" %%a in ('sc query state^= all 2^>nul ^| findstr /i "SERVICE_NAME"') do (
    echo %%a| findstr /i "postgres" >nul && if not defined PGSVC set "PGSVC=%%a"
)

:: ---- 1d) 注册表补充：HKLM\SOFTWARE\PostgreSQL\Installations 子键名 ----
if not defined PGSVC for /f "tokens=5 delims=\" %%a in ('reg query "HKLM\SOFTWARE\PostgreSQL\Installations" 2^>nul ^| findstr /i "Installations"') do if not "%%a"=="" set "PGSVC=%%a"

:: ---- 1e) 仍无 psql 时：从服务二进制路径反查安装目录 ----
if defined PGBIN goto detect_done
if not defined PGSVC goto detect_done
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$bp=(sc.exe qc '%PGSVC%' 2^>nul ^| Select-String 'BINARY_PATH').ToString();$m=[regex]::Match($bp,'\"([^\"]+)\"');if($m.Success){Split-Path ($m.Groups[1].Value)}"`) do if exist "%%i\psql.exe" set "PGBIN=%%i\"

:: ---- 1f) 注册表 Base Directory 兜底 ----
if defined PGBIN goto detect_done
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$k=Get-ChildItem 'HKLM:\SOFTWARE\PostgreSQL\Installations' -ErrorAction SilentlyContinue | Select-Object -First 1;if($k){$v=(Get-ItemProperty $k.PSPath).'Base Directory';if($v){Join-Path $v 'bin'}}"`) do if exist "%%i\psql.exe" set "PGBIN=%%i\"

:detect_done
if defined PGBIN if exist "%PGBIN%psql.exe" goto installed

:: ---- 未安装：弹窗给出明确指引并打开官网下载页 ----
echo     未检测到 PostgreSQL。
call :msg error "未检测到 PostgreSQL" "本机未检测到 PostgreSQL。六子棋的战绩与棋谱存档需要它。请在官网下载并安装（https://www.postgresql.org/download/windows/），安装时记住超级用户 postgres 的密码和端口（默认 5432），安装完成后重新运行本脚本即可自动完成剩余配置。"
start "" "https://www.postgresql.org/download/windows/"
exit /b 1

:installed
echo     已找到 PostgreSQL 程序目录：%PGBIN%
if defined PGSVC echo     数据库服务名：%PGSVC%

:: ==================================================================
::  [2/7] 弹窗询问监听端口与数据库密码
:: ==================================================================
echo [2/7] 请在弹窗中确认监听端口与数据库密码...
call :input "六子棋数据库配置 - 步骤 1/2" "请输入 PostgreSQL 监听端口（安装时一般为 5432）：" "%PORT%"
if defined INPUT set "PORT=%INPUT%"
call :check_num "%PORT%"
if errorlevel 1 (
    call :msg warning "端口无效" "端口必须是 1 到 65535 之间的纯数字，已回退为默认端口 5432。"
    set "PORT=5432"
)
call :input "六子棋数据库配置 - 步骤 2/2" "请输入数据库密码（用户 postgres 安装时设置的密码；输入时为明文显示，引号等特殊字符会被自动忽略）：" "%PGPASS%"
if defined INPUT set "PGPASS=%INPUT%"

:: ==================================================================
::  [3/7] 检测服务状态：未运行则引导授权并自动启动，验证启动结果
:: ==================================================================
echo [3/7] 正在检测数据库服务运行状态（端口 %PORT%）...
call :port_open %PORT%
if "%PORTOPEN%"=="1" goto port_ready

set "SVCRUN=0"
sc query "%PGSVC%" 2>nul | findstr /i "RUNNING" >nul && set "SVCRUN=1"
if "%SVCRUN%"=="0" if not defined PGSVC goto fail_no_service

if "%SVCRUN%"=="1" goto svc_running_port_closed

:: ---- 服务未运行：弹窗说明 -> UAC 授权 -> net start ----
call :ask question "需要管理员权限" "检测到 PostgreSQL 服务（%PGSVC%）未启动。点击（是）后将弹出 UAC 授权窗口，请在窗口中点击（是）以自动启动服务；点击（否）则本次配置终止。"
if not "%ASK%"=="6" goto fail_cancel_start
echo     正在请求管理员权限启动服务 %PGSVC% ...
call :uac_start_service
if errorlevel 1 goto fail_start_service
echo     启动命令已执行，等待端口就绪（最长 10 秒）...
set /a WAITN=0
:wait_port
call :port_open %PORT%
if "%PORTOPEN%"=="1" goto port_ready
set /a WAITN+=1
if %WAITN% GEQ 10 goto fail_start_no_port
ping -n 2 127.0.0.1 >nul
goto wait_port

:: ---- 服务在运行但端口未监听：引导用户输入实际端口 ----
:svc_running_port_closed
call :msg warning "端口未监听" "PostgreSQL 服务在运行，但端口 %PORT% 未监听。可能实际使用了其他端口，请在下一步输入实际端口。"
call :input "确认监听端口" "请输入 PostgreSQL 实际监听的端口（常见：5432）：" "%PORT%"
if defined INPUT set "PORT=%INPUT%"
call :port_open %PORT%
if "%PORTOPEN%"=="1" goto port_ready
goto fail_no_listener

:port_ready
echo     端口 %PORT% 监听正常。

:: ==================================================================
::  [4/7] 用 psql 验证账号密码（最多重试 3 次）
:: ==================================================================
echo [4/7] 正在验证数据库账号密码（用户 %PGUSER%）...
set "PGPASSWORD=%PGPASS%"
set /a TRYCNT=0
:verify_loop
set /a TRYCNT+=1
"%PGBIN%psql.exe" -h %PGHOST% -p %PORT% -U %PGUSER% -d postgres -tAc "SELECT 1;" >nul 2>&1
if not errorlevel 1 goto verify_ok
if %TRYCNT% GEQ 3 goto fail_bad_credentials
call :msg warning "密码验证失败（第 %TRYCNT% 次）" "无法使用当前密码连接数据库。请确认密码后重新输入（用户：%PGUSER%）。"
call :input "重新输入数据库密码" "请输入用户 %PGUSER% 的密码：" "%PGPASS%"
if not defined INPUT goto fail_bad_credentials
set "PGPASS=%INPUT%"
set "PGPASSWORD=%PGPASS%"
goto verify_loop
:verify_ok
echo     账号密码验证通过。

:: ==================================================================
::  [5/7] 检查并自动创建应用数据库 connect6
:: ==================================================================
echo [5/7] 正在检查并创建数据库 %PGDB% ...
"%PGBIN%psql.exe" -h %PGHOST% -p %PORT% -U %PGUSER% -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='%PGDB%';" 2>nul | findstr "1" >nul
if not errorlevel 1 goto db_exists
"%PGBIN%psql.exe" -h %PGHOST% -p %PORT% -U %PGUSER% -d postgres -c "CREATE DATABASE %PGDB%;" >nul 2>&1
if errorlevel 1 goto fail_create_db
echo     数据库 %PGDB% 已创建。
goto cfg_step
:db_exists
echo     数据库 %PGDB% 已存在，跳过创建。

:: ==================================================================
::  [6/7] 创建战绩 / 回放数据目录，并同步 config\database.ini
:: ==================================================================
:cfg_step
echo [6/7] 正在检查战绩 / 回放数据目录与配置文件...
set "DATADIR=%~dp0..data"
md "%DATADIR%" 2>nul
md "%DATADIR%\战绩" 2>nul
md "%DATADIR%\回放" 2>nul
md "%~dp0..config" 2>nul
if exist "%DATADIR%\战绩" goto folders_ok
:: 脚本目录只读（如放在 Program Files）时回退到「文档」目录
set "DATADIR=%USERPROFILE%\Documents\六子棋存档\data"
md "%DATADIR%\战绩" 2>nul
md "%DATADIR%\回放" 2>nul
if not exist "%DATADIR%\战绩" goto fail_dirs
:folders_ok
:: 确保 database.ini 存在（优先复制示例配置；都没有则生成最小配置）
if exist "%CFG%" goto cfg_ready
if exist "%~dp0..config.example\database.ini" copy /y "%~dp0..config.example\database.ini" "%CFG%" >nul 2>&1
:cfg_ready
if exist "%CFG%" goto cfg_update
(
echo [postgresql]
echo host = localhost
echo port = %PORT%
echo dbname = %PGDB%
echo user = %PGUSER%
echo password = %PGPASS%
echo connect_timeout = 5
) > "%CFG%"
goto cfg_done
:cfg_update
:: 用 PowerShell 按 UTF-8 读写（与程序 database.py 一致），精确替换 port / password 两行
powershell -NoProfile -Command "$f='%CFG%';$c=Get-Content -LiteralPath $f -Raw -Encoding UTF8;if($c){$c=$c -replace '(?m)^(\s*port\s*=).*$','$1 %PORT%';$c=$c -replace '(?m)^(\s*password\s*=).*$',('$1 ' + '%PGPASS%'.Replace('$','$$'));Set-Content -LiteralPath $f -Value $c -Encoding UTF8}" >nul 2>&1
:cfg_done
echo     数据目录已就绪：%DATADIR%
echo     配置文件已同步：%CFG%

:: ==================================================================
::  [7/7] 检查 PATH 环境变量：未包含 psql 目录则写入用户 PATH
:: ==================================================================
echo [7/7] 正在检查 PATH 环境变量...
where psql >nul 2>&1
if not errorlevel 1 goto path_ok
set "PATHRES=OK"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$b='%PGBIN:~0,-1%';$p=[Environment]::GetEnvironmentVariable('Path','User');if(-not $p){$p=''};if($p.ToLower().Contains($b.ToLower())){Write-Output 'OK'}else{[Environment]::SetEnvironmentVariable('Path',($p.TrimEnd(';')+';'+$b),'User');Write-Output 'ADDED'}"`) do set "PATHRES=%%i"
if "%PATHRES%"=="ADDED" call :msg information "环境变量已写入" "已将 PostgreSQL 的 bin 目录加入用户 PATH 环境变量（%PGBIN%）。已在运行的程序需重新打开后生效；六子棋不受影响。"
:path_ok
echo     PATH 环境变量检查完成。

:: ==================================================================
::  附加：可选将服务设为开机自启（推荐，免去每次手动启动）
:: ==================================================================
if not defined PGSVC goto skip_autostart
call :ask question "开机自启（可选）" "是否将 PostgreSQL 服务设置为开机自动启动（推荐，可避免每次开机后手动启动服务）？"
if not "%ASK%"=="6" goto skip_autostart
set "AUTO_RC=ERR"
net session >nul 2>&1
if not errorlevel 1 (
    sc config "%PGSVC%" start= auto >nul 2>&1
    set "AUTO_RC=0"
    goto autostart_done
)
for /f "usebackq tokens=2 delims==" %%i in (`powershell -NoProfile -Command "try{$p=Start-Process -FilePath 'sc.exe' -ArgumentList 'config','%PGSVC%','start=','auto' -Verb RunAs -Wait -PassThru;Write-Output ('RC='+$p.ExitCode)}catch{Write-Output 'RC=CANCEL'}"`) do set "AUTO_RC=%%i"
:autostart_done
if not "%AUTO_RC%"=="0" goto skip_autostart
call :msg information "设置完成" "PostgreSQL 服务已设置为开机自动启动。"
:skip_autostart

:: ==================================================================
::  全部完成
:: ==================================================================
set "PGPASSWORD="
set "PGPASS="
echo.
echo ============================================
echo   全部配置完成！PostgreSQL 已就绪：
echo   - 服务运行中（端口 %PORT%）
echo   - 数据库 %PGDB% 可用
echo   - config\database.ini 已同步更新
echo   - 数据目录：%DATADIR%
echo ============================================
call :msg information "配置完成" "PostgreSQL 配置完成：服务运行中（端口 %PORT%），数据库 %PGDB% 可用，config\database.ini 已同步更新。现在可以启动六子棋，战绩与棋谱将自动存档。"
exit /b 0

:: ==================================================================
::  失败出口：每个失败点均有明确中文提示，安全退出
:: ==================================================================
:fail_cancel_start
call :msg warning "已取消" "您取消了管理员授权，本次配置终止。可随时重新运行本脚本；也可按 Win+R 输入 services.msc，手动找到 PostgreSQL 服务并右键（启动）。"
goto fail

:fail_start_service
call :msg error "服务启动失败" "服务 %PGSVC% 启动失败或授权被取消。请打开服务管理器（Win+R 输入 services.msc）找到该服务手动启动；若仍失败，请查看 Windows 事件查看器中的错误详情。"
goto fail

:fail_start_no_port
call :msg error "启动后端口未监听" "服务已尝试启动，但端口 %PORT% 等待 10 秒后仍未监听。可能原因：安装了多个 PostgreSQL 实例、实际监听端口不同或服务启动失败。请打开服务管理器（services.msc）确认状态后重新运行本脚本。"
goto fail

:fail_no_service
call :msg error "未找到 PostgreSQL 服务" "已检测到 PostgreSQL 程序文件，但未找到对应 Windows 服务且端口未监听（可能是便携版）。请先手动启动数据库后重新运行本脚本。"
goto fail

:fail_no_listener
call :msg error "端口未监听" "PostgreSQL 服务在运行，但端口 %PORT% 始终未监听。请检查安装目录 data 文件夹下 postgresql.conf 中的 port 设置，或重新运行本脚本并输入正确端口。"
goto fail

:fail_bad_credentials
call :msg error "数据库验证失败" "连续 3 次无法使用输入的密码连接数据库。请确认用户 %PGUSER% 的密码；若忘记密码，可参考 PostgreSQL 官方文档重置密码后重试。"
goto fail

:fail_create_db
call :msg error "创建数据库失败" "无法创建数据库 %PGDB%（权限不足或其他异常）。可在 pgAdmin 或 psql 中手动执行 SQL：CREATE DATABASE %PGDB%; 然后重新运行本脚本。"
goto fail

:fail_dirs
call :msg error "创建目录失败" "无法创建战绩 / 回放数据目录（当前用户可能无写入权限）。请将本脚本复制到有写入权限的位置（如桌面）后重试。"
goto fail

:fail
echo.
echo 配置未完成，请根据弹窗提示处理后重新运行本脚本。
exit /b 1

:: ==================================================================
::  通用弹窗 / 探测子程序
:: ==================================================================

:: :msg 图形化提示框。参数：1=图标(information/warning/error/question) 2=标题 3=正文
:msg
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms;[void][System.Windows.Forms.MessageBox]::Show('%~3','%~2',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::%~1)" >nul 2>&1
exit /b 0

:: :ask 是/否询问框。参数：1=图标 2=标题 3=正文。结果：ASK=6(是)/7(否)/未定义
:ask
set "ASK="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms;[int][System.Windows.Forms.MessageBox]::Show('%~3','%~2',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::%~1)"`) do set "ASK=%%i"
exit /b 0

:: :input 单行输入框（自动剔除引号、百分号等危险字符）。
:: 参数：1=标题 2=提示语 3=默认值。结果：INPUT=用户输入（取消或清空则为未定义）
:input
set "INPUT="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Add-Type -AssemblyName Microsoft.VisualBasic;$r=[Microsoft.VisualBasic.Interaction]::InputBox('%~2','%~1','%~3');$r=([string]$r).Replace([char]39,'').Replace([char]34,'').Replace([char]37,'').Trim();if($r){Write-Output $r}"`) do set "INPUT=%%i"
exit /b 0

:: :port_open 探测本机端口是否监听。参数：1=端口。结果：PORTOPEN=1(通)/0(不通)
:port_open
set "PORTOPEN=0"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$r=$c.BeginConnect('127.0.0.1',%1,$null,$null);if($r.AsyncWaitHandle.WaitOne(800) -and $c.Connected){Write-Output 'OPEN'};$c.Close()}catch{}"`) do if "%%i"=="OPEN" set "PORTOPEN=1"
exit /b 0

:: :check_num 校验正整数（1~65535）。参数：1=待校验值。结果：errorlevel 0=有效 1=无效
:check_num
set "NUM_OK=1"
echo %~1| findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 set "NUM_OK=0"
if "%NUM_OK%"=="1" if %~1 GTR 65535 set "NUM_OK=0"
if "%NUM_OK%"=="0" exit /b 1
exit /b 0

:: :uac_start_service 弹 UAC 提权启动服务。结果：errorlevel 0=成功或已在运行
:uac_start_service
set "UAC_RC=ERR"
for /f "usebackq tokens=2 delims==" %%i in (`powershell -NoProfile -Command "try{$p=Start-Process -FilePath 'net.exe' -ArgumentList 'start','%PGSVC%' -Verb RunAs -Wait -PassThru;Write-Output ('RC='+$p.ExitCode)}catch{Write-Output 'RC=CANCEL'}"`) do set "UAC_RC=%%i"
if "%UAC_RC%"=="0" exit /b 0
if "%UAC_RC%"=="2" exit /b 0
exit /b 1
