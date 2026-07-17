"""批七 S2：POST /api/tasks/batch（全有全无+after 映射）+ 密级准入 gate + guide after 剥离降级。

tamper witness：
- O4 族：注释掉 create_task/batch 的 clearance gate 判定 → 拒建用例红→绿翻转。
- O8 族：移除 guide _validate_orchestrate 的 after 剥离逻辑 → stripped 用例翻转。
- 全有全无：破坏 batch 的先收集后拒（改为逐项即建）→ 零写入断言咬。
"""

from __future__ import annotations

import importlib.util
from typing import Any

from backend.app.config import REPO_ROOT
from backend.app.storage import repos


def _mk_item(name: str, **extra) -> dict[str, Any]:
    item = {"agent_id": "hello_agent", "name": name, "inputs": {"name": name}}
    item.update(extra)
    return item


def _seed_input_file(app, file_id: str, classification: str) -> str:
    conn = app.state.conn_factory()
    try:
        rec = repos.create_file(
            conn,
            file_id=file_id,
            task_id=None,
            kind="input",
            filename=f"{file_id}.txt",
            path=f"/nonexistent/{file_id}.txt",
            size_bytes=10,
            sha256="0" * 64,
            classification=classification,
        )
        return rec["id"]
    finally:
        conn.close()


# ── batch：after 下标 → 真 depends_on 映射 + 条件短路 ───────────────────────

def test_batch_after_maps_depends_on_and_holds_created(app_env):
    client, _ = app_env
    r = client.post("/api/tasks/batch", json={"items": [
        _mk_item("上游"),
        _mk_item("下游", after=[0]),
    ]})
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["status"] == "queued", "无依赖项保持 P2-4 原子入队"
    assert tasks[1]["status"] == "created", "带依赖项滞留 created 待 resolver"
    assert tasks[1]["depends_on"] == [tasks[0]["id"]], "after 下标必须映射为真 task_id"


def test_batch_all_or_nothing_zero_writes(app_env):
    client, _ = app_env
    before = len(client.get("/api/tasks").json())
    r = client.post("/api/tasks/batch", json={"items": [
        _mk_item("好的"),
        _mk_item("坏的", agent_id="no_such_agent_xyz"),
    ]})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["batch_errors"][0]["index"] == 1
    assert "no_such_agent_xyz" in detail["batch_errors"][0]["errors"][0]
    after = len(client.get("/api/tasks").json())
    assert after == before, "全有全无：任一项非法必须零写入，绝不半建"


def test_batch_self_or_forward_after_rejected(app_env):
    client, _ = app_env
    r = client.post("/api/tasks/batch", json={"items": [
        _mk_item("自引", after=[0]),
    ]})
    assert r.status_code == 422
    assert "after 下标" in str(r.json()["detail"])


# ── 密级准入 gate（ADR-0030，O4 族）────────────────────────────────────────

def test_clearance_gate_blocks_sensitive_input_on_create(app_env):
    """hello_agent 无 clearance 声明 → 缺省上限 internal → sensitive 材料 400 拒建。"""
    client, app = app_env
    fid = _seed_input_file(app, "file_b7_sens", "sensitive")
    r = client.post("/api/tasks", json={
        "agent_id": "hello_agent", "inputs": {"name": "x"}, "input_file_ids": [fid],
    })
    assert r.status_code == 400
    assert "密级准入上限" in r.json()["detail"]


def test_clearance_gate_allows_internal_input(app_env):
    client, app = app_env
    fid = _seed_input_file(app, "file_b7_int", "internal")
    r = client.post("/api/tasks", json={
        "agent_id": "hello_agent", "inputs": {"name": "x"}, "input_file_ids": [fid],
    })
    assert r.status_code == 200, "internal 材料 + 缺省 internal 上限必须放行（gate 有判别力非全拒）"


def test_clearance_gate_blocks_in_batch_path(app_env):
    """batch 路径同 gate（防旁路）：sensitive 项计入 batch_errors，整批零写入。"""
    client, app = app_env
    fid = _seed_input_file(app, "file_b7_sens2", "sensitive")
    before = len(client.get("/api/tasks").json())
    r = client.post("/api/tasks/batch", json={"items": [
        _mk_item("干净的"),
        _mk_item("越级的", input_file_ids=[fid]),
    ]})
    assert r.status_code == 422
    assert "密级准入上限" in str(r.json()["detail"]["batch_errors"])
    assert len(client.get("/api/tasks").json()) == before


def test_clearance_missing_file_record_fails_closed(app_env):
    """输入文件记录缺失 → 材料级 sensitive（出处不可考宁严勿洗白）→ 缺省上限拒。"""
    client, _ = app_env
    r = client.post("/api/tasks", json={
        "agent_id": "hello_agent", "inputs": {"name": "x"},
        "input_file_ids": ["file_never_uploaded"],
    })
    assert r.status_code == 400
    assert "sensitive" in r.json()["detail"]


# ── guide after 剥离降级（O8 族）────────────────────────────────────────────

def _load_wf():
    wf_path = REPO_ROOT / "agents" / "guide_agent" / "workflow.py"
    spec = importlib.util.spec_from_file_location("guide_wf_b7_test", wf_path)
    wf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wf)
    return wf


class _NoSchemaRegistry:
    def package_dir(self, agent_id):
        return None


_CANDS = [
    {"id": "a_one", "name": "甲", "category": "tool_automation", "status": "released", "maturity": "L1"},
    {"id": "a_two", "name": "乙", "category": "tool_automation", "status": "released", "maturity": "L1"},
    {"id": "a_three", "name": "丙", "category": "tool_automation", "status": "released", "maturity": "L1"},
]


def _entry(agent_id: str, **extra) -> dict[str, Any]:
    e = {"agent_id": agent_id, "role": "r", "rationale": "x", "prefilled_inputs": {}}
    e.update(extra)
    return e


def _plan(agents: list[dict[str, Any]]) -> dict[str, Any]:
    return {"decision": "orchestrate", "analysis": "a", "goal": "g", "workflow": "w", "agents": agents}


def test_guide_after_valid_chain_kept():
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("a_one"), _entry("a_two", after=[0])]), _NoSchemaRegistry(), _CANDS
    )
    assert result is not None
    assert result["agents"][0]["after"] == []
    assert result["agents"][1]["after"] == [0]
    assert "after" not in result["agents"][1]["stripped_fields"]


def test_guide_after_remaps_across_dropped_entries():
    """原始下标 2 的成员 after=[1]——下标 0 是幻觉被剪，重映射后指向最终下标 0。"""
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("ghost_agent"), _entry("a_one"), _entry("a_two", after=[1])]),
        _NoSchemaRegistry(), _CANDS,
    )
    assert result is not None
    assert [a["agent_id"] for a in result["agents"]] == ["a_one", "a_two"]
    assert result["agents"][1]["after"] == [0], "raw→final 重映射必须落到存活条目"


def test_guide_after_invalid_ref_stripped_whole():
    """引用被剪条目 → 整个 after 剥离为无依赖 + stripped_fields 留痕（绝不半保留）。"""
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("ghost_agent"), _entry("a_one"), _entry("a_two", after=[0, 1])]),
        _NoSchemaRegistry(), _CANDS,
    )
    assert result is not None
    assert result["agents"][1]["after"] == []
    assert "after" in result["agents"][1]["stripped_fields"]


def test_guide_after_forward_ref_stripped():
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("a_one", after=[1]), _entry("a_two")]), _NoSchemaRegistry(), _CANDS
    )
    assert result is not None
    assert result["agents"][0]["after"] == []
    assert "after" in result["agents"][0]["stripped_fields"]


def test_guide_after_non_int_stripped():
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("a_one"), _entry("a_two", after=["0"])]), _NoSchemaRegistry(), _CANDS
    )
    assert result is not None
    assert result["agents"][1]["after"] == []
    assert "after" in result["agents"][1]["stripped_fields"]
