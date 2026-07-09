"""M6 导引 Agent 与 interactive 会话运行时（ADR-0012）。

覆盖：
- guide_agent 作为 interactive 型插件注册；两条运行时语义正交（interactive 不建
  一次性任务、非 interactive 不发起会话）。
- 会话链：开启会话 → 逐轮消息 → assistant 回复；stub gateway 注入方式同 M5
  （app.state.conversation_service.model_gateway = stub）。
- LLM 边界（本里程碑核心）：推荐块经 workflow 确定性对账 Registry + 目标
  input_schema——合法推荐才外露，幻觉 agent_id / 自身 / 非法字段一律 fail-closed。
- 人是唯一签发者红线：导引全程不创建任何任务；预填草案由人在 tasks 端点亲手提交。
- 诚实失败：无内网 key（清空 FLAI_LLM_*）→ 本轮对话 502，用户消息留档不伪造回复。
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


def test_gateway_failure_502_and_user_message_persisted(app_env) -> None:
    client, app = app_env
    # 不注入 stub：走真实 gateway，FLAI_LLM_* 已清空 → fail-closed（不触网络）
    conv_id = _open_conversation(client)

    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "帮我分析"})
    assert resp.status_code == 502
    assert "可重试" in resp.json()["detail"]

    # 用户消息如实留档（问过但这轮失败），且没有伪造的 assistant 回复
    got = client.get(f"/api/conversations/{conv_id}").json()
    roles = [m["role"] for m in got["messages"]]
    assert roles == ["user"], "上游失败绝不伪造 assistant 回复"
    assert got["recommendation"] is None


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
