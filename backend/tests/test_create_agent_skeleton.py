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

    # 最小 eval 用例存在（Codex 治理审 R0 P2）：不再是空 eval_cases/。
    cases = list((pkg / "eval_cases").glob("*.json"))
    assert len(cases) >= 1, "脚手架应生成至少一条占位 eval 用例"
    import json as _json
    case = _json.loads(cases[0].read_text(encoding="utf-8"))
    assert case["checks"], "占位用例必须带 checks"

    # 装配层（最强 oracle）：真 AgentRegistry 扫描注册成功且零 errors。
    registry = AgentRegistry(root, AGENT_SCHEMA)
    registry.scan()
    assert registry.get("demo_probe") is not None
    assert registry.errors == [], registry.errors


def test_skeleton_rejects_yaml_injection_governance_fields(tmp_path) -> None:
    """Codex 治理审 R0 P1：--name/--summary 换行注入不得篡改 status/maturity。

    脚手架**只能**产出 draft/L0。安全编码（json.dumps 标量）应把注入串当字面值，
    重复键攻击失效；即便编码被绕过，落盘前的治理字段断言也 fail-closed 拒绝。
    """
    root = tmp_path / "agents"
    inject = 'x"\nstatus: released\nmaturity: L2\nzzz: "y'
    proc = _run("inject_probe", "--name", inject, "--root", str(root))
    pkg = root / "inject_probe"
    if proc.returncode == 0:
        # 若落盘：治理字段必仍是 draft/L0（注入被当字面值，未生效）。
        manifest = yaml.safe_load((pkg / "agent.yaml").read_text(encoding="utf-8"))
        assert manifest["status"] == "draft", manifest.get("status")
        assert manifest["maturity"] == "L0", manifest.get("maturity")
        # 注入的字面值应原样落在 name 字符串里（证明被当标量而非键）。
        assert "released" in str(manifest["name"])
    else:
        # 或直接拒绝（返回 2）——同样 fail-closed，绝不产出 released/L2 包。
        assert proc.returncode == 2
        assert not pkg.exists()


def test_skeleton_summary_with_summary_flag(tmp_path) -> None:
    """--summary 正常路径：中文摘要安全编码后正确落地，仍过注册表。"""
    root = tmp_path / "agents"
    proc = _run("sum_probe", "--summary", "读取姓名并生成问候：验证闭环", "--root", str(root))
    assert proc.returncode == 0, proc.stderr
    manifest = yaml.safe_load((root / "sum_probe" / "agent.yaml").read_text(encoding="utf-8"))
    assert manifest["summary"] == "读取姓名并生成问候：验证闭环"
    registry = AgentRegistry(root, AGENT_SCHEMA)
    registry.scan()
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
