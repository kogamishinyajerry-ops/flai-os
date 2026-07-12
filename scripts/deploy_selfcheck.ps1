# 部署自检门（M11-C2）：包装 deploy_selfcheck.py。内网 Windows 部署用，与同名 .sh 行为一致。
# $ErrorActionPreference=Stop + try/catch（Codex 审 P2）：python 不在 PATH 时
# CommandNotFoundException 默认不终止脚本、$LASTEXITCODE 残留 null/旧值，
# `exit $null`=0——自检门一项没跑却报成功（fail-open 大忌）。启动失败必须非零退出。
$ErrorActionPreference = "Stop"
try {
    Set-Location (Join-Path $PSScriptRoot "..")
    python scripts/deploy_selfcheck.py @args
    if ($null -eq $LASTEXITCODE) { exit 1 }
    exit $LASTEXITCODE
} catch {
    Write-Host "deploy_selfcheck 启动失败（python 不可用？）：$($_.Exception.Message)"
    exit 1
}
