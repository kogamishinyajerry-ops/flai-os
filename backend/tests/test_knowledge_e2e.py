"""knowledge 内核服务端到端集成测试（ADR-0015 收口件）。

走真实 FastAPI TestClient + JobRunner：临时 Agent 包（knowledge_qa 类，
enabled: true）经 /api/tasks 建任务 → runner 真跑 workflow → workflow 经
context["knowledge"] 检索临时 scope → 断言命中带出处、knowledge_search 事件
落 task_events 且逐条过 event.schema.json、越权 scope 被 default-deny 拒绝、
reconcile 违规 Agent 在 API 层不可见不可建任务。

fixture 全部 tmp_path 现造，不依赖真实 agents/ 与 data/（不受其他里程碑
在途改动影响）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import validate

from conftest import seed_and_login

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"

EVENT_SCHEMA = json.loads((CONTRACTS_DIR / "event.schema.json").read_text(encoding="utf-8"))

_PROBE_WORKFLOW = '''
import json
import os


def run(context):
    """探针 workflow：检索指定 scope 并把命中落盘（e2e 断言出处用）。"""
    scope_id = context["inputs"].get("scope_override") or "probe_scope"
    hits = context["knowledge"].search(scope_id, context["inputs"]["query"], top_k=3)
    out = os.path.join(context["output_dir"], "hits.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(hits, f, ensure_ascii=False)
    return {"status": "success", "outputs": [{"hit_count": len(hits)}]}
'''


def _write_agent_package(agents_dir: Path, agent_id: str, *, knowledge: dict[str, Any]) -> None:
    """按 docs/02 强制件清单现造最小合法 Agent 包（agent.yaml 过 schema 校验）。"""
    pkg = agents_dir / agent_id
    (pkg / "eval_cases").mkdir(parents=True)
    manifest = {
        "id": agent_id,
        "name": f"knowledge e2e 探针 {agent_id}",
        "version": "0.1.0",
        "status": "draft",
        "maturity": "L0",
        "category": "knowledge_qa",
        "summary": "e2e 测试探针：经 context['knowledge'] 检索并落盘命中，无业务含义。",
        "owner": {"department": "二所", "maintainer": "TBD", "business_reviewer": "TBD"},
        "model": {"profile": "none"},
        "knowledge": knowledge,
        "tools": [],
        "input": {"type": "params", "schema": "input_schema.json"},
        "output": {"formats": [".json"], "schema": "output_schema.json"},
        "workflow": {"entrypoint": "workflow.py", "mode": "job", "requires_human_review": False},
        "permissions": {"visibility": "admin_only", "allowed_roles": ["admin"]},
        "logging": {
            "save_inputs": True, "save_outputs": True, "save_tool_logs": True,
            "save_model_calls": True, "save_feedback": True,
        },
        "data_asset": {"collect_samples": False},
        "limitations": ["e2e 测试探针，无业务含义。"],
    }
    (pkg / "agent.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    (pkg / "workflow.py").write_text(_PROBE_WORKFLOW, encoding="utf-8")
    (pkg / "input_schema.json").write_text(json.dumps({
        "type": "object", "additionalProperties": False, "required": ["query"],
        "properties": {"query": {"type": "string", "minLength": 1},
                       "scope_override": {"type": "string"}},
    }), encoding="utf-8")
    (pkg / "output_schema.json").write_text(json.dumps({
        "type": "object", "properties": {"hit_count": {"type": "integer"}},
    }), encoding="utf-8")
    (pkg / "prompt.md").write_text("e2e 探针（0-LLM）。", encoding="utf-8")
    (pkg / "README.md").write_text("e2e 探针。", encoding="utf-8")
    (pkg / "changelog.md").write_text("0.1.0 初版。", encoding="utf-8")
    (pkg / "eval_cases" / "case_001.json").write_text(
        json.dumps({"inputs": {"query": "排液孔"}}), encoding="utf-8")


def _write_scope(knowledge_dir: Path, scope_id: str, docs: dict[str, str]) -> None:
    scope = knowledge_dir / scope_id
    (scope / "docs").mkdir(parents=True)
    (scope / "scope.yaml").write_text(yaml.safe_dump({
        "scope_id": scope_id,
        "name": f"e2e scope {scope_id}",
        "kind": "document",
        "source": "file_dir",
        "path_or_uri": "docs",
        "confidentiality": "public_internal",
        "owner": "e2e",
    }, allow_unicode=True), encoding="utf-8")
    for name, text in docs.items():
        (scope / "docs" / name).write_text(text, encoding="utf-8")


@pytest.fixture()
def app_env(tmp_path) -> Iterator[tuple[TestClient, Any]]:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent_package(agents_dir, "knowledge_probe",
                         knowledge={"enabled": True, "scopes": ["probe_scope"]})
    # 违规包：引用未注册 scope，装配对账应把它整包拒掉（reconcile e2e 钥匙）。
    _write_agent_package(agents_dir, "knowledge_violator",
                         knowledge={"enabled": True, "scopes": ["ghost_scope"]})
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    knowledge_dir = tmp_path / "knowledge"
    # ≥4 篇文档：N=2 的小语料里出现在 1 篇的词 idf=ln(1)=0 会被 score>0 过滤
    # 吞掉一切命中（BM25 复刻件与参考实现一致的退化，FDE retro 教训"样例 ≥4 文档"）。
    _write_scope(knowledge_dir, "probe_scope", {
        "em.md": "短舱排液孔堵塞的处置：先查排液孔是否有异物，再对照 EM 手册章节。",
        "ecm.md": "历史 ECM 记录：滑油滤压差告警多与滤芯堵塞相关。",
        "ballast1.md": "起动机更换后需要进行台架测试验证转速指标。",
        "ballast2.md": "燃油系统例行维护包括滤芯更换与管路目视检查。",
    })
    # 已注册但不在 probe 白名单内的 scope（default-deny 越权钥匙）。
    _write_scope(knowledge_dir, "other_scope", {"doc.md": "另一范围的内容。"})

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=tools_dir,
        contracts_dir=CONTRACTS_DIR,
        knowledge_dir=knowledge_dir,
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        yield client, app


def _create_and_run(client: TestClient, app, agent_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(
        "/api/tasks", json={"agent_id": agent_id, "inputs": inputs}
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]
    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True
    return client.get(f"/api/tasks/{task_id}").json()


def test_e2e_search_hits_with_provenance_and_events(app_env) -> None:
    """happy path：任务 completed；hits.json 出处双钥全非空；knowledge_search
    info 事件带 hit_count/hit_chunk_ids；全部事件逐条过 event.schema.json
    （knowledge_search 枚举漏改契约会在此咬住）。"""
    client, app = app_env
    task = _create_and_run(client, app, "knowledge_probe", {"query": "排液孔堵塞怎么处置"})
    assert task["status"] == "completed", task

    out_dir = Path(app.state.task_runs_dir) / task["id"] / "output"
    hits = json.loads((out_dir / "hits.json").read_text(encoding="utf-8"))
    assert len(hits) >= 1
    for h in hits:
        assert h["scope_id"] == "probe_scope"
        for key in ("chunk_id", "source", "fingerprint"):
            assert isinstance(h[key], str) and h[key].strip() != ""
        assert h["source"].endswith(".md")

    events = client.get(f"/api/tasks/{task['id']}/events").json()
    for e in events:
        validate(e, EVENT_SCHEMA)
    ks = [e for e in events if e["event_type"] == "knowledge_search"]
    assert len(ks) == 1
    assert ks[0]["level"] == "info"
    payload = ks[0]["payload"]
    assert payload["scope_id"] == "probe_scope"
    assert payload["hit_count"] == len(hits)
    assert payload["hit_chunk_ids"] == [h["chunk_id"] for h in hits]
    # 四钥 hit_citations 精确断言（Codex 治理审 R2 P1，防假绿）：删掉 runtime 里
    # hit_citations 的构造代码必须让本断言 RED——逐命中 chunk_id/source/fingerprint
    # 三钥齐全非空，且与 hits.json 出处逐一对齐（N7 一键回源+漂移比对的数据源）。
    cits = payload["hit_citations"]
    assert isinstance(cits, list) and len(cits) == len(hits)
    for cit, h in zip(cits, hits):
        assert cit["chunk_id"] == h["chunk_id"]
        assert cit["source"] == h["source"] and cit["source"].strip() != ""
        assert cit["fingerprint"] == h["fingerprint"] and cit["fingerprint"].strip() != ""


def test_e2e_scope_not_in_whitelist_denied_with_event(app_env) -> None:
    """default-deny 越权钥匙：other_scope 已注册但不在 probe 白名单 → 任务
    failed，knowledge_search error 事件带 denied 标注（拒绝也必须留痕）。"""
    client, app = app_env
    task = _create_and_run(client, app, "knowledge_probe",
                           {"query": "任意", "scope_override": "other_scope"})
    assert task["status"] == "failed"
    assert "KnowledgeScopeDeniedError" in (task.get("error_message") or "")

    events = client.get(f"/api/tasks/{task['id']}/events").json()
    denied = [e for e in events if e["event_type"] == "knowledge_search"]
    assert len(denied) == 1
    assert denied[0]["level"] == "error"
    assert denied[0]["payload"]["denied"] == "not_in_agent_scopes"


def test_e2e_reconcile_rejects_violator_at_api(app_env) -> None:
    """reconcile e2e 钥匙：引用未注册 scope 的 Agent 在 /api/agents 不可见，
    create_task 对其 404（deregister 是注册层出口而非仅内存标记）。"""
    client, app = app_env
    ids = [a["id"] for a in client.get("/api/agents").json()]
    assert "knowledge_probe" in ids
    assert "knowledge_violator" not in ids
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "knowledge_violator", "inputs": {"query": "x"}},
    )
    assert resp.status_code == 404
