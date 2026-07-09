# 启动 Vue 前端 dev server（M2 实现）。与同名 .sh 行为一致。
# 端口 8621，/api 代理到后端 127.0.0.1:8620（见 frontend/vite.config.js）。
# DECLARED-NOT-VERIFIED：本脚本在 macOS 开发机上无法实测，Windows 内网首跑时验证。
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "node_modules 缺失：先执行  cd frontend; npm install"
    exit 1
}

npm run dev
