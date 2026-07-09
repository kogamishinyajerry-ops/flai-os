"""M6 导引 Agent 与 interactive 会话运行时（ADR-0012）。

覆盖：
- guide_agent 作为 interactive 型插件注册；两条运行时语义正交（interactive 不建
  一次性任务、非 interactive 不发起会话）。
- 会话链：开启会话 → 逐轮消息 → assistant 回复；stub gateway 注入方式同 M5
  （app.state.conversation_service.model_gateway = stub）。
- LLM 边界（本里程碑核心）：推荐块经 workflow 确定性对账 Registry + 目标
  input_schema——合法推荐才外露，幻觉 agent_id / 自身 / 非法字段一律 fail-closed。
- 人是唯一签发者红线：导引全程不创建任何任务；预填草案由人在 tasks 端点亲手提交。
- 诚实失败（事务性单轮，ADR-0013）：无内网 key（清空 FLAI_LLM_*）→ 本轮 502 且
  **零消息落库**（幂等重试）；并发轮冲突 → 409 且零落库。
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.storage import repos
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_LLM_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")


class _CannedStub:
    """返回一条固定 assistant 文本的 stub gateway；签名对齐导引 workflow 直连调用
    model_gateway.chat(profile, messages)。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        return {"content": self.reply, "token_usage": None, "model_name": "stub", "finish_reason": "stop"}


def _reco_reply(rationale_text: str, payload: dict[str, Any]) -> str:
    """构造「理由文本 + 推荐块」形态的 assistant 回复。"""
    return f"{rationale_text}\n<<RECOMMEND>>\n{json.dumps(payload, ensure_ascii=False)}\n<<END>>"


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def app_env(tmp_path):
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=tmp_path / "flai_os.db",
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        yield client, app


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


def _open_conversation(client: TestClient) -> str:
    resp = client.post(
        "/api/conversations", json={"agent_id": "guide_agent", "created_by": "m6_test"}
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
        "/api/conversations", json={"agent_id": "hello_agent", "created_by": "m6_test"}
    )
    assert resp.status_code == 409
    assert "interactive" in resp.json()["detail"]


def test_create_conversation_unknown_agent_404(client: TestClient) -> None:
    resp = client.post(
        "/api/conversations", json={"agent_id": "no_such_agent", "created_by": "m6_test"}
    )
    assert resp.status_code == 404


def test_create_task_rejects_interactive_agent(client: TestClient) -> None:
    """ADR-0012 决策 6：interactive 型 Agent 不作为一次性任务运行。"""
    resp = client.post("/api/tasks", json={"agent_id": "guide_agent", "inputs": {}})
    assert resp.status_code == 409
    assert "conversations" in resp.json()["detail"]


def test_create_conversation_requires_named_creator(client: TestClient) -> None:
    resp = client.post(
        "/api/conversations", json={"agent_id": "guide_agent", "created_by": "   "}
    )
    assert resp.status_code == 422


# ── 会话链：追问（无推荐）────────────────────────────────────────────────


def test_post_message_clarifying_question_no_recommendation(app_env) -> None:
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


# ── LLM 边界：合法推荐经确定性校验 + 非法字段剥离 ────────────────────────


def test_valid_recommendation_validated_and_prefilled(app_env) -> None:
    client, app = app_env
    # 推荐 fta_agent：top_event 合法(string 保留)；components 传成 string(违反 array→剥离)；
    # bogus 未声明字段(剥离)。
    payload = {
        "agent_id": "fta_agent",
        "rationale": "你要做故障树分析",
        "prefilled_inputs": {
            "top_event": "供电完全丧失",
            "components": "发电机A",  # schema 要 array，类型不符 → 剥离
            "bogus": "x",             # 未声明 → 剥离
        },
    }
    _inject(app, _CannedStub(_reco_reply("根据你的需求，推荐故障树分析 Agent。", payload)))
    conv_id = _open_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "我要对双通道供电系统做故障树分析，顶事件是供电完全丧失"},
    )
    assert resp.status_code == 200, resp.text
    reco = resp.json()["message"]["recommendation"]
    assert reco is not None
    assert reco["agent_id"] == "fta_agent"
    assert reco["category"] == "reasoning_assist"
    assert reco["status"] == "draft" and reco["maturity"] == "L0"  # 如实带出成熟度
    # 只保留合法字段，非法字段剥离并如实记名
    assert reco["prefilled_inputs"] == {"top_event": "供电完全丧失"}
    assert reco["stripped_fields"] == ["bogus", "components"]
    # 理由文本原样展示（不因推荐块存在而丢）
    assert "推荐故障树分析 Agent" in resp.json()["message"]["content"]
    assert "<<RECOMMEND>>" not in resp.json()["message"]["content"], "推荐块不外露给用户当正文"

    # 会话级 recommendation 已回填
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"]["agent_id"] == "fta_agent"


def test_hallucinated_agent_id_dropped_failclosed(app_env) -> None:
    client, app = app_env
    payload = {"agent_id": "nonexistent_agent", "rationale": "瞎推荐", "prefilled_inputs": {}}
    _inject(app, _CannedStub(_reco_reply("推荐这个。", payload)))
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我推荐"})
    assert resp.status_code == 200
    # 幻觉 agent_id → 整个推荐作废，但对话文本仍在
    assert resp.json()["message"]["recommendation"] is None
    assert "推荐这个" in resp.json()["message"]["content"]
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"] is None


def test_self_recommendation_dropped(app_env) -> None:
    """导引不能推荐它自己（interactive/自身一律不在候选面）。"""
    client, app = app_env
    payload = {"agent_id": "guide_agent", "rationale": "推荐我自己", "prefilled_inputs": {}}
    _inject(app, _CannedStub(_reco_reply("试试这个。", payload)))
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "推荐"})
    assert resp.status_code == 200
    assert resp.json()["message"]["recommendation"] is None


# ── 人是唯一签发者：导引全程不创建任务，草案交人提交 ─────────────────────


def test_guide_never_creates_task_and_human_signs(app_env) -> None:
    client, app = app_env
    payload = {
        "agent_id": "fta_agent",
        "rationale": "故障树",
        "prefilled_inputs": {"top_event": "供电完全丧失"},
    }
    _inject(app, _CannedStub(_reco_reply("推荐故障树分析。", payload)))
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    reco = resp.json()["message"]["recommendation"]
    assert reco["agent_id"] == "fta_agent"

    # ① 导引全程零任务创建（红线：导引不签发任务）
    conn = app.state.conn_factory()
    try:
        assert repos.list_tasks(conn) == [], "导引绝不能创建任何任务"
    finally:
        conn.close()

    # ② 人拿预填草案去 tasks 端点亲手提交——草案对目标 Agent 是合法可用的输入起点
    #    （补全 required 后能真正建成任务，证明预填链路端到端有效）
    human_inputs = dict(reco["prefilled_inputs"])
    human_inputs["system_description"] = "双通道供电系统"
    human_inputs["components"] = ["发电机A", "发电机B"]
    created = client.post(
        "/api/tasks", json={"agent_id": reco["agent_id"], "inputs": human_inputs, "created_by": "王工"}
    )
    assert created.status_code == 200
    assert created.json()["status"] == "queued"


# ── 诚实失败：无内网 key → 本轮 502，用户消息留档不伪造 ───────────────────


def test_gateway_failure_502_transactional_no_partial_write(app_env) -> None:
    """无内网 key → 本轮 502；且是**事务性**的：失败一条消息都不落库，重试同一句
    不会在历史里堆重复 user 行（Codex P2：可重试路径必须幂等）。"""
    client, app = app_env
    # 不注入 stub：走真实 gateway，FLAI_LLM_* 已清空 → fail-closed（不触网络）
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我分析"})
    assert resp.status_code == 502
    assert "可重试" in resp.json()["detail"]

    # 失败：零消息落库（不伪造 assistant，也不留孤儿 user）
    got = client.get(f"/api/conversations/{conv_id}").json()
    assert [m["role"] for m in got["messages"]] == [], "瞬态失败必须零落库（可幂等重试）"
    assert got["recommendation"] is None

    # 重试同一句仍 502，历史仍为空——不累积重复 user 行
    resp2 = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我分析"})
    assert resp2.status_code == 502
    got2 = client.get(f"/api/conversations/{conv_id}").json()
    assert [m["role"] for m in got2["messages"]] == [], "重试不得堆出重复 user 行"


# ── 推荐撤回轮清空会话级 recommendation（反方 P3-1）──────────────────────


def test_recommendation_cleared_on_followup_without_reco(app_env) -> None:
    client, app = app_env
    conv_id = _open_conversation(client)

    # 第一轮：给推荐 → 会话级 recommendation 落地
    payload = {"agent_id": "fta_agent", "rationale": "r", "prefilled_inputs": {"top_event": "X"}}
    app.state.conversation_service.model_gateway = _CannedStub(_reco_reply("推荐", payload))
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"]["agent_id"] == "fta_agent"

    # 第二轮：只追问无推荐 → 会话级 recommendation 必须清回 None（不留陈旧草案）
    app.state.conversation_service.model_gateway = _CannedStub("还有别的组件吗？")
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "嗯"})
    assert client.get(f"/api/conversations/{conv_id}").json()["recommendation"] is None


# ── 预填字段校验对 $ref schema 也 fail-closed 不 500（反方 P2）──────────────


def test_clean_prefilled_inputs_handles_ref_schema(tmp_path) -> None:
    """目标 input_schema 用 $ref/$defs 时，逐字段校验必须能解析引用并正常剥离，
    绝不逃逸成 500（反方 P2：孤立子 schema 遇 $ref 抛非 ValidationError 引用错误）。"""
    import importlib.util

    wf_path = REPO_ROOT / "agents" / "guide_agent" / "workflow.py"
    spec = importlib.util.spec_from_file_location("guide_wf_under_test", wf_path)
    wf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wf)

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
    # 合法 $ref 值保留；空串（违反 minLength）+ n 类型错 + 未声明字段全部剥离——不抛异常
    kept, stripped = wf._clean_prefilled_inputs(reg, "target", {"code": "OK", "n": "notint", "code2": "x", "empty_code": ""})
    # empty_code 未声明（schema 无此属性）→ 剥离；code 合法保留
    assert kept == {"code": "OK"}
    assert set(stripped) == {"n", "code2", "empty_code"}

    # 再证「$ref 字段的非法值」也被剥离而非崩溃
    kept2, stripped2 = wf._clean_prefilled_inputs(reg, "target", {"code": ""})  # 空串违反 minLength
    assert kept2 == {} and stripped2 == ["code"]


# ── 推荐产物是 output_schema 的 oracle（反方 P3-5）────────────────────────


def test_recommendation_matches_output_schema(app_env) -> None:
    """_validate_recommendation 的返回结构必须过 guide_agent/output_schema.json——
    把 output_schema 从「文档」变成「oracle」，防结构漂移无人察觉。"""
    from jsonschema import validate as _validate

    client, app = app_env
    payload = {"agent_id": "fta_agent", "rationale": "r", "prefilled_inputs": {"top_event": "X", "bad": 1}}
    app.state.conversation_service.model_gateway = _CannedStub(_reco_reply("推荐", payload))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    reco = resp.json()["message"]["recommendation"]

    out_schema = json.loads(
        (REPO_ROOT / "agents" / "guide_agent" / "output_schema.json").read_text(encoding="utf-8")
    )
    _validate(reco, out_schema)  # 不抛即通过——结构与契约一致


# ── 会话存续期 Agent 被下线 → 拒绝继续对话（反方 P3-4）────────────────────


def test_post_message_rejected_if_agent_disabled_midway(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub("你好")
    conv_id = _open_conversation(client)

    # 模拟会话存续期间 guide_agent 被下线（改内存注册表）
    app.state.agent_registry.get("guide_agent")["status"] = "disabled"
    try:
        resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "继续"})
        assert resp.status_code == 409
        assert "不可用" in resp.json()["detail"]
    finally:
        app.state.agent_registry.get("guide_agent")["status"] = "draft"  # 还原，避免串扰


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

    # 直接把会话置为 concluded（模拟结束态）
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

    # 冲突轮零落库：历史里只有 interloper 那一条，无本轮 user/assistant
    got = client.get(f"/api/conversations/{conv_id}").json()
    contents = [m["content"] for m in got["messages"]]
    assert contents == ["并发插入的消息"], f"冲突轮不得落任何行，实得 {contents}"

    # 基于最新历史重试 → 正常成功
    _inject(app, _CannedStub("这轮正常"))
    retry = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "第一句"})
    assert retry.status_code == 200
    roles = [m["role"] for m in client.get(f"/api/conversations/{conv_id}").json()["messages"]]
    assert roles == ["user", "user", "assistant"]


def test_conversation_model_calls_attributed(app_env) -> None:
    """归因（ADR-0013 / §18-Q5）：①wrapper 自动注入 conversation_id+agent_id；
    ②真实 gateway 失败路径的 model_calls 行可经会话端点检索（成败全量）。"""
    client, app = app_env

    # ① stub 侧：wrapper 注入的 kwargs 可见
    stub = _CannedStub("你好")
    _inject(app, stub)
    conv_id = _open_conversation(client)
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "hi"})
    assert stub.calls[0]["conversation_id"] == conv_id
    assert stub.calls[0]["agent_id"] == "guide_agent"

    # ② 真实 gateway（FLAI_LLM_* 已清空）：失败留痕可按会话检索
    conv2 = client.post(
        "/api/conversations", json={"agent_id": "guide_agent", "created_by": "m6_test"}
    ).json()["id"]
    app.state.conversation_service.model_gateway = app.state.model_gateway  # 还原真实 gateway
    assert client.post(f"/api/conversations/{conv2}/messages", json={"content": "hi"}).status_code == 502

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


def test_split_recommendation_preserves_tail_text(app_env) -> None:
    """审计 P3：推荐块之后的 assistant 文本此前被静默丢弃——现原样保留；
    第二个推荐块整体丢弃（只认第一块，sentinel 不外露）。"""
    client, app = app_env
    payload = {"agent_id": "fta_agent", "rationale": "r", "prefilled_inputs": {"top_event": "X"}}
    reply = (
        "块前说明。\n" + _reco_reply("", payload).strip()
        + "\n块后重要提醒：请补全组件清单。\n<<RECOMMEND>>\n{\"agent_id\":\"hello_agent\"}\n<<END>>"
    )
    _inject(app, _CannedStub(reply))
    conv_id = _open_conversation(client)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "做故障树"})
    body = resp.json()["message"]
    assert "块前说明" in body["content"]
    assert "块后重要提醒" in body["content"], "推荐块之后的文本不得静默丢弃"
    assert "<<RECOMMEND>>" not in body["content"] and "<<END>>" not in body["content"]
    assert body["recommendation"]["agent_id"] == "fta_agent", "只认第一块"
