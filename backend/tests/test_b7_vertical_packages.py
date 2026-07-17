"""批七三垂类包（policy_qa / standards_qa / fault_history）行为测试。

Codex 落地、本文件为异源持久化验证（自报自测 ≠ 可复验证据）。直接驱动
workflow.run()（与 runtime 装载同一入口），不经 HTTP——registry 装载不变量
已由 test_b7_expert_contract.py 全舰队覆盖。

tamper witness：
- 移除 fault workflow 的未收录型号拒答分支 → test_fault_uncovered 翻转。
- 放开 _parse_ranking 白名单校验 → test_fault_ranked_outside_whitelist 翻转。
- 把 evidence resolved 改为 LLM 可自报 true → schema const false 用例翻转。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from backend.app.config import REPO_ROOT


def _load_wf(agent_id: str):
    wf_path = REPO_ROOT / "agents" / agent_id / "workflow.py"
    spec = importlib.util.spec_from_file_location(f"{agent_id}_b7_test", wf_path)
    wf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wf)
    return wf


class _Events:
    def __init__(self) -> None:
        self.logged: list[tuple[str, dict[str, Any]]] = []

    def log(self, kind: str, payload: dict[str, Any]) -> None:
        self.logged.append((kind, payload))


class _Gateway:
    """canned 回复网关；未预期调用（拒答路径不该调模型）时 fail-loud。"""

    def __init__(self, content: str | None = None) -> None:
        self._content = content
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, profile: str, messages: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
        if self._content is None:
            raise AssertionError("该路径不应调用模型（拒答须在确定性层完成）")
        self.calls.append(messages)
        return {"content": self._content, "finish_reason": "stop"}


def _agent_config(agent_id: str) -> dict[str, Any]:
    return {"id": agent_id, "model": {"profile": "reasoning"}}


def _fault_ctx(tmp_path: Path, gateway: _Gateway, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_logger": _Events(),
        "model_gateway": gateway,
        "inputs": inputs,
        "output_dir": str(tmp_path),
        "agent_config": _agent_config("fault_history_agent"),
    }


# ── fault_history：确定性检索 + 白名单排序 ─────────────────────────────────

def test_fault_uncovered_model_refuses_without_model_call(tmp_path):
    wf = _load_wf("fault_history_agent")
    gateway = _Gateway(content=None)  # 调用即 fail
    result = wf.run(_fault_ctx(tmp_path, gateway, {
        "problem_description": "热浸后间歇断电，冷却后恢复。",
        "model_type": "海岚-9",
    }))
    assert result["status"] == "success"
    out = result["outputs"][0]
    assert out["findings"] == []
    assert len(out["refusals"]) >= 1
    assert "海岚-9" in out["refusals"][0]["reason"]
    # 产物已落盘且过自身 output_schema（_write_outputs 内联 validate）
    assert (tmp_path / "fault_history.json").exists()
    assert (tmp_path / "fault_history.md").exists()


def test_fault_normal_path_findings_unresolved_and_cross_model(tmp_path):
    wf = _load_wf("fault_history_agent")
    problem = "XR-100 连续运行两小时后间歇断电并母线复位，热浸复现，冷却后恢复，怀疑接插件接触阻抗波动。"
    # 先确定性选出候选，再用其中真实 fault_ref 构造合法排序回复（含跨型号）
    probe = wf._select_candidates(
        wf._load_json("data", "fault_cases.json")["cases"], problem, "XR-100"
    )
    assert len(probe) >= 2, "语料应对该现象检出多条候选（含跨型号）"
    ranked_reply = json.dumps({"ranked": [
        {"fault_ref": c["fault_ref"], "similarity_basis": "现象与触发条件标签重合",
         "disposition_summary": "合成记录处置摘要，仅供人工比对。"}
        for c in probe[:3]
    ]}, ensure_ascii=False)
    gateway = _Gateway(content=ranked_reply)
    result = wf.run(_fault_ctx(tmp_path, gateway, {
        "problem_description": problem, "model_type": "XR-100",
    }))
    assert result["status"] == "success"
    out = result["outputs"][0]
    assert len(out["findings"]) >= 1
    for f in out["findings"]:
        for ev in f["evidence"]:
            assert ev["resolved"] is False, "resolved 置位权在后端回源，LLM 路径恒 false"
    assert out["human_review_required"] is True
    if any(c["model"] != "XR-100" for c in probe[:3]):
        assert len(out["cross_model_matches"]) >= 1, "跨型号候选必须落 cross_model_matches"
    assert len(gateway.calls) == 1
    assert "只能从这些 fault_ref 中选择" in gateway.calls[0][-1]["content"]


def test_fault_ranked_outside_whitelist_fails_honestly(tmp_path):
    wf = _load_wf("fault_history_agent")
    fabricated = json.dumps({"ranked": [
        {"fault_ref": "SYN-FH-FAKE-999", "similarity_basis": "编造", "disposition_summary": "编造"}
    ]})
    result = wf.run(_fault_ctx(tmp_path, _Gateway(content=fabricated), {
        "problem_description": "XR-100 间歇断电，热浸复现，冷却后恢复。",
        "model_type": "XR-100",
    }))
    assert result["status"] == "failed", "白名单外 fault_ref 必须诚实失败，绝不落盘编造案例"
    assert not (tmp_path / "fault_history.json").exists()


# ── policy_qa / standards_qa：结构化契约不满足 → 降级显式拒答 ────────────────

@pytest.mark.parametrize("agent_id", ["policy_qa_agent", "standards_qa_agent"])
def test_interactive_qa_invalid_payload_degrades_to_refusal(agent_id):
    wf = _load_wf(agent_id)
    result = wf.run({
        "messages": [{"role": "user", "content": "质量记录保存年限是多少？"}],
        "model_gateway": _Gateway(content="就是五年，放心。"),  # 自由文本，无结构块
        "agent_config": _agent_config(agent_id),
    })
    reco = result["recommendation"]
    assert reco["findings"] == []
    assert len(reco["refusals"]) >= 1, "无法过 output_schema 的回复必须降级为显式拒答"
    # 拒答 payload 本身也须过包内 output_schema（拒答不是逃生舱）
    from jsonschema import validate
    schema = json.loads(
        (REPO_ROOT / "agents" / agent_id / "output_schema.json").read_text(encoding="utf-8")
    )
    validate(reco, schema)


def test_standards_dual_evidence_payload_passes_through():
    wf = _load_wf("standards_qa_agent")
    payload = {
        "answer": "定位到条款与机型实例线索，供人工核对。",
        "findings": [{
            "claim": "紧固件防松要求见合成标准 SYN-STD-201 §4.2；SYN-TYPE-XR100-07 有同类实例。",
            "evidence": [
                {"kind": "standard_clause", "source_ref": "SYN-STD-201 §4.2",
                 "quote": "合成条款检索线索（非原文）", "resolved": False},
                {"kind": "type_case", "source_ref": "SYN-TYPE-XR100-07",
                 "quote": "合成机型实例检索线索（非原文）", "resolved": False},
            ],
            "confidence": {"level": "medium", "basis": "双源(条款+机型实例)"},
        }],
        "refusals": [],
    }
    result = wf.run({
        "messages": [{"role": "user", "content": "紧固件防松的标准依据？"}],
        "model_gateway": _Gateway(content=json.dumps(payload, ensure_ascii=False)),
        "agent_config": _agent_config("standards_qa_agent"),
    })
    reco = result["recommendation"]
    assert len(reco["findings"]) == 1
    kinds = {ev["kind"] for ev in reco["findings"][0]["evidence"]}
    assert kinds == {"standard_clause", "type_case"}, "双依据（条款+机型实例）须原样保留"


def test_qa_llm_cannot_self_report_resolved_true():
    """resolved=true 只能由后端回源指纹置位（ADR-0029/0030）——LLM 自报必被
    schema const:false 拒绝并降级拒答，绝不放行假『已核验』。"""
    wf = _load_wf("policy_qa_agent")
    payload = {
        "answer": "已核验的制度结论。",
        "findings": [{
            "claim": "合成制度 SYN-POL-001 规定保存五年。",
            "evidence": [{"kind": "knowledge_doc", "source_ref": "SYN-POL-001",
                          "quote": "合成目录线索", "resolved": True}],
            "confidence": {"level": "high", "basis": "自报已核验"},
        }],
        "refusals": [],
    }
    result = wf.run({
        "messages": [{"role": "user", "content": "记录保存几年？"}],
        "model_gateway": _Gateway(content=json.dumps(payload, ensure_ascii=False)),
        "agent_config": _agent_config("policy_qa_agent"),
    })
    reco = result["recommendation"]
    assert reco["findings"] == [], "resolved=true 自报必须整体降级，不得部分放行"
    assert len(reco["refusals"]) >= 1
