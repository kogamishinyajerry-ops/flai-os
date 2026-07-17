"""批七 ADR-0030 装载期不变量（专家身份轴/依据纪律/密级契约）。

两条新不变量的 tamper witness：
① L3「带我做」且 mode=job ⟹ requires_human_review is True——即使 profile=none
  的确定性 job 包也无免签通道（比既有 F3 job×LLM 不变量更强的一层）。
② evidence_policy.required=true ⟹ 包内 output_schema 顶层 properties 含 findings
  ——依据承诺必须有输出结构承接，否则拒载。
拆=移除 registry._load_one 对应校验 → violation 用例红→绿翻转即 defense 失效。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.runtime.registry import AgentRegistry

_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"

_EXPERTISE = {
    "domain": "fault_history",
    "specialty": "历史故障结构化检索与跨型号相似案例推荐",
    "usefulness_level": "L2",
    "charter": "我会基于已收录的故障报告推荐相似案例；未收录的型号我会明说无法覆盖。",
}


def _clone(src_id: str, agents_dir: Path, new_id: str) -> Path:
    dest = agents_dir / new_id
    shutil.copytree(AGENTS_DIR / src_id, dest)
    return dest


def _patch_yaml(pkg: Path, **overrides) -> None:
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


# ── ① L3 ⟹ 人签（对 profile=none job 包也生效——既有 F3 不咬的盲区）──────────

def test_violation_l3_job_without_review_rejected(tmp_path: Path) -> None:
    """performance_disk_agent（profile=none + rhr=False，F3 合法）+ L3 承诺 → 拒载。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("performance_disk_agent", agents_dir, "performance_disk_agent")
    _patch_yaml(pkg, expertise={**_EXPERTISE, "usefulness_level": "L3"})
    reg = _scan(agents_dir)
    assert reg.get("performance_disk_agent") is None, "L3 无人签竟被注册——ADR-0030① 失效"
    assert len(reg.errors) == 1
    assert "L3" in reg.errors[0]["error"]


def test_exempt_l2_job_without_review_registers(tmp_path: Path) -> None:
    """同包 L2 承诺 → 合法注册（不变量只咬 L3，有判别力非全拒）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("performance_disk_agent", agents_dir, "performance_disk_agent")
    _patch_yaml(pkg, expertise=dict(_EXPERTISE))
    reg = _scan(agents_dir)
    assert reg.get("performance_disk_agent") is not None
    assert reg.errors == []


def test_control_l3_with_review_registers(tmp_path: Path) -> None:
    """fta_agent（rhr=True）+ L3 → 合法注册（正控）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, expertise={**_EXPERTISE, "usefulness_level": "L3"})
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is not None
    assert reg.errors == []


# ── ② 依据承诺 ⟹ findings 输出结构 ─────────────────────────────────────────

def test_violation_evidence_required_without_findings_rejected(tmp_path: Path) -> None:
    """fta_agent 的 output_schema 无 findings + evidence_policy.required=true → 拒载。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, evidence_policy={"required": True, "kinds": ["fault_case"]})
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is None, "依据承诺无 findings 承接竟被注册——ADR-0030② 失效"
    assert len(reg.errors) == 1
    assert "findings" in reg.errors[0]["error"]


def test_control_evidence_required_with_findings_registers(tmp_path: Path) -> None:
    """同包 output_schema 补 findings 定义 → 合法注册（正控）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, evidence_policy={"required": True, "kinds": ["fault_case"]})
    out_path = pkg / "output_schema.json"
    out_doc = json.loads(out_path.read_text(encoding="utf-8"))
    out_doc.setdefault("properties", {})["findings"] = {"type": "array"}
    out_path.write_text(json.dumps(out_doc, ensure_ascii=False), encoding="utf-8")
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is not None
    assert reg.errors == []


def test_exempt_evidence_not_required_registers(tmp_path: Path) -> None:
    """evidence_policy.required=false → 无 findings 也合法（只咬承诺了的）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, evidence_policy={"required": False})
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is not None
    assert reg.errors == []


# ── schema 层：非法 domain 被契约拒 ─────────────────────────────────────────

def test_schema_rejects_unknown_domain(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, expertise={**_EXPERTISE, "domain": "astrology"})
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is None
    assert "agent.schema.json" in reg.errors[0]["error"]


# ── 存量 fleet 三 block 全缺省下零回归 ───────────────────────────────────────

def test_real_fleet_passes_new_invariants() -> None:
    reg = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
    reg.scan()
    b7_errors = [e for e in reg.errors if "ADR-0030" in e["error"] or "L3" in e["error"] or "findings" in e["error"]]
    assert b7_errors == [], f"存量包违反批七不变量：{b7_errors}"
