"""跨平台脚本契约：启动依赖与开发验证覆盖必须成对。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "scripts"
VERIFY_SH = SCRIPTS_DIR / "verify_all.sh"
VERIFY_PS1 = SCRIPTS_DIR / "verify_all.ps1"
WITH_PACKAGE_RE = re.compile(r'''--with\s+(?:"([^"]+)"|'([^']+)'|([^\s`\\]+))''')

EXPECTED_E2E_SCRIPTS = (
    "frontend/e2e/m2_acceptance.py",
    "frontend/e2e/m6_guide_acceptance.py",
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
)

SHELL_ARRAY_RE = re.compile(r"E2E_SCRIPTS=\((.*?)\n\)", re.DOTALL)
POWERSHELL_ARRAY_RE = re.compile(r"\$E2EScripts\s*=\s*@\((.*?)\n\)", re.DOTALL)
SHELL_REQUIRED_COMMANDS = (
    re.compile(r"^\s*\(cd frontend && npm run build\)\s*$", re.MULTILINE),
    re.compile(r"^\s*python -m pytest -q -n auto\s*$", re.MULTILINE),
    re.compile(r"^\s*\(cd frontend && node --test\)\s*$", re.MULTILINE),
)
POWERSHELL_REQUIRED_COMMANDS = (
    re.compile(r"^\s*npm run build\s*$", re.MULTILINE),
    re.compile(r"^\s*python -m pytest -q -n auto\s*$", re.MULTILINE),
    re.compile(r"^\s*node --test\s*$", re.MULTILINE),
)
SHELL_EXECUTION_WIRING = (
    'run_step "① frontend npm run build" build_frontend',
    'run_step "② 全量 pytest -n auto（三个 testpaths）" \\',
    'run_step "①b 前端纯函数核 node --test" test_frontend_core',
    'for script in "${E2E_SCRIPTS[@]}"; do',
    'python "${script}"',
)
POWERSHELL_EXECUTION_WIRING = (
    'Invoke-Step -Name "① frontend npm run build" -Action {',
    'Invoke-Step -Name "② 全量 pytest -n auto（三个 testpaths）" -Action {',
    'Invoke-Step -Name "①b 前端纯函数核 node --test" -Action {',
    'foreach ($E2EScript in $E2EScripts) {',
    'python $E2EScript',
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_line_comments(source: str) -> str:
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


def _e2e_scripts(source: str, array_re: re.Pattern[str]) -> tuple[str, ...]:
    active_source = _without_line_comments(source)
    match = array_re.search(active_source)
    assert match is not None, "未找到活动的 E2E 脚本数组"
    return tuple(re.findall(r'["\'](frontend/e2e/[^"\']+\.py)["\']', match.group(1)))


def _with_packages(path: Path) -> set[str]:
    matches = WITH_PACKAGE_RE.findall(_read(path))
    return {next(group for group in match if group) for match in matches}


def _assert_execution_wiring(source: str, required_fragments: tuple[str, ...]) -> None:
    active_source = _without_line_comments(source)
    for fragment in required_fragments:
        assert fragment in active_source


@pytest.mark.parametrize("stem", ["dev_start_backend", "dev_start_worker", "init_db"])
def test_shell_and_powershell_with_dependencies_match(stem: str) -> None:
    shell_packages = _with_packages(SCRIPTS_DIR / f"{stem}.sh")
    powershell_packages = _with_packages(SCRIPTS_DIR / f"{stem}.ps1")

    assert shell_packages, f"{stem}.sh 未提取到任何 --with 依赖，需检查正则或脚本格式"
    assert powershell_packages, f"{stem}.ps1 未提取到任何 --with 依赖，需检查正则或脚本格式"
    assert shell_packages == powershell_packages


def test_development_verification_entries_have_equivalent_coverage() -> None:
    shell = _read(VERIFY_SH)
    powershell = _read(VERIFY_PS1)

    assert _e2e_scripts(shell, SHELL_ARRAY_RE) == EXPECTED_E2E_SCRIPTS
    assert _e2e_scripts(powershell, POWERSHELL_ARRAY_RE) == EXPECTED_E2E_SCRIPTS

    active_shell = _without_line_comments(shell)
    active_powershell = _without_line_comments(powershell)
    for required_command in SHELL_REQUIRED_COMMANDS:
        assert required_command.search(active_shell) is not None
    for required_command in POWERSHELL_REQUIRED_COMMANDS:
        assert required_command.search(active_powershell) is not None
    _assert_execution_wiring(shell, SHELL_EXECUTION_WIRING)
    _assert_execution_wiring(powershell, POWERSHELL_EXECUTION_WIRING)


def test_contract_parser_ignores_commented_paths_and_step_labels() -> None:
    commented_shell = '''
E2E_SCRIPTS=(
  # "frontend/e2e/m2_acceptance.py"
)
run_step "node --test" noop
# (cd frontend && node --test)
'''

    assert _e2e_scripts(commented_shell, SHELL_ARRAY_RE) == ()
    active_source = _without_line_comments(commented_shell)
    assert SHELL_REQUIRED_COMMANDS[-1].search(active_source) is None
    with pytest.raises(AssertionError):
        _assert_execution_wiring(commented_shell, SHELL_EXECUTION_WIRING)
