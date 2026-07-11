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
