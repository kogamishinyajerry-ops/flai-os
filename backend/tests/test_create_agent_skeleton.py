"""create_agent_skeleton（评审 N14）测试。

核心 oracle 不是「文件存在」而是**真注册表咬合**：生成的包必须被
AgentRegistry.scan() 当场注册且零 errors——脚手架产物若破坏装配，
会连带拖垮整个 app 启动，这是最不能假绿的一格。
反向钥匙：已存在目录拒绝（不覆盖不落半截）、非法 id 拒绝。
"""

from __future__ import annotations

import json
import subprocess
import sys

import jsonschema
import yaml
from conftest import REPO_ROOT

from backend.app.runtime.registry import AgentRegistry

SCRIPT = REPO_ROOT / "scripts" / "create_agent_skeleton.py"
AGENT_SCHEMA = REPO_ROOT / "contracts" / "agent.schema.json"


def _run(*args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_skeleton_generates_registry_valid_package(tmp_path) -> None:
    root = tmp_path / "agents"
    proc = _run("demo_probe", "--root", str(root))
    assert proc.returncode == 0, proc.stderr

    pkg = root / "demo_probe"
    for rel in ("agent.yaml", "input_schema.json", "output_schema.json",
                "workflow.py", "README.md", "changelog.md", "prompt.md"):
        assert (pkg / rel).is_file(), f"缺文件 {rel}"
    assert (pkg / "eval_cases").is_dir()

    # 契约层：yaml 过 agent.schema.json；IO 契约本身是合法 JSON Schema。
    manifest = yaml.safe_load((pkg / "agent.yaml").read_text(encoding="utf-8"))
    jsonschema.validate(manifest, json.loads(AGENT_SCHEMA.read_text(encoding="utf-8")))
    assert manifest["status"] == "draft"
    assert manifest["maturity"] == "L0"
    assert manifest["workflow"]["requires_human_review"] is True  # 人签发默认在

    # 装配层（最强 oracle）：真 AgentRegistry 扫描注册成功且零 errors。
    registry = AgentRegistry(root, AGENT_SCHEMA)
    registry.scan()
    assert registry.get("demo_probe") is not None
    assert registry.errors == [], registry.errors


def test_skeleton_refuses_existing_dir(tmp_path) -> None:
    root = tmp_path / "agents"
    assert _run("dup_probe", "--root", str(root)).returncode == 0
    marker = root / "dup_probe" / "agent.yaml"
    before = marker.read_text(encoding="utf-8")

    proc = _run("dup_probe", "--root", str(root))
    assert proc.returncode == 2
    assert "已存在" in proc.stderr
    # 拒绝 = 一个字节都不动（不覆盖不追加）。
    assert marker.read_text(encoding="utf-8") == before


def test_skeleton_refuses_illegal_id(tmp_path) -> None:
    root = tmp_path / "agents"
    for bad in ("Bad-ID", "1starts_with_digit", "ab", "有中文"):
        proc = _run(bad, "--root", str(root))
        assert proc.returncode == 2, f"{bad!r} 应被拒"
        assert "不合法" in proc.stderr
    assert not root.exists() or list(root.iterdir()) == []  # 全拒 = 零残留
