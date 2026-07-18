"""批八 teams 团队模板：存蓝本 + summon 对账 gate G1-G5 + seq 重排 + 执行期
disabled 兜底（loop-auditor F1/F2/F3 的后端回归面）。

tamper witness：
- summon 对账循环判定短路 → G1-G4 各用例翻转（TB1 e2e 侧另咬）。
- seq 升序重排删掉、直译提交序 → 乱序用例翻转。
- runtime._execute 的 disabled 检查注释掉 → O9 用例翻转。
"""

from __future__ import annotations

from typing import Any

from backend.app.jobs.runner import JobRunner
from backend.app.storage import repos


def _mk_conv_with_plan(app, agents_plan: list[dict[str, Any]], conv_id: str = "conv_b8") -> str:
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn, conversation_id=conv_id, agent_id="guide_agent", created_by="tester"
        )
        repos.set_conversation_recommendation(
            conn, conv_id, {"decision": "orchestrate", "goal": "验收目标", "agents": agents_plan}
        )
        return conv_id
    finally:
        conn.close()


_PLAN = [
    {"agent_id": "hello_agent", "role": "上游打招呼"},
    {"agent_id": "hello_agent", "role": "下游接力", "after": [0]},
]


def _save_team(client, app, name: str = "验收团队") -> dict[str, Any]:
    conv_id = _mk_conv_with_plan(app, _PLAN)
    r = client.post("/api/teams", json={"name": name, "conversation_id": conv_id})
    assert r.status_code == 200, r.text
    return r.json()


def _task_count(client) -> int:
    return len(client.get("/api/tasks").json())


# ── 存蓝本 ──────────────────────────────────────────────────────────────────

def test_create_team_from_plan_roundtrip(app_env):
    client, app = app_env
    team = _save_team(client, app)
    assert team["name"] == "验收团队"
    assert [m["seq"] for m in team["members"]] == [0, 1]
    assert team["members"][1]["after"] == [0]
    assert team["members"][0]["agent_version_at_save"] == "0.1.0"
    listed = client.get("/api/teams").json()
    assert any(t["id"] == team["id"] for t in listed)
    detail = client.get(f"/api/teams/{team['id']}").json()
    assert detail["members"][1]["after"] == [0]
    assert detail["clearance_display"] in ("public", "internal", "sensitive")


def test_create_team_requires_orchestrate_plan(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn, conversation_id="conv_plain", agent_id="guide_agent", created_by="tester"
        )
    finally:
        conn.close()
    r = client.post("/api/teams", json={"name": "空方案", "conversation_id": "conv_plain"})
    assert r.status_code == 422
    assert "orchestrate" in r.text


# ── summon 对账 gate（G1-G5，auditor F2 逐条专属证明）──────────────────────

def test_summon_seat_mismatch_rejected_G5(app_env):
    client, app = app_env
    team = _save_team(client, app)
    before = _task_count(client)
    r = client.post(
        f"/api/teams/{team['id']}/summon",
        json={"items": [{"seq": 0, "inputs": {"name": "只来一半"}}]},
    )
    assert r.status_code == 422
    assert "缺席位" in r.text
    assert _task_count(client) == before, "对账不过必须零写入"


def test_summon_disabled_member_rejected_G2(app_env):
    client, app = app_env
    team = _save_team(client, app)
    agent = app.state.agent_registry.get("hello_agent")
    agent["status"] = "disabled"
    try:
        before = _task_count(client)
        r = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "a"}}, {"seq": 1, "inputs": {"name": "b"}}]},
        )
        assert r.status_code == 422
        assert "已下线" in r.text
        assert _task_count(client) == before
    finally:
        agent["status"] = "active"


def test_summon_unregistered_member_rejected_G1(app_env):
    client, app = app_env
    team = _save_team(client, app)
    app.state.agent_registry.deregister("hello_agent", "b8 测试卸载")
    r = client.post(
        f"/api/teams/{team['id']}/summon",
        json={"items": [{"seq": 0, "inputs": {"name": "a"}}, {"seq": 1, "inputs": {"name": "b"}}]},
    )
    assert r.status_code == 422
    assert "不在注册表" in r.text


def test_summon_interactive_flip_rejected_G3(app_env):
    client, app = app_env
    team = _save_team(client, app)
    agent = app.state.agent_registry.get("hello_agent")
    original_mode = agent["workflow"]["mode"]
    agent["workflow"]["mode"] = "interactive"
    try:
        r = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "a"}}, {"seq": 1, "inputs": {"name": "b"}}]},
        )
        assert r.status_code == 422
        assert "interactive" in r.text
    finally:
        agent["workflow"]["mode"] = original_mode


def test_summon_version_drift_G4(app_env):
    client, app = app_env
    team = _save_team(client, app)
    agent = app.state.agent_registry.get("hello_agent")
    try:
        # 0.x 期 minor 变化 → 拒
        agent["version"] = "0.2.0"
        r = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "a"}}, {"seq": 1, "inputs": {"name": "b"}}]},
        )
        assert r.status_code == 422
        assert "版本漂移" in r.text
        # patch 变化 → 放行 + warnings 如实列名
        agent["version"] = "0.1.1"
        r2 = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "a"}}, {"seq": 1, "inputs": {"name": "b"}}]},
        )
        assert r2.status_code == 200, r2.text
        assert any("0.1.0 → 0.1.1" in w for w in r2.json()["warnings"])
    finally:
        agent["version"] = "0.1.0"


# ── summon 成功链 + seq 重排（auditor F3）──────────────────────────────────

def test_summon_reverse_order_items_builds_correct_deps(app_env):
    """乱序提交（items 逆 seq 序）→ 依赖边仍正确：下游 depends_on=[上游真 task_id]、
    上游 queued、下游滞留 created。直译提交序的实现此处必翻。"""
    client, app = app_env
    team = _save_team(client, app)
    r = client.post(
        f"/api/teams/{team['id']}/summon",
        json={"items": [
            {"seq": 1, "inputs": {"name": "下游先提交"}},
            {"seq": 0, "inputs": {"name": "上游后提交"}},
        ]},
    )
    assert r.status_code == 200, r.text
    tasks = r.json()["tasks"]
    assert len(tasks) == 2
    upstream, downstream = tasks[0], tasks[1]  # 内核按 seq 升序建行
    assert upstream["inputs"]["name"] == "上游后提交"
    assert upstream["status"] == "queued"
    assert downstream["status"] == "created"
    assert downstream["depends_on"] == [upstream["id"]]


# ── 执行期 disabled 兜底（auditor F1 真修，O9 后端半）──────────────────────

def test_execute_disabled_agent_fails_honestly_O9(app_env):
    """任务入队后 agent 被禁用（版本不变）→ 执行期诚实 failed 不硬跑——修前
    _execute 只查未注册+版本漂移，禁用成员任务照跑（B7 继承缺口）。"""
    client, app = app_env
    r = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "x"}})
    assert r.status_code == 200, r.text
    task_id = r.json()["id"]
    agent = app.state.agent_registry.get("hello_agent")
    agent["status"] = "disabled"
    try:
        runner = JobRunner(app.state.runtime, app.state.conn_factory)
        runner.run_once()
        conn = app.state.conn_factory()
        try:
            task = repos.get_task(conn, task_id)
        finally:
            conn.close()
        assert task["status"] == "failed"
        assert "已下线" in (task.get("error_message") or "")
    finally:
        agent["status"] = "active"


# ── Codex R0 修复回归（P1 钉版本 / P2 材料校验 / P3 缺位密级展示）──────────

def test_summon_oversized_inputs_translated_422_not_500(app_env):
    """SummonItem 不带 BatchTaskItem 的 inputs 尺寸 validator——构造时的
    ValidationError 必须译成结构化 422（材料不合法清单），绝不放大成 500。"""
    client, app = app_env
    team = _save_team(client, app)
    before = _task_count(client)
    r = client.post(
        f"/api/teams/{team['id']}/summon",
        json={"items": [
            {"seq": 0, "inputs": {"name": "x" * (300 * 1024)}},
            {"seq": 1, "inputs": {"name": "b"}},
        ]},
    )
    assert r.status_code == 422, r.text
    assert "材料不合法" in r.text
    assert _task_count(client) == before, "材料校验不过必须零写入"


def test_run_batch_creation_pinned_version_mismatch_rejects(app_env):
    """钉版本校验（Codex R0 P1）：对账时点观察到的版本与创建时 registry 现势不一
    致 → 整批 422 零写入——闭「对账后热切换新版被盖进任务→runtime 漂移复检恒过」
    的 TOCTOU 旁路。"""
    import pytest
    from fastapi import HTTPException

    from backend.app.api.tasks import BatchTaskItem, run_batch_creation

    client, app = app_env
    conn = app.state.conn_factory()
    try:
        with pytest.raises(HTTPException) as exc_info:
            run_batch_creation(
                conn=conn,
                agent_registry=app.state.agent_registry,
                items=[BatchTaskItem(agent_id="hello_agent", inputs={"name": "x"})],
                conversation_id=None,
                created_by="tester",
                created_by_username="tester",
                pinned_versions={"hello_agent": "9.9.9"},
            )
        assert exc_info.value.status_code == 422
        assert "版本在对账后发生变化" in str(exc_info.value.detail)
    finally:
        conn.close()
    # 版本一致 → 正常放行（pinned 校验不误伤）
    conn = app.state.conn_factory()
    try:
        current = app.state.agent_registry.get("hello_agent").get("version")
        result = run_batch_creation(
            conn=conn,
            agent_registry=app.state.agent_registry,
            items=[BatchTaskItem(agent_id="hello_agent", inputs={"name": "x"})],
            conversation_id=None,
            created_by="tester",
            created_by_username="tester",
            pinned_versions={"hello_agent": current},
        )
        assert len(result["tasks"]) == 1
    finally:
        conn.close()


def test_projection_missing_member_counts_as_internal(app_env):
    """缺位成员按最保守 internal 参与团队密级 min（Codex R0 P3）：全员卸载后
    clearance_display 必须落 internal，不得虚标 sensitive。"""
    client, app = app_env
    team = _save_team(client, app)
    app.state.agent_registry.deregister("hello_agent", "b8 P3 测试卸载")
    detail = client.get(f"/api/teams/{team['id']}").json()
    assert all(m["present"] is False for m in detail["members"])
    assert detail["clearance_display"] == "internal"
