# ============================================================
#  _修复PostgreSQL.ps1 —— 由「一键修复PostgreSQL.cmd」以管理员身份调用
#
#  为什么需要它：本机 PostgreSQL 的 postmaster 以 NT AUTHORITY\NetworkService
#  运行，普通权限进程改不了 pg_hba.conf 也发不了 reload 信号，所以必须以
#  管理员身份执行。这个脚本做完整闭环，最后用程序自己的连接代码复验一遍。
#
#  本脚本不联网、不删除任何数据；只可能新建数据库 connect6 与三张表。
# ============================================================
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$CfgPath  = Join-Path $Root 'config\database.ini'
$CfgExample = Join-Path $Root 'config.example\database.ini'
$TestPy   = Join-Path $Root 'scripts\测试数据库连接.py'

# ---- 定位 PostgreSQL ----
$PgBin = $null
foreach ($v in @('18','17','16','15','14')) {
  $p = "C:\Program Files\PostgreSQL\$v\bin"
  if (Test-Path (Join-Path $p 'psql.exe')) { $PgBin = $p; $PgVer = $v; break }
}
if (-not $PgBin) {
  Write-Host "[错误] 没找到 PostgreSQL 安装目录（C:\Program Files\PostgreSQL\<版本>\bin）。" -ForegroundColor Red
  Write-Host "       若尚未安装，请先安装 PostgreSQL 后重试。"
  exit 1
}
$Psql = Join-Path $PgBin 'psql.exe'
$PgCtl = Join-Path $PgBin 'pg_ctl.exe'
Write-Host "PostgreSQL : $PgBin" -ForegroundColor Cyan

# ---- 数据目录（从服务注册表/命令行取，取不到再猜） ----
$DataDir = $null
try {
  $svc = Get-CimInstance Win32_Service -Filter "Name LIKE 'postgresql%'" -ErrorAction SilentlyContinue |
         Select-Object -First 1
  if ($svc) {
    $svcName = $svc.Name
    if ($svc.PathName -match '-D\s+"?([^"]+?)"?\s*$') { $DataDir = $Matches[1] }
  }
} catch {}
if (-not $DataDir) {
  foreach ($d in @("D:\PostgreData", "C:\Program Files\PostgreSQL\$PgVer\data")) {
    if (Test-Path (Join-Path $d 'pg_hba.conf')) { $DataDir = $d; break }
  }
}
if (-not $DataDir) {
  Write-Host "[错误] 找不到 PostgreSQL 数据目录（pg_hba.conf 所在处）。" -ForegroundColor Red
  exit 1
}
$Hba = Join-Path $DataDir 'pg_hba.conf'
Write-Host "服务名     : $svcName"
Write-Host "数据目录   : $DataDir"

# ---- 确保服务在运行 ----
$running = $false
try {
  $r = New-Object Net.Sockets.TcpClient
  $r.Connect('127.0.0.1', 5432); $running = $true; $r.Close()
} catch { $running = $false }
if (-not $running) {
  Write-Host "服务未运行，正在启动 $svcName ..." -ForegroundColor Yellow
  Start-Service $svcName -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
}

# ---- 读程序配置（与程序同一套解析规则：UTF-8 无 BOM + [postgres]） ----
function Read-Cfg([string]$path) {
  $t = @{}
  $t.Host = 'localhost'; $t.Port = '5432'; $t.Db = 'connect6'
  $t.User = 'postgres'; $t.Pass = ''; $t.Path = $path; $t.Ok = $false
  if (-not (Test-Path $path)) { return $t }
  $lines = Get-Content -LiteralPath $path -Encoding UTF8
  $sec = ''
  foreach ($ln in $lines) {
    $s = $ln.Trim()
    if ($s -eq '' -or $s.StartsWith(';') -or $s.StartsWith('#')) { continue }
    if ($s -match '^\[(.+)\]$') { $sec = $Matches[1].Trim().ToLower(); continue }
    if ($sec -and $sec -notin @('postgres','postgresql','pgsql','postgres_db')) { continue }
    if ($s -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
      $k = $Matches[1].ToLower(); $v = $Matches[2].Trim().Trim('"')
      switch ($k) {
        'host'            { if ($v) { $t.Host = $v } }
        'port'            { if ($v) { $t.Port = $v } }
        'dbname'          { if ($v) { $t.Db = $v } }
        'database'        { if ($v) { $t.Db = $v } }
        'user'            { if ($v) { $t.User = $v } }
        'username'        { if ($v) { $t.User = $v } }
        'password'        { $t.Pass = $v }
      }
    }
  }
  $t.Ok = $true
  return $t
}

function Try-Connect([string]$usr, [string]$pwd, [string]$db) {
  $old = $env:PGPASSWORD
  $env:PGPASSWORD = $pwd
  try {
    $out = & $Psql -h 127.0.0.1 -p 5432 -U $usr -d $db -tAc 'select 1' 2>&1
    return ($LASTEXITCODE -eq 0)
  } finally { $env:PGPASSWORD = $old }
}

function Invoke-Sql([string[]]$sqls, [string]$usr, [string]$pwd, [string]$db) {
  $old = $env:PGPASSWORD
  $env:PGPASSWORD = $pwd
  try {
    foreach ($s in $sqls) {
      & $Psql -h 127.0.0.1 -p 5432 -U $usr -d $db -v ON_ERROR_STOP=1 -c $s | Out-Null
      if ($LASTEXITCODE -ne 0) { throw "SQL 执行失败（退出码 $LASTEXITCODE）：$s" }
    }
  } finally { $env:PGPASSWORD = $old }
}

function Write-CfgFile([string]$user, [string]$pass) {
  $tpl = @"
; ============================================================
; 弈趣棋苑 —— PostgreSQL 数据库连接配置（由 一键修复PostgreSQL.cmd 生成）
;
; 本文件必须存为 UTF-8 无 BOM：BOM 会让 configparser 解析失败，
; 数据库功能会静默失效（本项目踩过这个坑）。
; ============================================================
[postgres]
host = localhost
port = 5432
dbname = connect6
user = $user
password = $pass
connect_timeout = 5
"@
  $cfgDir = Split-Path -Parent $CfgPath
  if (-not (Test-Path $cfgDir)) { New-Item -ItemType Directory -Path $cfgDir | Out-Null }
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($CfgPath, $tpl, $utf8NoBom)
}

# ============================================================
Write-Host ''
Write-Host '===== [1/6] 读取现有配置并试连 =====' -ForegroundColor Cyan
$cfg = Read-Cfg $CfgPath
Write-Host ("配置：{0}@{1}:{2}/{3}" -f $cfg.User, $cfg.Host, $cfg.Port, $cfg.Db)

$alreadyOk = $false
if ($cfg.Pass) {
  $alreadyOk = Try-Connect $cfg.User $cfg.Pass $cfg.Db
  if (-not $alreadyOk) { $alreadyOk = Try-Connect $cfg.User $cfg.Pass 'postgres' }
}
if ($alreadyOk) {
  Write-Host "  √ 现有配置可以连上，无需改密码。" -ForegroundColor Green
  $AppUser = $cfg.User; $AppPass = $cfg.Pass; $AppDb = $cfg.Db
  $needTrust = $false
} else {
  Write-Host "  × 现有配置连不上（原因：密码不对 / 角色已改名 / 库不存在 / 密码为空）" -ForegroundColor Yellow
  $needTrust = $true
}

# ============================================================
if ($needTrust) {
  Write-Host ''
  Write-Host '===== [2/6] 临时开启本机免密认证（只在回环地址，立即还原） =====' -ForegroundColor Cyan
  $bak = "$Hba.dsh-bak"
  Copy-Item -LiteralPath $Hba -Destination $bak -Force
  Write-Host "  已备份 pg_hba.conf -> $bak"
  $orig = Get-Content -LiteralPath $Hba
  $new = $orig | ForEach-Object {
    $_ -replace '^(local\s+all\s+all\s+)scram-sha-256\s*$', '${1}trust' `
       -replace '^(host\s+all\s+all\s+127\.0\.0\.1/32\s+)scram-sha-256\s*$', '${1}trust' `
       -replace '^(host\s+all\s+all\s+::1/128\s+)scram-sha-256\s*$', '${1}trust'
  }
  $ascii = New-Object System.Text.ASCIIEncoding
  [System.IO.File]::WriteAllLines($Hba, $new, $ascii)
  & $PgCtl reload -D $DataDir | Out-Null
  Start-Sleep -Seconds 2

  $ok = Try-Connect 'postgres' '' 'postgres'
  if (-not $ok) { $ok = Try-Connect 'tangzijie' '' 'postgres' }
  if (-not $ok) { $ok = Try-Connect 'postgres' '' 'template1' }
  if (-not $ok) {
    Copy-Item -LiteralPath $bak -Destination $Hba -Force
    & $PgCtl reload -D $DataDir | Out-Null
    Write-Host "  [错误] 临时免密后仍连不上，可能是 host 配置不是 127.0.0.1/::1，已还原 pg_hba.conf。" -ForegroundColor Red
    Write-Host "         请检查 $Hba"
    exit 1
  }
  Write-Host "  √ 已取得超级用户连接（不显示密码）" -ForegroundColor Green

  # ---- 取"操作角色"名 ----
  $super = & $Psql -h 127.0.0.1 -p 5432 -U 'postgres' -d 'postgres' -tAc `
           "select rolname from pg_roles where rolsuper order by rolname limit 1" 2>$null
  if (-not $super) { $super = 'tangzijie' }
  $super = ($super | Select-Object -First 1).Trim()
  Write-Host "  超级用户角色：$super"

  Write-Host ''
  Write-Host '===== [3/6] 设置新密码 =====' -ForegroundColor Cyan
  Write-Host '  请为 postgres 账号设置一个新密码（输入时不显示，留空则不改密码只做修复）。'
  $pwdInput = Read-Host -AsSecureString '  新密码'
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
             [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwdInput))
  if ([string]::IsNullOrWhiteSpace($plain)) {
    Write-Host '  （留空：跳过改密码，后面仍会建库/建表，但 config 里的密码需要你手填）' -ForegroundColor Yellow
  } else {
    if ($plain.Length -lt 4) {
      Write-Host '  [错误] 密码太短（至少 4 位）。' -ForegroundColor Red
      Copy-Item -LiteralPath $bak -Destination $Hba -Force
      & $PgCtl reload -D $DataDir | Out-Null
      exit 1
    }
    $esc = $plain.Replace("'", "''")
    # 历史遗留：本机曾把 postgres 改名为 tangzijie，两个角色名都兜住
    $sql = @(
      "DO `$`$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='postgres') THEN ALTER ROLE postgres WITH LOGIN SUPERUSER PASSWORD '$esc'; END IF; END `$`$;",
      "DO `$`$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='tangzijie') THEN ALTER ROLE tangzijie WITH LOGIN SUPERUSER PASSWORD '$esc'; END IF; END `$`$;"
    )
    Invoke-Sql $sql $super '' 'postgres'
    Write-Host '  √ 密码已更新' -ForegroundColor Green
  }

  # ---- 找出程序该用的角色名 ----
  Write-Host ''
  Write-Host '===== [4/6] 确定程序使用的账号 =====' -ForegroundColor Cyan
  $names = & $Psql -h 127.0.0.1 -p 5432 -U $super -d 'postgres' -tAc `
           "select rolname from pg_roles where rolcanlogin order by rolname" 2>$null
  $names = @($names | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  Write-Host ("  可登录角色：{0}" -f ($names -join ', '))
  $cand = @('postgres', 'tangzijie') | Where-Object { $names -contains $_ }
  if (-not $cand) { $cand = @($names[0]) }
  Write-Host ("  程序将使用：{0}" -f $cand[0])
  $AppUser = $cand[0]
  if ($plain) { $AppPass = $plain } else { $AppPass = $cfg.Pass }

  Write-Host ''
  Write-Host '===== [5/6] 建库 + 建表 =====' -ForegroundColor Cyan
  $AppDb = 'connect6'
  $exists = & $Psql -h 127.0.0.1 -p 5432 -U $super -d 'postgres' -tAc `
            "select 1 from pg_database where datname='connect6'" 2>$null
  if (-not ($exists -match '1')) {
    Invoke-Sql @('CREATE DATABASE connect6 ENCODING ''UTF8'' TEMPLATE template0;') $super '' 'postgres'
    Write-Host '  √ 已创建数据库 connect6' -ForegroundColor Green
  } else {
    Write-Host '  √ 数据库 connect6 已存在'
  }
  Invoke-Sql @(@'
CREATE TABLE IF NOT EXISTS players (
    id      SERIAL PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL,
    kind    TEXT NOT NULL DEFAULT 'human',
    wins    INT NOT NULL DEFAULT 0,
    losses  INT NOT NULL DEFAULT 0,
    draws   INT NOT NULL DEFAULT 0
);
'@, @'
CREATE TABLE IF NOT EXISTS games (
    id          SERIAL PRIMARY KEY,
    black_name  TEXT NOT NULL,
    black_kind  TEXT NOT NULL DEFAULT 'human',
    white_name  TEXT NOT NULL,
    white_kind  TEXT NOT NULL DEFAULT 'human',
    result      TEXT NOT NULL,
    reason      TEXT,
    move_count  INT NOT NULL DEFAULT 0,
    record      JSONB,
    started_at  TIMESTAMPTZ DEFAULT now(),
    ended_at    TIMESTAMPTZ DEFAULT now()
);
'@, @'
CREATE TABLE IF NOT EXISTS moves (
    id      SERIAL PRIMARY KEY,
    game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seq     INT NOT NULL,
    color   INT NOT NULL,
    x       INT NOT NULL,
    y       INT NOT NULL
);
'@) $super '' $AppDb
  # 表属主交给程序账号，避免以后权限问题
  Invoke-Sql @("ALTER DATABASE connect6 OWNER TO `"$AppUser`";",
               "GRANT ALL ON SCHEMA public TO `"$AppUser`";",
               "ALTER TABLE players OWNER TO `"$AppUser`";",
               "ALTER TABLE games OWNER TO `"$AppUser`";",
               "ALTER TABLE moves OWNER TO `"$AppUser`";") $super '' $AppDb
  Write-Host '  √ 表 players / games / moves 已就绪' -ForegroundColor Green

  # ---- 还原认证配置 ----
  Write-Host ''
  Write-Host '  还原 pg_hba.conf 并重载...'
  Copy-Item -LiteralPath $bak -Destination $Hba -Force
  & $PgCtl reload -D $DataDir | Out-Null
  Start-Sleep -Seconds 2
  Write-Host '  √ 认证配置已还原为 scram-sha-256' -ForegroundColor Green
} else {
  Write-Host ''
  Write-Host '===== [2-5/6] 现有配置可用，跳过改密/建库，仅确认表结构 =====' -ForegroundColor Cyan
  $AppUser = $cfg.User; $AppPass = $cfg.Pass; $AppDb = $cfg.Db
  Invoke-Sql @(@'
CREATE TABLE IF NOT EXISTS players (
    id      SERIAL PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL,
    kind    TEXT NOT NULL DEFAULT 'human',
    wins    INT NOT NULL DEFAULT 0,
    losses  INT NOT NULL DEFAULT 0,
    draws   INT NOT NULL DEFAULT 0
);
'@, @'
CREATE TABLE IF NOT EXISTS games (
    id          SERIAL PRIMARY KEY,
    black_name  TEXT NOT NULL,
    black_kind  TEXT NOT NULL DEFAULT 'human',
    white_name  TEXT NOT NULL,
    white_kind  TEXT NOT NULL DEFAULT 'human',
    result      TEXT NOT NULL,
    reason      TEXT,
    move_count  INT NOT NULL DEFAULT 0,
    record      JSONB,
    started_at  TIMESTAMPTZ DEFAULT now(),
    ended_at    TIMESTAMPTZ DEFAULT now()
);
'@, @'
CREATE TABLE IF NOT EXISTS moves (
    id      SERIAL PRIMARY KEY,
    game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seq     INT NOT NULL,
    color   INT NOT NULL,
    x       INT NOT NULL,
    y       INT NOT NULL
);
'@) $AppUser $AppPass $AppDb
  Write-Host '  √ 表结构已确认' -ForegroundColor Green
}

# ---- 写回程序配置（UTF-8 无 BOM） ----
if ($needTrust) {
  Write-CfgFile $AppUser $AppPass
  Write-Host "  √ 已写入 $CfgPath（user=$AppUser, db=connect6）" -ForegroundColor Green
}

# ============================================================
Write-Host ''
Write-Host '===== [6/6] 用程序自己的代码复验（连接 + 建表 + 读写） =====' -ForegroundColor Cyan
$Py = Join-Path $env:USERPROFILE '.workbuddy\venvs\liuziqi\Scripts\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }
if (Test-Path $TestPy) {
  & $Py $TestPy
  $rc = $LASTEXITCODE
  if ($rc -ne 0) {
    Write-Host "[提示] 程序侧复验未通过（退出码 $rc），请把上面的『原因/建议』对照检查。" -ForegroundColor Yellow
    exit $rc
  }
} else {
  Write-Host "  （未找到 $TestPy，跳过程序侧复验）" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '完成：数据库已可用于存档与战绩查询。' -ForegroundColor Green
exit 0
