"""协作运行时 F3 注册期不变量（§3.6）：判决⟹人签。

不变量：workflow.mode==job 且 model.profile!=none ⟹ workflow.requires_human_review is True，
违反=注册期 fail-closed 拒载。这是 F3 owner 裁决（注册期不变量）的机械落点——令
depends_on 链里的非 review-gated 上游恒为 profile=none 确定性 Agent，LLM 判决永不无人签
流经协作链。

T8 tamper witness：违反不变量的 agent 必须被 registry 拒载（=咬合）；正控（合规 agent
照常注册）证明校验有判别力非全拒。拆=移除 registry._load_one 的不变量校验→违反 agent
被接受→本文件 test_violation_* 变绿失败（红→绿翻转即 defense 失效证据）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.runtime.registry import AgentRegistry

_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"


def _clone(src_id: str, agents_dir: Path, new_id: str) -> Path:
    """把真实 agent 包克隆到 tmp agents_dir 下，返回包目录（id 保持原样，单包扫描）。"""
    dest = agents_dir / new_id
    shutil.copytree(AGENTS_DIR / src_id, dest)
    return dest


def _patch_yaml(pkg: Path, **overrides) -> None:
    """按 dotted-path 覆写 agent.yaml，如 workflow.requires_human_review=False。"""
    data = yaml.safe_load((pkg / "agent.yaml").read_text(encoding="utf-8"))
    for dotted, value in overrides.items():
        node = data
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    (pkg / "agent.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _scan(agents_dir: Path) -> AgentRegistry:
    reg = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    reg.scan()
    return reg


# ── 正控：合规 LLM job agent 照常注册（证校验有判别力，非全拒）──────────────

def test_control_llm_job_agent_registers(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _clone("fta_agent", agents_dir, "fta_agent")  # profile=reasoning + rhr=True
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is not None
    assert reg.errors == []


# ── T8 咬合：违反不变量的 agent 被拒载 ─────────────────────────────────────

def test_violation_llm_job_not_gated_rejected(tmp_path: Path) -> None:
    """profile=reasoning + mode=job + requires_human_review=False → 拒载。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, **{"workflow.requires_human_review": False})
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is None, "违反不变量的 agent 竟被注册——defense 失效"
    assert len(reg.errors) == 1
    assert "requires_human_review" in reg.errors[0]["error"]
    assert "F3" in reg.errors[0]["error"] or "review-gated" in reg.errors[0]["error"]


def test_violation_truthiness_not_accepted(tmp_path: Path) -> None:
    """严格 is True：requires_human_review 为真值但非 True（如字符串 'yes'）也拒——
    安全 gate 一律 is True，绝不 truthiness。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, **{"workflow.requires_human_review": "yes"})
    reg = _scan(agents_dir)
    # schema 可能先拦（rhr 声明为 boolean）——两种拒法都算 fail-closed 正确
    assert reg.get("fta_agent") is None


# ── 豁免：交互式 Agent（跑 ConversationService 不入链）─────────────────────

def test_exempt_interactive_agent_registers(tmp_path: Path) -> None:
    """guide_agent：profile=reasoning + rhr=False + mode=interactive → 豁免通过
    （不入 depends_on 链，安全阀=ADR-0012 绝不建任务）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _clone("guide_agent", agents_dir, "guide_agent")
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is not None, "交互式 Agent 被误杀——mode==job 限定失效"
    assert reg.errors == []


# ── 豁免：确定性 job Agent（profile=none）非-gated 合法 ─────────────────────

def test_exempt_deterministic_job_agent_registers(tmp_path: Path) -> None:
    """performance_disk_agent：profile=none + rhr=False + mode=job → 合法非-gated
    （确定性，不产 LLM 判决，自动链安全）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _clone("performance_disk_agent", agents_dir, "performance_disk_agent")
    reg = _scan(agents_dir)
    assert reg.get("performance_disk_agent") is not None
    assert reg.errors == []


# ── 存量 fleet 全过（真实 AGENTS_DIR 无回归）────────────────────────────────

def test_real_fleet_all_pass_invariant() -> None:
    """真实 9 Agent fleet 以新不变量全过——诚实上报的存量校验（§3.6）。"""
    reg = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
    reg.scan()
    invariant_errors = [e for e in reg.errors if "F3" in e["error"] or "review-gated" in e["error"]]
    assert invariant_errors == [], f"存量 Agent 违反 F3 不变量：{invariant_errors}"
