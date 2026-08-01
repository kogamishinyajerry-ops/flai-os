"""M6 导引 Agent 与 interactive 会话运行时（ADR-0012；M8 编排官化）。

覆盖：
- guide_agent 作为 interactive 型插件注册；两条运行时语义正交（interactive 不建
  一次性任务、非 interactive 不发起会话）。
- 会话链：开启会话 → 逐轮消息 → assistant 回复；stub gateway 注入方式同 M5
  （app.state.conversation_service.model_gateway = stub）。
- **LLM 边界（本里程碑核心）**：计划块经 workflow 确定性对账 Registry + 目标
  input_schema。M8 起计划有两裁决——orchestrate（召集一组 Agent，逐个校验）/
  refuse（显式拒绝）。orchestrate 里幻觉/自身/重复 agent_id 逐个剥离，无合法 Agent
  存活则整份作废（fail-closed）；预填非法字段逐字段剥离记名。
- 人是唯一签发者红线：导引全程不创建任何任务；预填草案由人在 tasks 端点亲手提交。
- 诚实失败（事务性单轮，ADR-0013）：无内网 key（清空 FLAI_LLM_*）=永久配置错
  → 本轮 **503**（非「可重试」）；临时上游故障 → 502「可重试」；均**零消息落库**；
  并发轮冲突 → 409 且零落库。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.requests import Request

from conftest import TEST_DISPLAY_NAME

from backend.app.api.conversations import PostMessageRequest, stream_message
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime import conversation as conversation_mod
from backend.app.core.errors import ModelUpstreamError
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]

_LLM_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")


def _publish_agent_status(app, tmp_path: Path, agent_id: str, status: str) -> None:
    snapshot = app.state.agent_registry.package_snapshot(agent_id)
    assert snapshot is not None
    shadow_root = tmp_path / f"{agent_id}-{status}-shadow"
    shadow_root.mkdir()
    with snapshot.materialized(parent=tmp_path) as frozen_dir:
        package_dir = shadow_root / agent_id
        shutil.copytree(frozen_dir, package_dir)
    yaml_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    manifest["status"] = status
    yaml_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    shadow = AgentRegistry(shadow_root, app.state.agent_registry.schema_path)
    shadow.scan()
    assert shadow.errors == []
    app.state.agent_registry.adopt(shadow)


class _CannedStub:
    """返回一条固定 assistant 文本的 stub gateway；签名对齐导引 workflow 直连调用
    model_gateway.chat(profile, messages)。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        return {"content": self.reply, "token_usage": None, "model_name": "stub", "finish_reason": "stop"}


class _StreamingStub(_CannedStub):
    """按 pieces 真调用 on_delta 的可控网关；可在已发部分内容后诚实失败。"""

    def __init__(self, reply: str, pieces: list[str], error: Exception | None = None) -> None:
        super().__init__(reply)
        self.pieces = pieces
        self.error = error

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        on_delta = kwargs.get("on_delta")
        for piece in self.pieces:
            if callable(on_delta):
                on_delta(piece)
        if self.error is not None:
            raise self.error
        return {
            "content": self.reply,
            "token_usage": None,
            "model_name": "stub",
            "finish_reason": "stop",
        }


class _UntilDisconnectedStreamingStub(_CannedStub):
    """持续发 delta，直到 ASGI disconnect 使 callback 明确失败。"""

    def __init__(self) -> None:
        super().__init__("不应提交")
        self.finished = threading.Event()

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        on_delta = kwargs.get("on_delta")
        try:
            for _ in range(2_000):
                if callable(on_delta):
                    on_delta("片")
                time.sleep(0.001)
        finally:
            self.finished.set()
        return {
            "content": self.reply,
            "token_usage": None,
            "model_name": "stub",
            "finish_reason": "stop",
        }


# ── 计划块构造小工具（M8：<<PLAN>> orchestrate | refuse）──────────────────

def _plan_reply(text: str, plan: dict[str, Any]) -> str:
    return f"{text}\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"


def _agent(agent_id: str, prefilled: dict[str, Any] | None = None, role: str = "负责这一段", rationale: str = "适配理由") -> dict[str, Any]:
    return {"agent_id": agent_id, "role": role, "rationale": rationale, "prefilled_inputs": prefilled or {}}


def _orchestrate(agents: list[dict[str, Any]], analysis: str = "最终分析", goal: str = "达成目标", workflow: str = "先A后B") -> dict[str, Any]:
    return {"decision": "orchestrate", "analysis": analysis, "goal": goal, "workflow": workflow, "agents": agents}


def _refuse(reason: str = "平台没有对口能力", residual: list | None = None, reframe: list | None = None) -> dict[str, Any]:
    return {"decision": "refuse", "reason": reason, "residual_problems": residual or [], "reframe": reframe or []}


def _load_wf():
    """按路径加载 guide workflow 模块，供纯函数级单测（不经 HTTP）。"""
    wf_path = REPO_ROOT / "agents" / "guide_agent" / "workflow.py"
    spec = importlib.util.spec_from_file_location("guide_wf_under_test", wf_path)
    wf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wf)
    return wf


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


def _open_conversation(client: TestClient) -> str:
    resp = client.post(
        "/api/conversations", json={"agent_id": "guide_agent"}
    )
    assert resp.status_code == 200, resp.text
    conv = resp.json()
    assert conv["status"] == "active"
    assert conv["agent_id"] == "guide_agent"
    return conv["id"]


def _inject(app, stub) -> None:
    app.state.conversation_service.model_gateway = stub


# ── 注册 + 两条运行时语义正交 ────────────────────────────────────────────


def test_guide_agent_registered_as_interactive(client: TestClient, app_env) -> None:
    _, app = app_env
    g = app.state.agent_registry.get("guide_agent")
    assert g["workflow"]["mode"] == "interactive"
    assert g["category"] == "reasoning_assist"
    assert g["model"]["profile"] == "reasoning"
    # 门户 API 也能看到它（统一入口对用户可见）
    ids = [a["id"] for a in client.get("/api/agents").json()]
    assert "guide_agent" in ids


def test_create_conversation_rejects_non_interactive_agent(client: TestClient) -> None:
    resp = client.post(
        "/api/conversations", json={"agent_id": "hello_agent"}
    )
    assert resp.status_code == 409
    assert "interactive" in resp.json()["detail"]


def test_create_conversation_unknown_agent_404(client: TestClient) -> None:
    resp = client.post(
        "/api/conversations", json={"agent_id": "no_such_agent"}
    )
    assert resp.status_code == 404


def test_create_task_rejects_interactive_agent(client: TestClient) -> None:
    """ADR-0012 决策 6：interactive 型 Agent 不作为一次性任务运行。"""
    resp = client.post("/api/tasks", json={"agent_id": "guide_agent", "inputs": {}})
    assert resp.status_code == 409
    assert "conversations" in resp.json()["detail"]


def test_create_conversation_rejects_client_creator_and_derives_session_identity(
    client: TestClient,
) -> None:
    forged = client.post(
        "/api/conversations", json={"agent_id": "guide_agent", "created_by": "   "}
    )
    assert forged.status_code == 422

    honest = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert honest.status_code == 200
    assert honest.json()["created_by"] == TEST_DISPLAY_NAME


# ── 会话链：追问（无计划）────────────────────────────────────────────────


def test_post_message_clarifying_question_no_plan(app_env) -> None:
    client, app = app_env
    _inject(app, _CannedStub("请问这个系统的关键组件有哪些？"))
    conv_id = _open_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages", json={"content": "我想做点分析"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "请问这个系统的关键组件有哪些？"
    assert body["message"]["recommendation"] is None
    assert body["conversation"]["status"] == "active"
    assert body["conversation"]["recommendation"] is None

    # 历史含 user + assistant 两条
    got = client.get(f"/api/conversations/{conv_id}").json()
    roles = [m["role"] for m in got["messages"]]
    assert roles == ["user", "assistant"]


# ── LLM 边界：orchestrate 合法召集 + 非法字段剥离 ────────────────────────


def test_orchestrate_validated_and_prefilled(app_env) -> None:
    client, app = app_env
    # 召集 fta_agent：top_event 合法(string 保留)；components 传成 string(违反 array→剥离)；
    # bogus 未声明字段(剥离)。
    plan = _orchestrate([
        _agent("fta_agent", prefilled={
            "top_event": "供电完全丧失",
            "components": "发电机A",  # schema 要 array，类型不符 → 剥离
            "bogus": "x",             # 未声明 → 剥离
        }, role="搭建故障树"),
    ])
    _inject(app, _CannedStub(_plan_reply("根据你的需求，召集故障树分析 Agent。", plan)))
    conv_id = _open_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "我要对双通道供电系统做故障树分析，顶事件是供电完全丧失"},
    )
    assert resp.status_code == 200, resp.text
    reco = resp.json()["message"]["recommendation"]
    assert reco is not None
    assert reco["decision"] == "orchestrate"
    assert reco["goal"] and reco["analysis"] and reco["workflow"]
    assert len(reco["agents"]) == 1
    a0 = reco["agents"][0]
    assert a0["agent_id"] == "fta_agent"
    assert a0["category"] == "reasoning_assist"
    assert a0["status"] == "draft" and a0["maturity"] == "L0"  # 如实带出成熟度
    assert a0["role"] == "搭建故障树"
    # 只保留合法字段，非法字段剥离并如实记名
    assert a0["prefilled_inputs"] == {"top_event": "供电完全丧失"}
    assert a0["stripped_fields"] == ["bogus", "components"]
    assert reco["dropped_agents"] == [] and reco["capped"] is False
    # 分析文本原样展示（不因计划块存在而丢）
    assert "召集故障树分析 Agent" in resp.json()["message"]["content"]
    assert "<<PLAN>>" not in resp.json()["message"]["content"], "计划块不外露给用户当正文"

    # 会话级 recommendation 已回填
    got = client.get(f"/api/conversations/{conv_id}").json()
    assert got["recommendation"]["agents"][0]["agent_id"] == "fta_agent"


def test_multi_agent_orchestrate(app_env) -> None:
    """召集多个真实 Agent：全部保留、各带分工与预填。"""
    client, app = app_env
    plan = _orchestrate([
        _agent("fta_agent", prefilled={"top_event": "X"}, role="做故障树"),
        _agent("control_logic_agent", role="生成控制逻辑"),
    ])
    _inject(app, _CannedStub(_plan_reply("这需要两个 Agent 接力。", plan)))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "复杂任务"})
    reco = resp.json()["message"]["recommendation"]
    assert reco["decision"] == "orchestrate"
    ids = [a["agent_id"] for a in reco["agents"]]
    assert ids == ["fta_agent", "control_logic_agent"]
    assert reco["dropped_agents"] == []


def test_orchestrate_partial_drop_keeps_valid(app_env) -> None:
    """一真一假：真的保留、假的进 dropped_agents，不因个别幻觉整份作废。"""
    client, app = app_env
    plan = _orchestrate([
        _agent("fta_agent", prefilled={"top_event": "X"}),
        _agent("nonexistent_agent"),
        _agent("guide_agent"),  # 自身也不可召集
    ])
    _inject(app, _CannedStub(_plan_reply("方案如下。", plan)))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "任务"})
    reco = resp.json()["message"]["recommendation"]
    assert [a["agent_id"] for a in reco["agents"]] == ["fta_agent"]
    assert set(reco["dropped_agents"]) == {"nonexistent_agent", "guide_agent"}


def test_orchestrate_duplicate_agent_deduped(app_env) -> None:
    """同一 Agent 重复召集：只保留首个，重复计入 dropped。"""
    client, app = app_env
    plan = _orchestrate([
        _agent("fta_agent", prefilled={"top_event": "A"}),
        _agent("fta_agent", prefilled={"top_event": "B"}),
    ])
    _inject(app, _CannedStub(_plan_reply("方案。", plan)))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "任务"})
    reco = resp.json()["message"]["recommendation"]
    assert len(reco["agents"]) == 1
    assert reco["agents"][0]["prefilled_inputs"] == {"top_event": "A"}  # 保留首个
    assert reco["dropped_agents"] == ["fta_agent"]


def test_orchestrate_all_hallucinated_failclosed(app_env) -> None:
    """orchestrate 却无一真实 Agent 存活 → 整份作废（fail-closed，不外露空壳召集）。"""
    client, app = app_env
    plan = _orchestrate([_agent("nonexistent_agent"), _agent("guide_agent")])
    _inject(app, _CannedStub(_plan_reply("我来召集。", plan)))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我"})
    assert resp.status_code == 200
    # 无合法 Agent → recommendation 作废，但对话文本仍在
    assert resp.json()["message"]["recommendation"] is None
    assert "我来召集" in resp.json()["message"]["content"]
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"] is None


def test_orchestrate_caps_at_five_agents() -> None:
    """纯函数级：超过 5 个合法 Agent 时截断并置 capped（真实仓只有 4 个候选，用假
    候选集直测 _validate_orchestrate 的上限逻辑）。"""
    wf = _load_wf()
    candidates = [{"id": f"a{i}", "name": f"A{i}", "category": "tool_automation", "status": "draft", "maturity": "L0"} for i in range(6)]

    class _NoSchemaRegistry:
        def package_dir(self, agent_id):
            return None  # 无 input_schema → 预填一律剥离，不影响上限逻辑

    proposed = _orchestrate([{"agent_id": f"a{i}", "role": "r", "rationale": "x", "prefilled_inputs": {}} for i in range(6)])
    result = wf._validate_orchestrate(proposed, _NoSchemaRegistry(), candidates)
    assert result is not None
    assert len(result["agents"]) == 5, "召集上限 5 个"
    assert result["capped"] is True


# ── LLM 边界：refuse 显式拒绝 ────────────────────────────────────────────


def test_refuse_decision_rendered(app_env) -> None:
    client, app = app_env
    plan = _refuse(
        reason="这是一次性的行政统计，不是工程智能体该接的活儿。",
        residual=["你仍需要人工整理这批表格", "口径不统一的问题没解决"],
        reframe=["如果拆成『按 input_schema 的性能盘批量计算』，performance_disk_agent 可接"],
    )
    _inject(app, _CannedStub(_plan_reply("我判断平台接不住这件事。", plan)))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我整理这堆杂事"})
    assert resp.status_code == 200
    reco = resp.json()["message"]["recommendation"]
    assert reco["decision"] == "refuse"
    assert "一次性" in reco["reason"]
    assert len(reco["residual_problems"]) == 2
    assert len(reco["reframe"]) == 1
    # 拒绝不产生任何任务，也不外露 sentinel
    assert "<<PLAN>>" not in resp.json()["message"]["content"]
    conn = app.state.conn_factory()
    try:
        assert repos.list_tasks(conn) == []
    finally:
        conn.close()


def test_refuse_coerces_nonstring_fields() -> None:
    """refuse 的自由文本字段做类型强制：非串归空、列表过滤非串项（防脏 JSON）。"""
    wf = _load_wf()
    got = wf._validate_refuse({"decision": "refuse", "reason": 123, "residual_problems": ["ok", 5, None], "reframe": "notalist"})
    assert got["reason"] == ""
    assert got["residual_problems"] == ["ok"]
    assert got["reframe"] == []


def test_unknown_decision_failclosed(app_env) -> None:
    """decision 非 orchestrate/refuse（或缺失）→ 整份作废。"""
    client, app = app_env
    _inject(app, _CannedStub(_plan_reply("嗯。", {"decision": "自动执行", "agents": [_agent("fta_agent")]})))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "x"})
    assert resp.json()["message"]["recommendation"] is None


# ── 人是唯一签发者：导引全程不创建任务，草案交人提交 ─────────────────────


def test_guide_never_creates_task_and_human_signs(app_env) -> None:
    client, app = app_env
    plan = _orchestrate([_agent("fta_agent", prefilled={"top_event": "供电完全丧失"})])
    _inject(app, _CannedStub(_plan_reply("召集故障树分析。", plan)))
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    reco = resp.json()["message"]["recommendation"]
    a0 = reco["agents"][0]
    assert a0["agent_id"] == "fta_agent"

    # ① 导引全程零任务创建（红线：导引不签发任务）
    conn = app.state.conn_factory()
    try:
        assert repos.list_tasks(conn) == [], "导引绝不能创建任何任务"
    finally:
        conn.close()

    # ② 人拿预填草案去 tasks 端点亲手提交——草案对目标 Agent 是合法可用的输入起点
    human_inputs = dict(a0["prefilled_inputs"])
    human_inputs["system_description"] = "双通道供电系统"
    human_inputs["components"] = ["发电机A", "发电机B"]
    created = client.post(
        "/api/tasks", json={"agent_id": a0["agent_id"], "inputs": human_inputs}
    )
    assert created.status_code == 200
    assert created.json()["status"] == "queued"


# ── 诚实失败：区分永久配置错(503) 与临时上游故障(502)，均事务性零落库 ────────


class _RaisingStub:
    """chat 抛指定异常的 stub gateway，用于测临时上游故障（非配置错）路径。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        raise self._exc


def test_missing_config_503_transactional_no_partial_write(app_env) -> None:
    """无内网 key（FLAI_LLM_* 未配）→ 本轮 **503 配置错**（PM 战略审 top：永久性
    错误绝不谎报「可重试」误导用户反复点发送）；且事务性零落库，配置修好后重试
    不会在历史里堆重复 user 行。"""
    client, app = app_env
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我分析"})
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "模型网关未配置" in detail and "可重试" not in detail

    got = client.get(f"/api/conversations/{conv_id}").json()
    assert [m["role"] for m in got["messages"]] == [], "配置错必须零落库"
    assert got["recommendation"] is None

    resp2 = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我分析"})
    assert resp2.status_code == 503
    got2 = client.get(f"/api/conversations/{conv_id}").json()
    assert [m["role"] for m in got2["messages"]] == [], "重试不得堆出重复 user 行"


def test_transient_upstream_502_still_retryable(app_env) -> None:
    """env 已配但上游临时故障（网络错误/非 2xx，非配置错）→ 仍 502「可重试」——
    分流不得误伤真正可重试的临时故障。"""
    from backend.app.core.errors import ModelUpstreamError

    client, app = app_env
    conv_id = _open_conversation(client)
    _inject(app, _RaisingStub(ModelUpstreamError("上游网络错误：connect timeout")))

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我分析"})
    assert resp.status_code == 502
    assert "可重试" in resp.json()["detail"]


# ── 计划撤回轮清空会话级 recommendation（反方 P3-1）──────────────────────


def test_recommendation_cleared_on_followup_without_plan(app_env) -> None:
    client, app = app_env
    conv_id = _open_conversation(client)

    # 第一轮：给计划 → 会话级 recommendation 落地
    plan = _orchestrate([_agent("fta_agent", prefilled={"top_event": "X"})])
    app.state.conversation_service.model_gateway = _CannedStub(_plan_reply("召集", plan))
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"]["decision"] == "orchestrate"

    # 第二轮：只追问无计划 → 会话级 recommendation 必须清回 None
    app.state.conversation_service.model_gateway = _CannedStub("还有别的组件吗？")
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "嗯"})
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"] is None


# ── 预填字段校验对 $ref schema 也 fail-closed 不 500（反方 P2）──────────────


def test_clean_prefilled_inputs_handles_ref_schema(tmp_path) -> None:
    """目标 input_schema 用 $ref/$defs 时，逐字段校验必须能解析引用并正常剥离，
    绝不逃逸成 500（反方 P2：孤立子 schema 遇 $ref 抛非 ValidationError 引用错误）。"""
    wf = _load_wf()

    schema = {
        "type": "object",
        "properties": {"code": {"$ref": "#/$defs/NonEmpty"}, "n": {"type": "integer"}},
        "$defs": {"NonEmpty": {"type": "string", "minLength": 1}},
    }
    schema_path = tmp_path / "input_schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    class _FakeRegistry:
        def package_dir(self, agent_id):
            return tmp_path

    reg = _FakeRegistry()
    kept, stripped = wf._clean_prefilled_inputs(reg, "target", {"code": "OK", "n": "notint", "code2": "x", "empty_code": ""})
    assert kept == {"code": "OK"}
    assert set(stripped) == {"n", "code2", "empty_code"}

    kept2, stripped2 = wf._clean_prefilled_inputs(reg, "target", {"code": ""})
    assert kept2 == {} and stripped2 == ["code"]


def test_clean_prefilled_inputs_strips_root_combinator_violation(tmp_path) -> None:
    """异源 Codex R1-#1：input_schema 用**根层** allOf 施加更严/跨字段约束时，逐字段
    _field_valid 看不到根 allOf——单字段合法但违反根 allOf 的预填必须经整体复验剥离
    （fail-closed），而非漏进草案（否则完整 schema 校验会在人提交时才失败）。"""
    wf = _load_wf()
    # properties.x 只声明 type=string；根层 allOf 另把 x 限成 maxLength=3（跨"子 schema"约束）。
    schema = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "allOf": [{"properties": {"x": {"maxLength": 3}}}],
    }
    (tmp_path / "input_schema.json").write_text(json.dumps(schema), encoding="utf-8")

    class _FakeRegistry:
        def package_dir(self, agent_id):
            return tmp_path

    reg = _FakeRegistry()
    # x="AAAA" 逐字段过 properties.x（是字符串），却违反根 allOf 的 maxLength=3 → 必剥离。
    kept, stripped = wf._clean_prefilled_inputs(reg, "target", {"x": "AAAA"})
    assert kept == {}, "违反根 allOf 的预填必须被剥离，不得漏进草案"
    assert "x" in stripped
    # 对照：合法长度值仍保留（证明只咬跨字段违规，不是一刀切拒绝）。
    kept_ok, _ = wf._clean_prefilled_inputs(reg, "target", {"x": "AA"})
    assert kept_ok == {"x": "AA"}


def test_plan_oversized_raw_failclosed() -> None:
    """异源 Codex R1-#2：计划块原始字节超 _MAX_PLAN_BYTES → 整份作废（fail-closed），
    先于 json.loads、不落库——防超大 prefill 值/审计列表撑爆 recommendation_json。"""
    wf = _load_wf()
    raw_huge = json.dumps(_refuse(reason="X" * (wf._MAX_PLAN_BYTES + 100)), ensure_ascii=False)
    assert len(raw_huge) > wf._MAX_PLAN_BYTES
    assert wf._validate_plan(raw_huge, None, []) is None, "超字节顶的计划块必须整份作废"
    # 对照：同结构在字节顶内 → 正常产出（证明是字节顶在起作用；refuse 不碰 registry）。
    raw_ok = json.dumps(_refuse(reason="就绪"), ensure_ascii=False)
    assert wf._validate_plan(raw_ok, None, [])["decision"] == "refuse"


def test_plan_cjk_bytes_over_cap_failclosed() -> None:
    """异源 Codex R1-#2 复审：上限按 **UTF-8 字节** 非字符——CJK 计划字符数在顶内、字节数
    超顶仍须作废（否则 3 字节/字的中文可绕过字符顶塞进 ~3× 存储）。"""
    wf = _load_wf()
    reason = "漢" * (wf._MAX_PLAN_BYTES // 3 + 500)  # 每字 3 字节：字符 < 顶、字节 > 顶
    raw = json.dumps(_refuse(reason=reason), ensure_ascii=False)
    assert len(raw) < wf._MAX_PLAN_BYTES, "字符数须在顶内（证明字符顶会漏）"
    assert len(raw.encode("utf-8")) > wf._MAX_PLAN_BYTES, "字节数须超顶"
    assert wf._validate_plan(raw, None, []) is None, "按字节超顶必作废"


def test_plan_deeply_nested_json_failclosed() -> None:
    """异源 Codex R1-#2 复审：限额内的深嵌套 JSON 会让 json.loads 抛 RecursionError——
    须捕获作废，绝不逃逸成未处理 500。"""
    wf = _load_wf()
    depth = 20_000
    raw = "[" * depth + "]" * depth  # 合法但深嵌套；字节数远小于顶（不被字节闸拦）
    assert len(raw.encode("utf-8")) < wf._MAX_PLAN_BYTES
    assert wf._validate_plan(raw, None, []) is None  # 不崩，作废


def test_clean_prefilled_early_path_bounds_stripped() -> None:
    """异源 Codex R1-#2 复审：目标无 input_schema 的早退路径也须收界 stripped——海量
    未知字段名不得原样撑大审计列表（此前早退绕过条数/长度顶）。"""
    wf = _load_wf()

    class _NoSchemaRegistry:
        def package_dir(self, agent_id):
            return None  # 无 schema → 早退路径

    many = {f"field_{i}_{'x' * 80}": i for i in range(100)}  # 100 个超长未知字段名
    kept, stripped = wf._clean_prefilled_inputs(_NoSchemaRegistry(), "t", many)
    assert kept == {}
    assert len(stripped) <= wf._MAX_STRIPPED, "早退路径 stripped 条数须收界"
    assert all(len(n) <= wf._MAX_ID_CHARS for n in stripped), "单字段名须截断"


# ── 计划产物是 output_schema 的 oracle（反方 P3-5）────────────────────────


def test_plan_matches_output_schema(app_env) -> None:
    """_validate_plan 的两种返回（orchestrate/refuse）都必须过 guide_agent/
    output_schema.json（oneOf）——把 output_schema 从「文档」变成「oracle」。"""
    from jsonschema import validate as _validate

    client, app = app_env
    out_schema = json.loads(
        (REPO_ROOT / "agents" / "guide_agent" / "output_schema.json").read_text(encoding="utf-8")
    )
    conv_id = _open_conversation(client)

    # orchestrate 结构过 schema
    plan = _orchestrate([_agent("fta_agent", prefilled={"top_event": "X", "bad": 1})])
    app.state.conversation_service.model_gateway = _CannedStub(_plan_reply("召集", plan))
    reco = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"}).json()["message"]["recommendation"]
    _validate(reco, out_schema)

    # refuse 结构过 schema
    app.state.conversation_service.model_gateway = _CannedStub(_plan_reply("拒绝", _refuse(residual=["a"], reframe=["b"])))
    reco2 = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "别的"}).json()["message"]["recommendation"]
    _validate(reco2, out_schema)


# ── 会话存续期 Agent 被下线 → 拒绝继续对话（反方 P3-4）────────────────────


def test_post_message_rejected_if_agent_disabled_midway(
    app_env, tmp_path: Path
) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub("你好")
    conv_id = _open_conversation(client)

    _publish_agent_status(app, tmp_path, "guide_agent", "disabled")
    try:
        resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "继续"})
        assert resp.status_code == 409
        assert "不可用" in resp.json()["detail"]
    finally:
        app.state.agent_registry.scan()


def test_post_message_never_reads_live_package_dir(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub("你好")
    conv_id = _open_conversation(client)

    def _forbidden_live_dir(_agent_id: str):
        raise AssertionError("Conversation 不得读取可变 package_dir")

    monkeypatch.setattr(
        app.state.agent_registry,
        "package_dir",
        _forbidden_live_dir,
    )

    response = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "继续"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["message"]["content"]


# ── agents API 暴露 mode（前端路由信号，Codex P2）─────────────────────────


def test_agents_api_exposes_mode(client: TestClient) -> None:
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    assert agents["guide_agent"]["mode"] == "interactive"
    assert agents["fta_agent"]["mode"] == "job"


# ── 会话已结束不再接受消息 ────────────────────────────────────────────────


def test_post_to_closed_conversation_409(app_env) -> None:
    client, app = app_env
    _inject(app, _CannedStub("你好"))
    conv_id = _open_conversation(client)

    conn = app.state.conn_factory()
    try:
        repos.set_conversation_status(conn, conv_id, "concluded")
    finally:
        conn.close()

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "还能说话吗"})
    assert resp.status_code == 409
    assert "concluded" in resp.json()["detail"]


# ── ADR-0013 审计硬化：conclude 生命周期 / 并发冲突 / 归因 / 上限 / 窗口 ────


def test_conclude_lifecycle(app_env) -> None:
    """conclude：active→concluded 唯一合法转出；重复 conclude 与后续消息均 409。"""
    client, app = app_env
    _inject(app, _CannedStub("你好"))
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/conclude")
    assert resp.status_code == 200
    assert resp.json()["status"] == "concluded"

    again = client.post(f"/api/conversations/{conv_id}/conclude")
    assert again.status_code == 409, "重复 conclude 必须如实 409，不幂等吞掉"

    msg = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "还在吗"})
    assert msg.status_code == 409

    assert client.post("/api/conversations/conv_missing/conclude").status_code == 404


class _InterloperStub(_CannedStub):
    """模拟并发轮：在本轮 workflow 执行期间，另一请求往同一会话插了一条消息。"""

    def __init__(self, reply: str, app, conv_id: str) -> None:
        super().__init__(reply)
        self._app = app
        self._conv_id = conv_id

    def chat(self, profile, messages, **kwargs):
        from backend.app.storage import repos as _repos

        conn = self._app.state.conn_factory()
        try:
            _repos.append_message(
                conn, conversation_id=self._conv_id, role="user", content="并发插入的消息"
            )
        finally:
            conn.close()
        return super().chat(profile, messages, **kwargs)


def test_concurrent_turn_conflict_409_and_zero_partial_write(app_env) -> None:
    """乐观并发检查（审计 P2）：本轮生成期间历史被并发修改 → 409 且本轮零落库，
    绝不把基于过期历史的回复交错写进历史；随后基于最新历史重试成功。"""
    client, app = app_env
    conv_id = _open_conversation(client)
    _inject(app, _InterloperStub("基于过期历史的回复", app, conv_id))

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "第一句"})
    assert resp.status_code == 409
    assert "并发" in resp.json()["detail"]

    got = client.get(f"/api/conversations/{conv_id}").json()
    contents = [m["content"] for m in got["messages"]]
    assert contents == ["并发插入的消息"], f"冲突轮不得落任何行，实得 {contents}"

    _inject(app, _CannedStub("这轮正常"))
    retry = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "第一句"})
    assert retry.status_code == 200
    roles = [m["role"] for m in client.get(f"/api/conversations/{conv_id}").json()["messages"]]
    assert roles == ["user", "user", "assistant"]


def test_conversation_model_calls_attributed(app_env) -> None:
    """归因（ADR-0013 / §18-Q5）：①wrapper 自动注入 conversation_id+agent_id；
    ②真实 gateway 失败路径的 model_calls 行可经会话端点检索（成败全量）。"""
    client, app = app_env

    stub = _CannedStub("你好")
    _inject(app, stub)
    conv_id = _open_conversation(client)
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "hi"})
    assert stub.calls[0]["conversation_id"] == conv_id
    assert stub.calls[0]["agent_id"] == "guide_agent"

    conv2 = client.post(
        "/api/conversations", json={"agent_id": "guide_agent"}
    ).json()["id"]
    app.state.conversation_service.model_gateway = app.state.model_gateway
    # 缺 env=配置错→503（原 502），但 model_calls 失败留痕不变（子类仍被内部 except 捕获记 failed）
    assert client.post(f"/api/conversations/{conv2}/messages", json={"content": "hi"}).status_code == 503

    calls = client.get(f"/api/conversations/{conv2}/model_calls").json()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert calls[0]["conversation_id"] == conv2
    assert calls[0]["agent_id"] == "guide_agent"
    assert client.get("/api/conversations/conv_missing/model_calls").status_code == 404


def test_post_message_content_cap_422(app_env) -> None:
    client, app = app_env
    _inject(app, _CannedStub("你好"))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "x" * 16001})
    assert resp.status_code == 422


def test_history_window_caps_messages_and_chars() -> None:
    from backend.app.runtime.conversation import _HISTORY_MAX_MESSAGES, _window

    many = [{"role": "user", "content": f"m{i}"} for i in range(100)]
    w = _window(many)
    assert len(w) == _HISTORY_MAX_MESSAGES
    assert w[-1]["content"] == "m99", "窗口必须保住最新一条"

    huge = [{"role": "user", "content": "x" * 50_000} for _ in range(5)]
    w2 = _window(huge)
    assert 1 <= len(w2) < 5, "字符预算必须截断，且至少保住最后一条"
    assert w2[-1] is huge[-1]


def test_split_plan_preserves_tail_text(app_env) -> None:
    """审计 P3：计划块之后的 assistant 文本此前被静默丢弃——现原样保留；
    第二个计划块整体丢弃（只认第一块，sentinel 不外露）。"""
    client, app = app_env
    plan = _orchestrate([_agent("fta_agent", prefilled={"top_event": "X"})])
    reply = (
        "块前说明。\n" + _plan_reply("", plan).strip()
        + "\n块后重要提醒：请补全组件清单。\n<<PLAN>>\n{\"decision\":\"orchestrate\",\"agents\":[{\"agent_id\":\"hello_agent\"}]}\n<<END>>"
    )
    _inject(app, _CannedStub(reply))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    body = resp.json()["message"]
    assert "块前说明" in body["content"]
    assert "块后重要提醒" in body["content"], "计划块之后的文本不得静默丢弃"
    assert "<<PLAN>>" not in body["content"] and "<<END>>" not in body["content"]
    assert body["recommendation"]["agents"][0]["agent_id"] == "fta_agent", "只认第一块"


def test_visible_reply_stream_hides_fragmented_plan_marker() -> None:
    """计划 sentinel 横跨上游 chunk 时也不得闪到用户眼前；普通正文立即透传。"""
    wf = _load_wf()
    visible: list[str] = []
    stream = wf._VisibleReplyStream(visible.append)

    stream.feed("先给你答")
    stream.feed("复。<<PL")
    stream.feed('AN>>{"decision":"orchestrate"}<<END>>')
    stream.finish()

    assert "".join(visible) == "先给你答复。"
    assert "<<PLAN>>" not in "".join(visible)


def test_stream_message_ndjson_yields_safe_deltas_then_atomic_done(app_env) -> None:
    client, app = app_env
    plan = _orchestrate([_agent("fta_agent", prefilled={"top_event": "X"})])
    reply = _plan_reply("先给你一句可见回复。", plan)
    _inject(
        app,
        _StreamingStub(
            reply,
            ["先给你一句", "可见回复。<<PL", f"AN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"],
        ),
    )
    conv_id = _open_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "做故障树"},
    ) as resp:
        assert resp.status_code == 200
        events = [json.loads(line) for line in resp.iter_lines() if line]

    assert events[0]["type"] == "start"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "先给你一句可见回复。"
    assert all("<<PLAN>>" not in json.dumps(e, ensure_ascii=False) for e in events)
    done = events[-1]
    assert done["type"] == "done"
    assert done["message"]["content"] == "先给你一句可见回复。"
    assert done["message"]["recommendation"]["agents"][0]["agent_id"] == "fta_agent"

    persisted = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    assert [m["role"] for m in persisted] == ["user", "assistant"]


def test_stream_message_partial_error_is_explicit_and_zero_persistence(app_env) -> None:
    client, app = app_env
    _inject(
        app,
        _StreamingStub(
            "不会完整返回",
            ["已收到一小段"],
            ModelUpstreamError("上游在流式中途断开"),
        ),
    )
    conv_id = _open_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "请分析"},
    ) as resp:
        events = [json.loads(line) for line in resp.iter_lines() if line]

    assert [e["type"] for e in events] == ["start", "delta", "error"]
    assert events[1]["text"] == "已收到一小段"
    assert events[2]["status"] == 502
    assert events[2]["persisted"] is False
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_stream_message_unclosed_plan_fails_closed_with_zero_persistence(app_env) -> None:
    """出现 <<PLAN>> 却缺 <<END>> 时，控制片段不得进入 done 或数据库。"""
    client, app = app_env
    reply = '先给可见说明。<<PLAN>>\n{"decision":"orchestrate"'
    _inject(
        app,
        _StreamingStub(
            reply,
            ["先给可见说明。<<PL", 'AN>>\n{"decision":"orchestrate"'],
        ),
    )
    conv_id = _open_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "做分析"},
    ) as resp:
        events = [json.loads(line) for line in resp.iter_lines() if line]

    assert [e["type"] for e in events] == ["start", "delta", "error"]
    assert events[1]["text"] == "先给可见说明。"
    assert events[-1]["persisted"] is False
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_stream_asgi_disconnect_cancels_round_before_persistence(app_env) -> None:
    """真实 ASGI http.disconnect 必须及时关闭流，并让后台轮次在提交前退出。"""
    client, app = app_env
    stub = _UntilDisconnectedStreamingStub()
    _inject(app, stub)
    conv_id = _open_conversation(client)
    path = f"/api/conversations/{conv_id}/messages/stream"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
        "app": app,
    }
    sent: list[dict[str, Any]] = []

    async def exercise_disconnect() -> None:
        disconnected = asyncio.Event()

        async def receive() -> dict[str, Any]:
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)
            if (
                message["type"] == "http.response.body"
                and b'"type":"start"' in message.get("body", b"")
            ):
                disconnected.set()

        response = stream_message(
            conv_id,
            PostMessageRequest(content="断连测试"),
            Request(scope, receive),
        )
        await asyncio.wait_for(response(scope, receive, send), timeout=2)

    asyncio.run(exercise_disconnect())
    assert any(
        m["type"] == "http.response.body"
        and b'"type":"start"' in m.get("body", b"")
        for m in sent
    )
    assert stub.finished.wait(timeout=3), "断连后后台模型消费必须及时结束"
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_stream_done_has_no_fallible_database_read_after_commit(app_env, monkeypatch) -> None:
    """commit 后若再读会话可能误报 persisted:false；done 必须来自事务内快照。"""
    client, app = app_env
    _inject(app, _StreamingStub("完整回复", ["完整", "回复"]))
    conv_id = _open_conversation(client)
    original_get = conversation_mod.repos.get_conversation
    outside_transaction_calls = 0

    def reject_second_outside_read(conn, conversation_id):
        nonlocal outside_transaction_calls
        row = original_get(conn, conversation_id)
        if not conn.in_transaction:
            outside_transaction_calls += 1
            if outside_transaction_calls > 1:
                raise RuntimeError("commit 后禁止再次读取")
        return row

    monkeypatch.setattr(
        conversation_mod.repos, "get_conversation", reject_second_outside_read
    )
    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "请回答"},
    ) as resp:
        events = [json.loads(line) for line in resp.iter_lines() if line]

    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["content"] == "完整回复"
    assert outside_transaction_calls == 1

    monkeypatch.setattr(conversation_mod.repos, "get_conversation", original_get)
    assert [m["role"] for m in client.get(
        f"/api/conversations/{conv_id}"
    ).json()["messages"]] == ["user", "assistant"]
