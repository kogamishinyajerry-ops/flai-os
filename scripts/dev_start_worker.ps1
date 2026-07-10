# 启动 Job Runner 轮询进程 —— M1 实现（见 docs/01_Overall_Architecture.md 里程碑表）。
# 内网 Windows 用，本机未测 = DECLARED-NOT-VERIFIED（与同名 .sh 保持行为一致）。
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "启动 FLAi-OS Job Runner：python -m backend.app.jobs.runner"
Write-Host "依赖缺失？先装：pip install fastapi jsonschema pyyaml httpx openpyxl jieba 'pydantic>2'"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run --no-project `
        --with fastapi --with jsonschema --with pyyaml --with httpx --with openpyxl --with jieba --with "pydantic>2" `
        -- python -m backend.app.jobs.runner
} else {
    python -m backend.app.jobs.runner
}
