# M4 排期信号包机械 gate；与同名 .sh 参数/退出码一致。
# PowerShell 启动失败或 Python 未返回退出码时一律非零，避免 gate 假绿。
$ErrorActionPreference = "Stop"
try {
    Set-Location (Join-Path $PSScriptRoot "..")
    python scripts/verify_m4_signal_package.py @args
    if ($null -eq $LASTEXITCODE) { exit 1 }
    exit $LASTEXITCODE
} catch {
    Write-Host "verify_m4_signal_package 启动失败（python 不可用？）：$($_.Exception.Message)"
    exit 1
}
