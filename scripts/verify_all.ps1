# 一键执行前端构建、后端全量测试、前端纯函数核与 22 套浏览器验收；任一步失败立即汇总退出。
# macOS pwsh 只验证脚本对称性；Windows 内网目标机运行仍为 DECLARED-NOT-VERIFIED。
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

# node --test 不带路径参数，按 Node 默认规则发现 frontend/tests/ 下的测试。
Invoke-Step -Name "①b 前端纯函数核 node --test" -Action {
    Push-Location "frontend"
    try {
        node --test
    } finally {
        Pop-Location
    }
}

if ($env:UPDATE_GOLDENS -eq "1") {
    Write-Host "E2E 截图模式：显式更新 docs/reviews 金图"
} else {
    if ([string]::IsNullOrWhiteSpace($env:FLAI_E2E_ARTIFACT_DIR)) {
        $env:FLAI_E2E_ARTIFACT_DIR = Join-Path `
            ([System.IO.Path]::GetTempPath()) `
            ("flai-os-e2e-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force $env:FLAI_E2E_ARTIFACT_DIR | Out-Null
    }
    Write-Host "E2E 临时产物目录：$env:FLAI_E2E_ARTIFACT_DIR"
}

$E2EScripts = @(
    "frontend/e2e/m2_acceptance.py",
    "frontend/e2e/m6_guide_acceptance.py",
    "frontend/e2e/p23_question_acceptance.py",
    "frontend/e2e/p24_search_acceptance.py",
    "frontend/e2e/m8_collab_chain_acceptance.py",
    "frontend/e2e/m8_guide_orchestrator_acceptance.py",
    "frontend/e2e/m8_workbench_acceptance.py",
    "frontend/e2e/m9_guide_loop_acceptance.py",
    "frontend/e2e/m10_governance_acceptance.py",
    "frontend/e2e/m11_auth_acceptance.py",
    "frontend/e2e/cfd_flow_acceptance.py",
    "frontend/e2e/batch_a_livefeed_acceptance.py",
    "frontend/e2e/batch_b_today_acceptance.py",
    "frontend/e2e/batch_c_rewards_acceptance.py",
    "frontend/e2e/batch_d_visual_acceptance.py",
    "frontend/e2e/eval_queue_acceptance.py",
    "frontend/e2e/eval_snapshot_acceptance.py",
    "frontend/e2e/inline_summon_acceptance.py",
    "frontend/e2e/craft_desktop_acceptance.py",
    "frontend/e2e/batch_g_squad_acceptance.py",
    "frontend/e2e/batch_h_teams_acceptance.py",
    "frontend/e2e/agent_fact_projection_acceptance.py"
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
