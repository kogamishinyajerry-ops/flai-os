# 启动 FastAPI 后端(uvicorn backend.app.main) —— M1 实现（见 docs/01_Overall_Architecture.md 里程碑表）。
# 内网 Windows 用，本机未测 = DECLARED-NOT-VERIFIED（与同名 .sh 保持行为一致）。
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$Port = if ($env:FLAI_BACKEND_PORT) { $env:FLAI_BACKEND_PORT } else { "8620" }

Write-Host "启动 FLAi-OS 后端：uvicorn backend.app.main:app --port $Port"
Write-Host "依赖缺失？先装：pip install fastapi uvicorn jsonschema pyyaml python-multipart httpx 'pydantic>2'"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run --no-project `
        --with fastapi --with uvicorn --with jsonschema --with pyyaml `
        --with python-multipart --with httpx --with "pydantic>2" `
        -- python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $Port
} else {
    python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $Port
}
