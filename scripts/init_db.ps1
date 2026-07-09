# 初始化 SQLite 数据库表 —— M1 实现（见 docs/01_Overall_Architecture.md 里程碑表）。
# 内网 Windows 用，本机未测 = DECLARED-NOT-VERIFIED（与同名 .sh 保持行为一致）。
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "初始化 FLAi-OS SQLite 数据库（幂等，可重复执行）..."

$PyCmd = @"
from backend.app import config
from backend.app.storage.db import init_db
config.ensure_dirs()
init_db(config.DB_PATH)
print(f"已初始化：{config.DB_PATH}")
"@

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run --no-project --with jsonschema --with pyyaml -- python -c $PyCmd
} else {
    python -c $PyCmd
}
