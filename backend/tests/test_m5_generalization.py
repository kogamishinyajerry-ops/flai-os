"""M5 平台泛化验证（任务书 §12.6）：三类 Agent 同一 Runtime 承载。

- control_logic_agent（structured_gen，零 LLM 零工具）：纯确定性结构生成 +
  BFS 不可达态分析——「纯结构化生成型」首证。
- fta_agent（reasoning_assist，model.profile=reasoning + requires_human_review）：
  首次真实走通 Model Gateway 调用链与 waiting_review 人工放行链。

stub gateway 注入方式：create_app 在 lifespan 里装配真实 ModelGateway 并挂进
AgentRuntime；AgentRuntime 每次 execute 都读 self.model_gateway 属性，故测试
在 TestClient 启动后直接 `app.state.runtime.model_gateway = stub` 即完成注入
（与 test_runtime.py 的构造注入等价，但适配 create_app 装配路径）。stub 的
chat 签名对齐 _ModelGatewayContext 的转发形态：chat(profile, messages,
task_id=..., agent_id=..., **kwargs)。

fta 失败路径刻意用**真实** ModelGateway + 清空 FLAI_LLM_* 环境变量：gateway
在 env 缺失时 fail-closed 抛 ModelUpstreamError（不触网络），比 raising-stub
多验证了 gateway 自身的 model_calls 留痕。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]

_LLM_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")

_STUB_DRAFT = (
    "[STUB] 中间事件候选：主通道供电丧失；备用通道供电丧失。\n"
    "[STUB] 基本事件候选：发电机A 失效（待工程师确认）；转换开关卡滞。\n"
    "[STUB] 最小割集建议：{发电机A 失效, 发电机B 失效}。"
)


class _StubGateway:
    """确定文本 stub：签名对齐 _ModelGatewayContext 转发（接收 task_id/agent_id kwargs）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        return {
            "content": _STUB_DRAFT,
            "token_usage": None,
            "model_name": "stub-model",
            "finish_reason": "stop",
        }


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    """清空宿主机 LLM 环境变量：stub 路径不受串扰，失败路径确定性 fail-closed。"""
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


def _create_and_run(client: TestClient, app, agent_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(
        "/api/tasks",
        json={"agent_id": agent_id, "inputs": inputs, "created_by": "m5_test"},
    )
    assert resp.status_code == 200
    task_id = resp.json()["id"]
    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True
    return client.get(f"/api/tasks/{task_id}").json()


def _outputs_by_name(client: TestClient, app, task: dict) -> dict[str, bytes]:
    conn = app.state.conn_factory()
    try:
        records = [repos.get_file(conn, fid) for fid in task["output_file_ids"]]
    finally:
        conn.close()
    out: dict[str, bytes] = {}
    for record in records:
        assert record is not None
        resp = client.get(f"/api/files/{record['id']}/download")
        assert resp.status_code == 200
        out[record["filename"]] = resp.content
    return out


# eval_cases/case_001.json 是期望口径的单一事实源
_CL_CASE = json.loads(
    (REPO_ROOT / "agents" / "control_logic_agent" / "eval_cases" / "case_001.json").read_text(encoding="utf-8")
)
_FTA_CASE = json.loads(
    (REPO_ROOT / "agents" / "fta_agent" / "eval_cases" / "case_001.json").read_text(encoding="utf-8")
)


# ── control_logic_agent：结构化生成型 E2E ────────────────────────────────


def test_control_logic_e2e_completed_with_unreachable_analysis(app_env) -> None:
    client, app = app_env
    task = _create_and_run(client, app, "control_logic_agent", _CL_CASE["inputs"])
    expected = _CL_CASE["expected"]

    assert task["status"] == expected["task_status"] == "completed"

    outputs = _outputs_by_name(client, app, task)
    assert set(outputs.keys()) == set(expected["artifacts"])

    logic = json.loads(outputs["control_logic.json"].decode("utf-8"))
    assert logic["initial_state"] == _CL_CASE["inputs"]["states"][0]
    assert logic["analysis"]["unreachable_states"] == expected["unreachable_states"]
    assert len(logic["states"]) == expected["state_count"]
    assert len(logic["transitions"]) == expected["transition_count"]

    md = outputs["control_logic.md"].decode("utf-8")
    assert "状态转移表" in md
    assert "不可达态警告" in md and "maintenance" in md

    # 事件完整：workflow 三事件折叠为 agent_log（workflow_event_type 保留原类型）
    events = client.get(f"/api/tasks/{task['id']}/events").json()
    folded_types = [
        e["payload"].get("workflow_event_type") for e in events if e["event_type"] == "agent_log"
    ]
    for required in ("validation_started", "structure_generated", "reachability_checked"):
        assert required in folded_types, f"缺 workflow 事件：{required}"
    assert any(e["event_type"] == "task_completed" for e in events)

    # 零工具零模型：tool_runs / model_calls 都必须为空（负向保证）
    conn = app.state.conn_factory()
    try:
        assert repos.list_tool_runs(conn, task["id"]) == []
        assert repos.list_model_calls(conn, task["id"]) == []
    finally:
        conn.close()

    # 反馈链在新 Agent 上同样可用
    fb = client.post(
        "/api/feedback",
        json={"task_id": task["id"], "rating": "good", "category": "suggestion",
              "message": "结构展开正确", "created_by": "m5_王工"},
    )
    assert fb.status_code == 200


def test_control_logic_invalid_transition_failed_honestly(app_env) -> None:
    client, app = app_env
    inputs = {
        "system_name": "坏输入示例",
        "states": ["idle", "running"],
        "transitions": [
            {"from": "ghost", "to": "running", "condition": "x"},   # from 不在 states
            {"from": "running", "to": "phantom", "condition": "y"},  # to 不在 states
        ],
    }
    task = _create_and_run(client, app, "control_logic_agent", inputs)
    assert task["status"] == "failed"
    assert "ghost" in task["error_message"] and "phantom" in task["error_message"], \
        "语义校验必须一次列出全部问题"
    assert task["output_file_ids"] == []


# ── fta_agent：Gateway 调用链 + waiting_review 人工放行链（M5 核心）──────


def test_fta_e2e_waiting_review_then_approve(app_env) -> None:
    client, app = app_env
    stub = _StubGateway()
    app.state.runtime.model_gateway = stub  # 注入 stub（见模块 docstring）

    task = _create_and_run(client, app, "fta_agent", _FTA_CASE["inputs"])
    expected = _FTA_CASE["expected"]
    task_id = task["id"]

    # ① 任务停 waiting_review（不是 completed）——requires_human_review 链被真实走到
    assert task["status"] == expected["task_status"] == "waiting_review"

    # ② stub 被以正确画像调用，messages 含 prompt.md 的 system 提示词
    assert len(stub.calls) == 1
    assert stub.calls[0]["profile"] == "reasoning"
    system_msg = stub.calls[0]["messages"][0]
    assert system_msg["role"] == "system"
    assert "故障树分析" in system_msg["content"] and "草案" in system_msg["content"]
    assert stub.calls[0]["task_id"] == task_id  # _ModelGatewayContext 自动带 task_id

    # ③ 草案已注册可下载，含强制水印 + stub 原文（原样存档未删改）
    outputs = _outputs_by_name(client, app, task)
    assert set(outputs.keys()) == {expected["draft_file"]}
    draft = outputs["fta_draft.md"].decode("utf-8")
    assert expected["watermark_substring"] in draft
    assert "不得用于任何" in draft and "安全性判断" in draft
    assert _STUB_DRAFT in draft, "模型草案必须原样存档"

    # ④ model_call 事件落库（info）+ review_requested；tool_runs 为空（fta 不调工具）
    events = client.get(f"/api/tasks/{task_id}/events").json()
    mc = [e for e in events if e["event_type"] == "model_call"]
    assert len(mc) == 1 and mc[0]["level"] == "info"
    assert mc[0]["payload"] == {"profile": "reasoning", "kind": "chat"}
    assert any(e["event_type"] == "review_requested" for e in events)
    folded = [e["payload"].get("workflow_event_type") for e in events if e["event_type"] == "agent_log"]
    assert "fta_reasoning_started" in folded and "fta_draft_generated" in folded

    conn = app.state.conn_factory()
    try:
        assert repos.list_tool_runs(conn, task_id) == []
    finally:
        conn.close()

    # ⑤ 具名人工放行 → completed + review_approved（M1 建成的放行链首次被真实 Agent 使用）
    review = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": "approve", "reviewer": "安全性分析师_李工", "comment": "草案结构合理，割集候选已核"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "completed"

    events_after = client.get(f"/api/tasks/{task_id}/events").json()
    approved = [e for e in events_after if e["event_type"] == "review_approved"]
    assert len(approved) == 1
    assert approved[0]["payload"]["reviewer"] == "安全性分析师_李工"


def test_fta_gateway_upstream_failure_task_failed_honestly(app_env) -> None:
    """真实 ModelGateway + FLAI_LLM_* 环境变量已清空：chat fail-closed 抛
    ModelUpstreamError（不触网络）→ workflow 不吞 → 任务 failed +
    model_call error 事件 + gateway 自身 model_calls 表 failed 行；无草案文件。
    """
    client, app = app_env
    # 不注入 stub：走 create_app 装配的真实 gateway

    task = _create_and_run(client, app, "fta_agent", _FTA_CASE["inputs"])
    task_id = task["id"]

    assert task["status"] == "failed"
    assert "ModelUpstreamError" in task["error_message"]
    assert task["output_file_ids"] == [], "上游失败绝不产出伪造草案"

    events = client.get(f"/api/tasks/{task_id}/events").json()
    mc_error = [e for e in events if e["event_type"] == "model_call" and e["level"] == "error"]
    assert len(mc_error) == 1
    assert "FLAI_LLM" in mc_error[0]["payload"]["error"], "错误信息应如实指向缺失的环境变量"
    assert any(e["event_type"] == "task_failed" for e in events)

    conn = app.state.conn_factory()
    try:
        calls = repos.list_model_calls(conn, task_id)
    finally:
        conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert calls[0]["model_profile"] == "reasoning"


# ── 注册对账：四 Agent 三类型同 Registry ─────────────────────────────────


def test_four_agents_registered_with_expected_categories(app_env) -> None:
    client, app = app_env
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    agents = {a["id"]: a for a in resp.json()}

    expected_categories = {
        "hello_agent": "tool_automation",
        "performance_disk_agent": "tool_automation",
        "control_logic_agent": "structured_gen",
        "fta_agent": "reasoning_assist",
    }
    for agent_id, category in expected_categories.items():
        assert agent_id in agents, f"Agent 未注册：{agent_id}"
        assert agents[agent_id]["category"] == category

    # 泛化实锤：至少三种不同 category 同时在册
    assert len({a["category"] for a in agents.values()}) >= 3

    # fta/control_logic 的关键开关如实注册——经 Registry 查（API 投影刻意只出
    # 门户最小字段集，不透出 workflow/model/tools 治理细节，M2 既定决策，不为测试放宽）
    registry = app.state.agent_registry
    fta = registry.get("fta_agent")
    assert fta["workflow"]["requires_human_review"] is True
    assert fta["model"]["profile"] == "reasoning"
    cl = registry.get("control_logic_agent")
    assert cl["model"]["profile"] == "none"
    assert cl["tools"] == []
