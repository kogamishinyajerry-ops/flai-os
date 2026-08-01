"""批七 S2：POST /api/tasks/batch（全有全无+after 映射）+ 密级准入 gate + guide after 剥离降级。

tamper witness：
- O4 族：注释掉 create_task/batch 的 clearance gate 判定 → 拒建用例红→绿翻转。
- O8 族：移除 guide _validate_orchestrate 的 after 剥离逻辑 → stripped 用例翻转。
- 全有全无：破坏 batch 的先收集后拒（改为逐项即建）→ 零写入断言咬。
"""

from __future__ import annotations

import importlib.util
import itertools
from typing import Any

from backend.app.config import REPO_ROOT
from backend.app.storage import repos


def _mk_item(name: str, **extra) -> dict[str, Any]:
    item = {"agent_id": "hello_agent", "name": name, "inputs": {"name": name}}
    item.update(extra)
    return item


_BATCH_OPERATION_SEQ = itertools.count(1)


def _batch_payload(app, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Public batch fixtures carry the same atomic package envelope as Guide."""
    versions: dict[str, str] = {}
    digests: dict[str, str] = {}
    for agent_id in {item["agent_id"] for item in items}:
        try:
            snapshot = app.state.agent_registry.package_snapshot(agent_id)
        except KeyError:
            snapshot = None
        versions[agent_id] = (
            snapshot.manifest["version"] if snapshot is not None else "0.0.0"
        )
        digests[agent_id] = snapshot.digest if snapshot is not None else "0" * 64
    return {
        "operation_id": f"b7_contract_{next(_BATCH_OPERATION_SEQ)}",
        "pinned_versions": versions,
        "pinned_package_digests": digests,
        "items": items,
    }


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
    client, app = app_env
    r = client.post("/api/tasks/batch", json=_batch_payload(app, [
        _mk_item("上游"),
        _mk_item("下游", after=[0]),
    ]))
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["status"] == "queued", "无依赖项保持 P2-4 原子入队"
    assert tasks[1]["status"] == "created", "带依赖项滞留 created 待 resolver"
    assert tasks[1]["depends_on"] == [tasks[0]["id"]], "after 下标必须映射为真 task_id"


def test_batch_all_or_nothing_zero_writes(app_env):
    client, app = app_env
    before = len(client.get("/api/tasks").json())
    r = client.post("/api/tasks/batch", json=_batch_payload(app, [
        _mk_item("好的"),
        _mk_item("坏的", agent_id="no_such_agent_xyz"),
    ]))
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["batch_errors"][0]["index"] == 1
    assert "no_such_agent_xyz" in detail["batch_errors"][0]["errors"][0]
    after = len(client.get("/api/tasks").json())
    assert after == before, "全有全无：任一项非法必须零写入，绝不半建"


def test_batch_emits_creation_and_charter_events(app_env):
    """Codex R0 P1/P2：batch 每项落 task_created 事件（status_to 如实）；有 charter
    的 agent 另落 charter_intro 开场白事件（创建时点快照，防包升级伪史）；
    无 charter 的 agent 绝不发空开场白。"""
    client, app = app_env
    r = client.post("/api/tasks/batch", json=_batch_payload(app, [
        {"agent_id": "fault_history_agent", "name": "检索", "inputs": {"problem_description": "液压压力波动"}},
        _mk_item("下游", after=[0]),
    ]))
    assert r.status_code == 200
    tasks = r.json()["tasks"]

    ev0 = client.get(f"/api/tasks/{tasks[0]['id']}/events").json()
    created0 = [e for e in ev0 if e["event_type"] == "task_created"]
    assert len(created0) == 1
    assert created0[0]["payload"]["status_to"] == "queued"
    charter0 = [e for e in ev0 if (e.get("payload") or {}).get("charter_intro") is True]
    assert len(charter0) == 1, "fault_history_agent 声明了 charter，batch 创建须落开场白事件"
    assert "相似不等于适用" in charter0[0]["message"]

    ev1 = client.get(f"/api/tasks/{tasks[1]['id']}/events").json()
    created1 = [e for e in ev1 if e["event_type"] == "task_created"]
    assert len(created1) == 1
    assert created1[0]["payload"]["status_to"] == "created"
    assert [e for e in ev1 if (e.get("payload") or {}).get("charter_intro")] == [], (
        "hello_agent 无 charter，不得编造开场白"
    )


def test_single_create_emits_charter_event(app_env):
    """单建路径与 batch 同款：charter 持久化为创建期事件。"""
    client, _ = app_env
    r = client.post("/api/tasks", json={
        "agent_id": "fault_history_agent",
        "name": "单建检索",
        "inputs": {"problem_description": "液压压力波动"},
    })
    assert r.status_code == 200
    task_id = r.json()["id"]
    events = client.get(f"/api/tasks/{task_id}/events").json()
    charter = [e for e in events if (e.get("payload") or {}).get("charter_intro") is True]
    assert len(charter) == 1
    assert "相似不等于适用" in charter[0]["message"]


def test_batch_self_or_forward_after_rejected(app_env):
    client, app = app_env
    r = client.post("/api/tasks/batch", json=_batch_payload(app, [
        _mk_item("自引", after=[0]),
    ]))
    assert r.status_code == 422
    assert "after 下标" in str(r.json()["detail"])


def test_batch_after_boolean_rejected_not_coerced(app_env):
    """Codex R1 P2：非严格 list[int] 会把 JSON false 静默强转 0——伪造出提交者
    没写的依赖边。StrictInt 下布尔/字符串下标必须 422，且零写入。"""
    client, app = app_env
    before = len(client.get("/api/tasks").json())
    for bad in ([False], [True], ["0"]):
        r = client.post("/api/tasks/batch", json=_batch_payload(app, [
            _mk_item("上游"),
            _mk_item("下游", after=bad),
        ]))
        assert r.status_code == 422, f"after={bad!r} 竟未被拒"
    assert len(client.get("/api/tasks").json()) == before, "非法下标必须零写入"


def test_batch_retry_lineage_persists_on_each_declared_root(app_env):
    """失败任务回到主对话后，自动编排的根任务保留 retry_of；依赖成员只沿
    depends_on 接力，避免把同一旧任务伪装成每个下游成员的直接重跑来源。"""
    client, app = app_env
    origin = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "原失败任务"}},
    )
    assert origin.status_code == 200, origin.text
    origin_id = origin.json()["id"]
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET status = 'failed', error_message = ? WHERE id = ?",
            ("测试构造的真实失败", origin_id),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json=_batch_payload(app, [
            _mk_item("恢复根任务", retry_of=origin_id),
            _mk_item("恢复下游", after=[0]),
        ]),
    )

    assert response.status_code == 200, response.text
    tasks = response.json()["tasks"]
    assert tasks[0]["retry_of"] == origin_id
    assert tasks[1]["retry_of"] is None
    assert tasks[1]["depends_on"] == [tasks[0]["id"]]


def test_batch_retry_lineage_rejects_nonfailed_origin(app_env):
    """retry_of 是失败恢复血缘，不得由 URL 把 queued/completed 任务伪装成重跑来源。"""
    client, app = app_env
    origin = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "仍在排队的任务"}},
    )
    assert origin.status_code == 200, origin.text
    origin_id = origin.json()["id"]
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json=_batch_payload(app, [_mk_item("伪造恢复任务", retry_of=origin_id)]),
    )

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]["batch_errors"]
    assert "只能指向失败任务" in "；".join(errors[0]["errors"])
    assert len(client.get("/api/tasks").json()) == before


def test_batch_dangling_retry_lineage_rejects_whole_batch(app_env):
    """自动重试血缘不可悬空；任一 retry_of 不存在时整批零写入。"""
    client, app = app_env
    before = len(client.get("/api/tasks").json())
    response = client.post(
        "/api/tasks/batch",
        json=_batch_payload(
            app,
            [_mk_item("恢复任务", retry_of="task_missing_retry_origin")],
        ),
    )

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]["batch_errors"]
    assert errors[0]["index"] == 0
    assert "retry_of" in "；".join(errors[0]["errors"])
    assert len(client.get("/api/tasks").json()) == before


# ── 交互附件密级 gate（Codex R2 P1：会话路径与任务路径同受 ADR-0030）───────

class _ConvStub:
    """canned 回复网关；denied 路径不应触达（gate 在 LLM 调用前抛）。"""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, profile, messages, **kw):
        self.calls += 1
        return {"content": "收到，能再说说输入数据的形态吗？", "token_usage": None,
                "model_name": "stub", "finish_reason": "stop"}


def test_interactive_attachment_sensitive_denied_zero_writes(app_env):
    """internal 上限交互 Agent + sensitive 附件 → 400 密级拒绝，零落库零 LLM 调用
    ——此前会话路径只查附件存在性，越级材料直进模型上下文（R2 P1 verbatim）。"""
    client, app = app_env
    stub = _ConvStub()
    app.state.conversation_service.model_gateway = stub
    fid = _seed_input_file(app, "conv-sens-file", "sensitive")
    conv_id = client.post("/api/conversations", json={"agent_id": "guide_agent"}).json()["id"]
    r = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "帮我看这份材料", "file_ids": [fid]},
    )
    assert r.status_code == 400, r.text
    assert "密级准入上限" in r.json()["detail"]
    assert stub.calls == 0, "gate 必须先于 LLM 调用（越级材料不得进上下文）"
    msgs = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    assert msgs == [], "拒绝轮必须零落库"


def test_interactive_attachment_internal_passes_gate(app_env):
    """对照：internal 附件过 gate，会话正常推进（gate 有判别力非全拒）。"""
    client, app = app_env
    app.state.conversation_service.model_gateway = _ConvStub()
    fid = _seed_input_file(app, "conv-int-file", "internal")
    conv_id = client.post("/api/conversations", json={"agent_id": "guide_agent"}).json()["id"]
    r = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "帮我看这份材料", "file_ids": [fid]},
    )
    assert r.status_code == 200, r.text


def test_interactive_attachment_historical_rechecked(app_env):
    """历史在窗附件同受复核：先以 internal 记录入会话，事后该文件被改级
    sensitive（模拟上游改级/污染传播），下一轮即拒——gate 判的是**在窗全部**
    附件而非仅本轮新提交。"""
    client, app = app_env
    app.state.conversation_service.model_gateway = _ConvStub()
    fid = _seed_input_file(app, "conv-flip-file", "internal")
    conv_id = client.post("/api/conversations", json={"agent_id": "guide_agent"}).json()["id"]
    r1 = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "先看这份内部材料", "file_ids": [fid]},
    )
    assert r1.status_code == 200, r1.text
    conn = app.state.conn_factory()
    try:
        conn.execute("UPDATE files SET classification = 'sensitive' WHERE id = ?", (fid,))
        conn.commit()
    finally:
        conn.close()
    r2 = client.post(
        f"/api/conversations/{conv_id}/messages", json={"content": "继续分析"}
    )
    assert r2.status_code == 400, r2.text
    assert "密级准入上限" in r2.json()["detail"]


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
    r = client.post("/api/tasks/batch", json=_batch_payload(app, [
        _mk_item("干净的"),
        _mk_item("越级的", input_file_ids=[fid]),
    ]))
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
    {"id": "a_one", "name": "甲", "category": "tool_automation", "status": "released", "maturity": "L1", "mode": "job", "input_type": "none"},
    {"id": "a_two", "name": "乙", "category": "tool_automation", "status": "released", "maturity": "L1", "mode": "job", "input_type": "none"},
    {"id": "a_three", "name": "丙", "category": "tool_automation", "status": "released", "maturity": "L1", "mode": "job", "input_type": "none"},
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


def test_guide_dropped_prerequisite_closes_whole_plan():
    """依赖图含被剔除成员时不得重映射后开放残缺方案。"""
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("ghost_agent"), _entry("a_one"), _entry("a_two", after=[1])]),
        _NoSchemaRegistry(), _CANDS,
    )
    assert isinstance(result, wf._ClarificationNeeded)
    assert "工作环节" in result.gaps[0][1][0]


def test_guide_after_reference_to_dropped_member_closes_plan():
    """引用被剔除成员说明方案语义已不完整，不能降级成无依赖并继续。"""
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("ghost_agent"), _entry("a_one"), _entry("a_two", after=[0, 1])]),
        _NoSchemaRegistry(), _CANDS,
    )
    assert isinstance(result, wf._ClarificationNeeded)
    assert "工作环节" in result.gaps[0][1][0]


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


def test_guide_after_explicit_empty_is_legal_not_stripped():
    """3-lens P2：显式 `"after": []` 是合法「无依赖」声明——绝不当剥离记名，
    否则前端会向用户口播虚假的「已剔除不合法字段」降级告警。"""
    wf = _load_wf()
    result = wf._validate_orchestrate(
        _plan([_entry("a_one"), _entry("a_two", after=[])]), _NoSchemaRegistry(), _CANDS
    )
    assert result is not None
    assert result["agents"][1]["after"] == []
    assert "after" not in result["agents"][1]["stripped_fields"]


# ── 消费点密级复核（3-lens P1，ADR-0030 双端强制）─────────────────────────────

def test_clearance_reenforced_at_consumption_point(app_env):
    """resolver 管道注入旁路：下游创建时 input_file_ids=[]（材料级 public 恒过
    创建门），事后被注入 sensitive 上游产物——消费点必须重跑同一判定拒执行。"""
    import pytest

    from backend.app.core.errors import FileIntegrityError

    client, app = app_env
    conn = app.state.conn_factory()
    try:
        rec = repos.create_file(
            conn,
            file_id="file_b7_piped_sens",
            task_id=None,
            kind="output",
            filename="piped.json",
            path="/nonexistent/piped.json",
            size_bytes=10,
            sha256="0" * 64,
            classification="sensitive",
        )
        task = {
            "id": "task_b7_downstream",
            "agent_id": "hello_agent",  # 无 clearance 声明 → 缺省上限 internal
            "input_file_ids": [rec["id"]],
            "depends_on": ["task_b7_upstream"],
        }
        package_snapshot = app.state.agent_registry.package_snapshot("hello_agent")
        assert package_snapshot is not None
        with pytest.raises(FileIntegrityError, match="密级复核失败"):
            app.state.runtime._open_input_files(
                conn, task, package_snapshot.manifest
            )
    finally:
        conn.close()


def test_clearance_recheck_uses_the_execution_snapshot_not_live_projection(
    app_env, monkeypatch
):
    """即使活 Registry 投影被放宽，消费门也必须按本次 workflow 的同一快照判定。"""
    import pytest

    from backend.app.core.errors import FileIntegrityError

    _client, app = app_env
    package_snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert package_snapshot is not None
    frozen_agent = package_snapshot.manifest
    monkeypatch.setattr(
        app.state.agent_registry,
        "get",
        lambda _agent_id: {
            **frozen_agent,
            "clearance": {"max_data_classification": "sensitive"},
        },
    )
    conn = app.state.conn_factory()
    try:
        rec = repos.create_file(
            conn,
            file_id="file_b7_snapshot_clearance",
            task_id=None,
            kind="output",
            filename="snapshot-clearance.json",
            path="/nonexistent/snapshot-clearance.json",
            size_bytes=10,
            sha256="0" * 64,
            classification="sensitive",
        )
        task = {
            "id": "task_b7_snapshot_clearance",
            "agent_id": "hello_agent",
            "input_file_ids": [rec["id"]],
            "depends_on": ["task_b7_upstream"],
        }
        with pytest.raises(FileIntegrityError, match="密级复核失败"):
            app.state.runtime._open_input_files(conn, task, frozen_agent)
    finally:
        conn.close()


def test_clearance_consumption_point_lets_internal_reach_provenance(app_env):
    """对照（gate 有判别力非全拒）：internal 材料过密级复核，失败发生在后续
    完整性/来源链校验（报错不含密级字样）——证明消费点复核只咬越级不误杀。"""
    import pytest

    from backend.app.core.errors import FileIntegrityError

    client, app = app_env
    conn = app.state.conn_factory()
    try:
        rec = repos.create_file(
            conn,
            file_id="file_b7_piped_int",
            task_id=None,
            kind="output",
            filename="piped_int.json",
            path="/nonexistent/piped_int.json",
            size_bytes=10,
            sha256="0" * 64,
            classification="internal",
        )
        task = {
            "id": "task_b7_downstream2",
            "agent_id": "hello_agent",
            "input_file_ids": [rec["id"]],
            "depends_on": [],  # 产物未声明依赖 → 应撞 provenance 校验而非密级门
        }
        package_snapshot = app.state.agent_registry.package_snapshot("hello_agent")
        assert package_snapshot is not None
        with pytest.raises(FileIntegrityError) as exc:
            app.state.runtime._open_input_files(
                conn, task, package_snapshot.manifest
            )
        assert "密级复核" not in str(exc.value)
    finally:
        conn.close()
