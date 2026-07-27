"""跨平台脚本依赖声明对账测试；只读脚本文本，不执行脚本。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
WITH_PACKAGE_RE = re.compile(r'''--with\s+(?:"([^"]+)"|'([^']+)'|([^\s`\\]+))''')


def _with_packages(path: Path) -> set[str]:
    matches = WITH_PACKAGE_RE.findall(path.read_text(encoding="utf-8"))
    return {next(group for group in match if group) for match in matches}


@pytest.mark.parametrize("stem", ["dev_start_backend", "dev_start_worker", "init_db"])
def test_shell_and_powershell_with_dependencies_match(stem: str) -> None:
    shell_packages = _with_packages(SCRIPTS_DIR / f"{stem}.sh")
    powershell_packages = _with_packages(SCRIPTS_DIR / f"{stem}.ps1")

    assert shell_packages, f"{stem}.sh 未提取到任何 --with 依赖，需检查正则或脚本格式"
    assert powershell_packages, f"{stem}.ps1 未提取到任何 --with 依赖，需检查正则或脚本格式"
    assert shell_packages == powershell_packages


def test_m10_governance_e2e_runs_in_both_full_verification_scripts() -> None:
    required_script = "frontend/e2e/m10_governance_acceptance.py"

    for script_name in ("verify_all.sh", "verify_all.ps1"):
        script = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
        assert required_script in script, f"{script_name} 未执行 {required_script}"


def test_full_windows_verification_script_is_ascii_for_windows_powershell_51() -> None:
    raw_script = (SCRIPTS_DIR / "verify_all.ps1").read_bytes()

    assert raw_script.isascii(), (
        "verify_all.ps1 must stay ASCII so Windows PowerShell 5.1 does not "
        "misdecode non-ASCII strings and fail during parsing"
    )
