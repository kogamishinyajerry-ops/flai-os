# 一键执行前端构建、后端全量测试与五组浏览器验收；任一步失败立即汇总退出。
# DECLARED-NOT-VERIFIED：本脚本在 macOS 开发机上无法实测，Windows 内网首跑时验证。
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$script:CompletedSteps = @()
$script:FailedSteps = @()

function Show-Summary {
    Write-Host ""
    Write-Host "验证步骤汇总："
    if ($script:CompletedSteps.Count -eq 0) {
        Write-Host "- [完成] （无）"
    } else {
        foreach ($Step in $script:CompletedSteps) {
            Write-Host "- [完成] $Step"
        }
    }
    if ($script:FailedSteps.Count -eq 0) {
        Write-Host "- [失败] （无）"
    } else {
        foreach ($Step in $script:FailedSteps) {
            Write-Host "- [失败] $Step"
        }
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    Write-Host ""
    Write-Host "开始：$Name"
    $global:LASTEXITCODE = 0
    try {
        & $Action
        $ExitCode = $LASTEXITCODE
    } catch {
        $ExitCode = if ($LASTEXITCODE -ne 0) { $LASTEXITCODE } else { 1 }
        $script:FailedSteps += "$Name（退出码 $ExitCode；$($_.Exception.Message)）"
        Show-Summary
        exit $ExitCode
    }

    if ($ExitCode -ne 0) {
        $script:FailedSteps += "$Name（退出码 $ExitCode）"
        Show-Summary
        exit $ExitCode
    }

    $script:CompletedSteps += $Name
    Write-Host "完成：$Name"
}

Invoke-Step -Name "① frontend npm run build" -Action {
    Push-Location "frontend"
    try {
        npm run build
    } finally {
        Pop-Location
    }
}

# 不限定路径：跑满 pyproject testpaths（tests/ + tools_impl/ + backend/tests），
# 与 verify_all.sh 保持逐字对齐（Codex 互审 P2）。
Invoke-Step -Name "② 全量 pytest -n auto（三个 testpaths）" -Action {
    uv run --no-project `
        --with pytest --with pytest-xdist --with jsonschema --with pyyaml `
        --with fastapi --with httpx --with python-multipart --with "pydantic>2" `
        --with jieba --with openpyxl `
        python -m pytest -q -n auto
}

$E2EScripts = @(
    "frontend/e2e/m2_acceptance.py",
    "frontend/e2e/m6_guide_acceptance.py",
    "frontend/e2e/m8_collab_chain_acceptance.py",
    "frontend/e2e/m8_guide_orchestrator_acceptance.py",
    "frontend/e2e/m8_workbench_acceptance.py",
    "frontend/e2e/batch_c_rewards_acceptance.py",
    "frontend/e2e/batch_d_visual_acceptance.py"
)

foreach ($E2EScript in $E2EScripts) {
    Invoke-Step -Name "③ E2E $E2EScript" -Action {
        uv run --no-project `
            --with playwright --with uvicorn --with pytest --with pytest-xdist `
            --with jsonschema --with pyyaml --with fastapi --with httpx `
            --with python-multipart --with "pydantic>2" --with jieba --with openpyxl `
            python $E2EScript
    }
}

Show-Summary
