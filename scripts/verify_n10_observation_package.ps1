# N10 申报观察记录完整性检查；与同名 .sh 参数/退出码一致。
# PowerShell 启动失败或 Python 未返回退出码时一律非零，避免 gate 假绿。
$ErrorActionPreference = "Stop"
try {
    Set-Location (Join-Path $PSScriptRoot "..")
    python scripts/verify_n10_observation_package.py @args
    if ($null -eq $LASTEXITCODE) { exit 1 }
    exit $LASTEXITCODE
} catch {
    Write-Host "verify_n10_observation_package 启动失败（python 不可用？）：$($_.Exception.Message)"
    exit 1
}
