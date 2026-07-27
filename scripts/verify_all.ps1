# Run the frontend build, full backend test suite, and browser acceptance gates.
# DECLARED-NOT-VERIFIED: parsing is verified on Windows PowerShell 5.1, but the full gate still awaits dependencies.
# Stop immediately on failure and print the completed/failed step summary.
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$script:CompletedSteps = @()
$script:FailedSteps = @()

function Show-Summary {
    Write-Host ""
    Write-Host "Verification summary:"
    if ($script:CompletedSteps.Count -eq 0) {
        Write-Host "- [completed] (none)"
    } else {
        foreach ($Step in $script:CompletedSteps) {
            Write-Host "- [completed] $Step"
        }
    }
    if ($script:FailedSteps.Count -eq 0) {
        Write-Host "- [failed] (none)"
    } else {
        foreach ($Step in $script:FailedSteps) {
            Write-Host "- [failed] $Step"
        }
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    Write-Host ""
    Write-Host "Starting: $Name"
    $global:LASTEXITCODE = 0
    try {
        & $Action
        $ExitCode = $LASTEXITCODE
    } catch {
        $ExitCode = if ($LASTEXITCODE -ne 0) { $LASTEXITCODE } else { 1 }
        $script:FailedSteps += "$Name (exit code $ExitCode; $($_.Exception.Message))"
        Show-Summary
        exit $ExitCode
    }

    if ($ExitCode -ne 0) {
        $script:FailedSteps += "$Name (exit code $ExitCode)"
        Show-Summary
        exit $ExitCode
    }

    $script:CompletedSteps += $Name
    Write-Host "Completed: $Name"
}

Invoke-Step -Name "1. frontend npm run build" -Action {
    Push-Location "frontend"
    try {
        npm run build
    } finally {
        Pop-Location
    }
}

# Keep pytest unscoped so pyproject testpaths run in full
# (tests/ + tools_impl/ + backend/tests), matching verify_all.sh.
Invoke-Step -Name "2. full pytest -n auto (all three testpaths)" -Action {
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
    "frontend/e2e/m10_governance_acceptance.py",
    "frontend/e2e/batch_c_rewards_acceptance.py",
    "frontend/e2e/batch_d_visual_acceptance.py",
    "frontend/e2e/inline_summon_acceptance.py",
    "frontend/e2e/craft_desktop_acceptance.py",
    "frontend/e2e/batch_g_squad_acceptance.py",
    "frontend/e2e/batch_h_teams_acceptance.py"
)

foreach ($E2EScript in $E2EScripts) {
    Invoke-Step -Name "3. E2E $E2EScript" -Action {
        uv run --no-project `
            --with playwright --with uvicorn --with pytest --with pytest-xdist `
            --with jsonschema --with pyyaml --with fastapi --with httpx `
            --with python-multipart --with "pydantic>2" --with jieba --with openpyxl `
            python $E2EScript
    }
}

Show-Summary
