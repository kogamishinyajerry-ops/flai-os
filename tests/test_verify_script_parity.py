"""Cross-platform verification entrypoints must keep the same executable gate."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "scripts" / "verify_all.sh"
PS1 = ROOT / "scripts" / "verify_all.ps1"
ARTIFACT_HELPER = ROOT / "frontend" / "e2e" / "_artifacts.py"

SCREENSHOT_E2E_SUITES = {
    "m2_acceptance.py": "m2-acceptance-shots",
    "m6_guide_acceptance.py": "m6-guide-shots",
    "m8_collab_chain_acceptance.py": "m8-collab-chain-shots",
    "m8_guide_orchestrator_acceptance.py": "m8-orchestrator-shots",
    "m8_workbench_acceptance.py": "m8-workbench-shots",
    "m9_guide_loop_acceptance.py": "m9-guide-loop-shots",
    "m10_governance_acceptance.py": "m10-acceptance-shots",
    "m11_auth_acceptance.py": "m11-auth-shots",
    "batch_a_livefeed_acceptance.py": "batch-a-livefeed-shots",
    "batch_b_today_acceptance.py": "batch-b-shots",
    "batch_c_rewards_acceptance.py": "batch-c-shots",
    "batch_d_visual_acceptance.py": "batch-d-shots",
}


def _e2e_scripts(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"(frontend/e2e/[^"\n]+\.py)"', text)


def test_verify_all_platform_scripts_run_the_same_e2e_suite() -> None:
    shell_scripts = _e2e_scripts(SH)
    powershell_scripts = _e2e_scripts(PS1)

    assert shell_scripts
    assert powershell_scripts == shell_scripts
    assert all((ROOT / script).is_file() for script in shell_scripts)


def test_verify_all_platform_scripts_both_run_frontend_node_tests() -> None:
    assert "node --test" in SH.read_text(encoding="utf-8")
    assert "node --test" in PS1.read_text(encoding="utf-8")


def test_screenshot_e2e_suites_use_the_shared_artifact_root_helper() -> None:
    assert ARTIFACT_HELPER.is_file()

    for filename, suite_dir in SCREENSHOT_E2E_SUITES.items():
        text = (ROOT / "frontend" / "e2e" / filename).read_text(encoding="utf-8")
        assert "from _artifacts import artifact_dir" in text, filename
        assert f'SHOTS = artifact_dir(REPO, "{suite_dir}")' in text, filename
        assert 'SHOTS = REPO / "docs" / "reviews"' not in text, filename


def test_artifact_helper_preserves_direct_run_default_and_honors_override(
    monkeypatch, tmp_path: Path
) -> None:
    spec = importlib.util.spec_from_file_location("flai_e2e_artifacts", ARTIFACT_HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.delenv("FLAI_E2E_ARTIFACT_ROOT", raising=False)
    assert module.artifact_dir(ROOT, "suite-shots") == ROOT / "docs" / "reviews" / "suite-shots"

    redirected_root = tmp_path / "acceptance-artifacts"
    monkeypatch.setenv("FLAI_E2E_ARTIFACT_ROOT", str(redirected_root))
    assert module.artifact_dir(ROOT, "suite-shots") == redirected_root / "suite-shots"


def test_verify_all_platform_scripts_redirect_artifacts_to_printed_temp_roots() -> None:
    shell = SH.read_text(encoding="utf-8")
    powershell = PS1.read_text(encoding="utf-8")

    assert 'export FLAI_E2E_ARTIFACT_ROOT' in shell
    assert 'mktemp -d' in shell
    assert 'E2E artifacts: ${FLAI_E2E_ARTIFACT_ROOT}' in shell

    assert '$env:FLAI_E2E_ARTIFACT_ROOT' in powershell
    assert '[System.IO.Path]::GetTempPath()' in powershell
    assert 'New-Item -ItemType Directory' in powershell
    assert 'E2E artifacts: $env:FLAI_E2E_ARTIFACT_ROOT' in powershell
