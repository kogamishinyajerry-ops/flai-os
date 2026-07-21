"""跨平台脚本契约：启动依赖与开发验证覆盖必须成对。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
VERIFY_SH = SCRIPTS_DIR / "verify_all.sh"
VERIFY_PS1 = SCRIPTS_DIR / "verify_all.ps1"
M2_ACCEPTANCE = REPO_ROOT / "frontend" / "e2e" / "m2_acceptance.py"
WITH_PACKAGE_RE = re.compile(r'''--with\s+(?:"([^"]+)"|'([^']+)'|([^\s`\\]+))''')

EXPECTED_E2E_SCRIPTS = (
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
    "frontend/e2e/agent_fact_projection_acceptance.py",
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


def _strip_shell_line_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    comment_boundaries = " \t\r\n;&|()<>"
    index = 0
    while index < len(line):
        char = line[index]
        if escaped:
            escaped = False
        elif quote is None:
            if char == "\\":
                escaped = True
            elif char in {'"', "'"}:
                quote = char
            elif char == "#" and (
                index == 0 or line[index - 1] in comment_boundaries
            ):
                return line[:index]
        elif quote == '"' and char == "\\":
            escaped = True
        elif char == quote:
            quote = None
        index += 1
    return line


def _without_shell_comments(source: str) -> str:
    return "\n".join(_strip_shell_line_comment(line) for line in source.splitlines())


def _without_powershell_comments(source: str) -> str:
    active: list[str] = []
    quote: str | None = None
    in_block_comment = False
    index = 0
    while index < len(source):
        char = source[index]
        if in_block_comment:
            if source.startswith("#>", index):
                in_block_comment = False
                index += 2
            else:
                if char == "\n":
                    active.append(char)
                index += 1
            continue

        if quote is not None:
            active.append(char)
            if quote == '"' and char == "`" and index + 1 < len(source):
                active.append(source[index + 1])
                index += 2
                continue
            if char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    active.append(source[index + 1])
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in {'"', "'"}:
            quote = char
            active.append(char)
            index += 1
        elif char == "`" and index + 1 < len(source):
            active.extend((char, source[index + 1]))
            index += 2
        elif source.startswith("<#", index):
            in_block_comment = True
            index += 2
        elif char == "#":
            while index < len(source) and source[index] != "\n":
                index += 1
        else:
            active.append(char)
            index += 1
    return "".join(active)


def _active_source(source: str, *, powershell: bool = False) -> str:
    if powershell:
        return _without_powershell_comments(source)
    return _without_shell_comments(source)


def _e2e_scripts(
    source: str,
    array_re: re.Pattern[str],
    *,
    powershell: bool = False,
) -> tuple[str, ...]:
    active_source = _active_source(source, powershell=powershell)
    match = array_re.search(active_source)
    assert match is not None, "未找到活动的 E2E 脚本数组"
    return tuple(re.findall(r'["\'](frontend/e2e/[^"\']+\.py)["\']', match.group(1)))


def _with_packages(path: Path) -> set[str]:
    source = _active_source(_read(path), powershell=path.suffix == ".ps1")
    matches = WITH_PACKAGE_RE.findall(source)
    return {next(group for group in match if group) for match in matches}


def _assert_execution_wiring(
    source: str,
    required_fragments: tuple[str, ...],
    *,
    powershell: bool = False,
) -> None:
    active_source = _active_source(source, powershell=powershell)
    cursor = 0
    for fragment in required_fragments:
        position = active_source.find(fragment, cursor)
        assert position >= 0, f"执行接线缺失或顺序错误：{fragment}"
        cursor = position + len(fragment)


@pytest.mark.parametrize("stem", ["dev_start_backend", "dev_start_worker", "init_db"])
def test_shell_and_powershell_with_dependencies_match(stem: str) -> None:
    shell_packages = _with_packages(SCRIPTS_DIR / f"{stem}.sh")
    powershell_packages = _with_packages(SCRIPTS_DIR / f"{stem}.ps1")

    assert shell_packages, f"{stem}.sh 未提取到任何 --with 依赖，需检查正则或脚本格式"
    assert powershell_packages, f"{stem}.ps1 未提取到任何 --with 依赖，需检查正则或脚本格式"
    assert shell_packages == powershell_packages


@pytest.mark.parametrize(
    "stem",
    [
        "deploy_selfcheck",
        "verify_m4_signal_package",
        "verify_n10_observation_package",
    ],
)
def test_fail_closed_python_gate_wrappers_are_paired(stem: str) -> None:
    shell = _active_source(_read(SCRIPTS_DIR / f"{stem}.sh"))
    powershell = _active_source(
        _read(SCRIPTS_DIR / f"{stem}.ps1"), powershell=True
    )

    assert f'exec python3 scripts/{stem}.py "$@"' in shell
    assert f"python scripts/{stem}.py @args" in powershell
    assert "$null -eq $LASTEXITCODE" in powershell
    assert "exit $LASTEXITCODE" in powershell
    assert re.search(r"catch\s*\{.*?exit 1\s*\}", powershell, re.DOTALL)


def test_development_verification_entries_have_equivalent_coverage() -> None:
    shell = _read(VERIFY_SH)
    powershell = _read(VERIFY_PS1)

    assert _e2e_scripts(shell, SHELL_ARRAY_RE) == EXPECTED_E2E_SCRIPTS
    assert _e2e_scripts(
        powershell,
        POWERSHELL_ARRAY_RE,
        powershell=True,
    ) == EXPECTED_E2E_SCRIPTS

    active_shell = _active_source(shell)
    active_powershell = _active_source(powershell, powershell=True)
    for required_command in SHELL_REQUIRED_COMMANDS:
        assert required_command.search(active_shell) is not None
    for required_command in POWERSHELL_REQUIRED_COMMANDS:
        assert required_command.search(active_powershell) is not None
    _assert_execution_wiring(shell, SHELL_EXECUTION_WIRING)
    _assert_execution_wiring(
        powershell,
        POWERSHELL_EXECUTION_WIRING,
        powershell=True,
    )


def test_m2_acceptance_has_no_wall_clock_or_temporary_debug_probe() -> None:
    source = _read(M2_ACCEPTANCE)

    assert "time.time()" not in source
    assert 'lambda: "已完成" in page.locator("body").inner_text()' not in source
    assert "[DEBUG-m2race]" not in source
    assert "[M2-DIAG]" not in source
    assert "[M2-STACK]" not in source


def test_contract_parser_ignores_commented_paths_and_step_labels() -> None:
    commented_shell = '''
E2E_SCRIPTS=(
  # "frontend/e2e/m2_acceptance.py"
)
run_step "node --test" noop
# (cd frontend && node --test)
'''

    assert _e2e_scripts(commented_shell, SHELL_ARRAY_RE) == ()
    active_source = _without_shell_comments(commented_shell)
    assert SHELL_REQUIRED_COMMANDS[-1].search(active_source) is None
    with pytest.raises(AssertionError):
        _assert_execution_wiring(commented_shell, SHELL_EXECUTION_WIRING)


def test_contract_parser_ignores_powershell_block_comments() -> None:
    commented_powershell = '''
<#
$E2EScripts = @(
  "frontend/e2e/m2_acceptance.py"
)
Invoke-Step -Name "① frontend npm run build" -Action {
Invoke-Step -Name "② 全量 pytest -n auto（三个 testpaths）" -Action {
Invoke-Step -Name "①b 前端纯函数核 node --test" -Action {
foreach ($E2EScript in $E2EScripts) {
python $E2EScript
#>
$E2EScripts = @(
)
'''

    assert _e2e_scripts(
        commented_powershell,
        POWERSHELL_ARRAY_RE,
        powershell=True,
    ) == ()
    with pytest.raises(AssertionError):
        _assert_execution_wiring(
            commented_powershell,
            POWERSHELL_EXECUTION_WIRING,
            powershell=True,
        )


def test_execution_wiring_rejects_reordered_steps() -> None:
    reordered_shell = "\n".join(reversed(SHELL_EXECUTION_WIRING))

    with pytest.raises(AssertionError, match="缺失或顺序错误"):
        _assert_execution_wiring(reordered_shell, SHELL_EXECUTION_WIRING)


def test_contract_parser_ignores_inline_comment_decoys() -> None:
    commented_powershell = '''
$E2EScripts = @(
  $null # "frontend/e2e/m2_acceptance.py"
)
'''
    wiring_decoys = "\n".join(
        f'Write-Host "decoy" # {fragment}'
        for fragment in POWERSHELL_EXECUTION_WIRING
    )

    assert _e2e_scripts(
        commented_powershell,
        POWERSHELL_ARRAY_RE,
        powershell=True,
    ) == ()
    with pytest.raises(AssertionError, match="缺失或顺序错误"):
        _assert_execution_wiring(
            wiring_decoys,
            POWERSHELL_EXECUTION_WIRING,
            powershell=True,
        )
    assert _without_powershell_comments(
        'Write-Host "literal # value" # Invoke-Step decoy'
    ) == 'Write-Host "literal # value" '


def test_powershell_backslash_does_not_escape_quote_before_comment() -> None:
    wiring_decoys = "\n".join(
        r'Write-Host "x\" # ' + fragment
        for fragment in POWERSHELL_EXECUTION_WIRING
    )

    with pytest.raises(AssertionError, match="缺失或顺序错误"):
        _assert_execution_wiring(
            wiring_decoys,
            POWERSHELL_EXECUTION_WIRING,
            powershell=True,
        )


def test_shell_comment_stripping_preserves_parameter_length_operator() -> None:
    source = 'if ((${#COMPLETED_STEPS[@]})); then # real comment'

    assert _without_shell_comments(source) == 'if ((${#COMPLETED_STEPS[@]})); then '
