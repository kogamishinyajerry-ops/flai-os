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
    # 3-lens P2 收紧后：正控须给出最低可核验结构（array + evidence + resolved），
    # 仅 {"type": "array"} 已不再够格（无判别力的空承诺同样拒载）。
    out_doc.setdefault("properties", {})["findings"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "evidence": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"resolved": {"const": False}}},
                }
            },
        },
    }
    out_path.write_text(json.dumps(out_doc, ensure_ascii=False), encoding="utf-8")
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is not None
    assert reg.errors == []


def test_violation_evidence_findings_vacuous_schema_rejected(tmp_path: Path) -> None:
    """3-lens P2：findings 给空 schema `{}` 或缺 evidence/resolved 结构=无判别力的
    假承诺——同样拒载（仅顶层有键不算兑现）。"""
    for weak in ({}, {"type": "array"}, {"type": "object"}):
        agents_dir = tmp_path / f"agents_{len(str(weak))}"
        agents_dir.mkdir()
        pkg = _clone("fta_agent", agents_dir, "fta_agent")
        _patch_yaml(pkg, evidence_policy={"required": True, "kinds": ["fault_case"]})
        out_path = pkg / "output_schema.json"
        out_doc = json.loads(out_path.read_text(encoding="utf-8"))
        out_doc.setdefault("properties", {})["findings"] = weak
        out_path.write_text(json.dumps(out_doc, ensure_ascii=False), encoding="utf-8")
        reg = _scan(agents_dir)
        assert reg.get("fta_agent") is None, f"弱 schema {weak!r} 竟被注册"
        assert len(reg.errors) == 1


def test_malformed_output_schema_quarantined_not_crash(tmp_path: Path) -> None:
    """Codex R0 P1：output_schema.json 顶层非 object（`[]` 是合法 JSON）→ 该包
    隔离进 reg.errors，scan 不崩、同目录健康包照常注册（一个坏包不炸全场）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    bad = _clone("fta_agent", agents_dir, "bad_agent")
    _patch_yaml(bad, id="bad_agent", evidence_policy={"required": True, "kinds": ["fault_case"]})
    (bad / "output_schema.json").write_text("[]", encoding="utf-8")
    good = _clone("policy_qa_agent", agents_dir, "policy_qa_agent")
    assert good.is_dir()
    reg = _scan(agents_dir)  # 不得抛 AttributeError
    assert reg.get("bad_agent") is None
    assert any("bad_agent" in e["path"] for e in reg.errors)
    assert reg.get("policy_qa_agent") is not None, "坏包隔离失败殃及健康包"


def test_non_utf8_output_schema_quarantined_not_crash(tmp_path: Path) -> None:
    """Codex R1 P2：非 UTF-8 的 output_schema.json（UnicodeDecodeError 逃逸面）
    同样隔离进 errors，不炸整个 scan。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    bad = _clone("fta_agent", agents_dir, "bad_agent")
    _patch_yaml(bad, id="bad_agent", evidence_policy={"required": True, "kinds": ["fault_case"]})
    (bad / "output_schema.json").write_bytes(b"\xff\xfe\x00broken")
    reg = _scan(agents_dir)  # 不得抛 UnicodeDecodeError
    assert reg.get("bad_agent") is None
    assert any("bad_agent" in e["path"] for e in reg.errors)


def test_violation_evidence_string_match_bypass_rejected(tmp_path: Path) -> None:
    """Codex R0 P2：findings 里塞名为 evidence/resolved 的**兄弟键**（items 无约束）
    ——旧字符串搜索会放行，结构化路径校验必须拒载。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("fta_agent", agents_dir, "fta_agent")
    _patch_yaml(pkg, evidence_policy={"required": True, "kinds": ["fault_case"]})
    out_path = pkg / "output_schema.json"
    out_doc = json.loads(out_path.read_text(encoding="utf-8"))
    out_doc.setdefault("properties", {})["findings"] = {
        "type": "array",
        "x-evidence": "evidence",
        "x-resolved": "resolved",
    }
    out_path.write_text(json.dumps(out_doc, ensure_ascii=False), encoding="utf-8")
    reg = _scan(agents_dir)
    assert reg.get("fta_agent") is None, "兄弟键字面命中 evidence/resolved 竟骗过装载门"
    assert len(reg.errors) == 1


def test_qa_output_schemas_reject_both_empty(tmp_path: Path) -> None:
    """Codex R0 P1：三垂类包 output schema 拒收 findings 与 refusals 双空——
    「无依据也无拒答」的裸结论违反 evidence-required/refuse-if-uncovered 承诺。"""
    import jsonschema
    import pytest
    for pkg_id in ("policy_qa_agent", "standards_qa_agent"):
        sch = json.loads((AGENTS_DIR / pkg_id / "output_schema.json").read_text(encoding="utf-8"))
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"answer": "无依据裸结论", "findings": [], "refusals": []}, sch)
    fh = json.loads((AGENTS_DIR / "fault_history_agent" / "output_schema.json").read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {
                "problem_description": "x",
                "requested_model_type": None,
                "findings": [],
                "refusals": [],
                "cross_model_matches": [],
                "human_review_required": True,
                "artifacts": ["fault_history_report.json", "fault_history_report.md"],
            },
            fh,
        )


def test_violation_l3_interactive_rejected(tmp_path: Path) -> None:
    """3-lens P2：L3 挂 interactive 包=永久没有人签闸可兑现（会话运行时无
    waiting_review 状态机）——装载期同样拒载，不止咬 job 未开 rhr 一种姿势。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("policy_qa_agent", agents_dir, "policy_qa_agent")
    _patch_yaml(pkg, **{"expertise.usefulness_level": "L3"})
    reg = _scan(agents_dir)
    assert reg.get("policy_qa_agent") is None, "L3+interactive 竟被注册——人签闸无处兑现"
    assert len(reg.errors) == 1
    assert "L3" in reg.errors[0]["error"]


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
