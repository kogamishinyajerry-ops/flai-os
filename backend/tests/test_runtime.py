"""AgentRuntime 测试：真实 hello_agent + 真实 mock_echo 走通完整生命周期。

依赖说明（跨 lane 交付顺序偏离，显式报告）：`backend/app/tools/registry.py`
与 `backend/app/model_gateway/gateway.py` 是另两路分工，写测试时尚未交付
（`backend/app/tools/` 与 `backend/app/model_gateway/` 目录下只有 `__init__.py`）。
本文件用 `_RealishToolRegistry`/`_FakeModelGateway` 作为最小忠实替身：前者不是
伪造数据——真实读 `tools_impl/mock_tools/tool.yaml`、真实 jsonschema 校验入参
出参、真实 `importlib` 调用 `tools_impl.mock_tools.adapter.run`、真实落
`tool_runs` 表，接口形状对齐 M1 契约里 `ToolRegistry.call(tool_id, payload, *,
conn=None, task_id=None)` 约定；后者未被 hello_agent 调用（`model.profile=none`），
仅满足 `AgentRuntime.__init__` 的构造签名。两者与正式实现接口一致，理论上
正式 `backend/app/tools/registry.py` 落地后可直接替换，无需改动
`backend/app/runtime/runtime.py`。
"""

from __future__ import annotations

import importlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db

_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _RealishToolRegistry:
    """`backend/app/tools/registry.py` 尚未交付时的最小忠实替身（见模块 docstring）。"""

    def __init__(self, tools_dir: Path) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        for entry in sorted(Path(tools_dir).iterdir()):
            yaml_path = entry / "tool.yaml"
            if yaml_path.is_file():
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                self._tools[data["id"]] = data

    def call(self, tool_id: str, payload: dict[str, Any], *, conn=None, task_id=None) -> dict[str, Any]:
        from backend.app.core.errors import (
            ToolInputInvalidError,
            ToolNotRegisteredError,
            ToolOutputInvalidError,
        )

        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotRegisteredError(f"未注册工具：{tool_id}")

        started_at = _now_iso()

        def _fail(exc_cls, message: str):
            if conn is not None:
                repos.record_tool_run(
                    conn, task_id=task_id, tool_id=tool_id, tool_version=tool["version"],
                    mock=bool(tool.get("mock", False)), status="failed", input_json=payload,
                    error_message=message, started_at=started_at, finished_at=_now_iso(),
                )
            raise exc_cls(message)

        try:
            jsonschema.validate(payload, tool["input_schema"])
        except jsonschema.ValidationError as exc:
            _fail(ToolInputInvalidError, str(exc))

        module_path, func_name = tool["entrypoint"].split(":")
        module = importlib.import_module(module_path)
        output = getattr(module, func_name)(payload)

        try:
            jsonschema.validate(output, tool["output_schema"])
        except jsonschema.ValidationError as exc:
            _fail(ToolOutputInvalidError, str(exc))

        if conn is not None:
            repos.record_tool_run(
                conn, task_id=task_id, tool_id=tool_id, tool_version=tool["version"],
                mock=bool(tool.get("mock", False)), status="success", input_json=payload,
                output_json=output, started_at=started_at, finished_at=_now_iso(),
            )
        return output


class _FakeModelGateway:
    """hello_agent 是 0-LLM 示例（model.profile=none），本替身预期不会被调用。"""

    def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hello_agent 不应调用 model_gateway")

    def embed(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hello_agent 不应调用 model_gateway")

    def vision(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hello_agent 不应调用 model_gateway")


def _make_runtime(agents_dir: Path, tmp_path: Path) -> tuple[AgentRuntime, Path]:
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()
    assert registry.errors == [], f"意外的无效包：{registry.errors}"
    runtime = AgentRuntime(
        agent_registry=registry,
        tool_registry=_RealishToolRegistry(TOOLS_DIR),
        model_gateway=_FakeModelGateway(),
        conn_factory=lambda: get_conn(db_path),
        task_runs_dir=tmp_path / "task_runs",
    )
    return runtime, db_path


def _create_and_queue_task(db_path: Path, *, agent_id: str, inputs: dict[str, Any]) -> str:
    conn = get_conn(db_path)
    try:
        task = repos.create_task(
            conn, task_id="task_1", agent_id=agent_id, agent_version="0.1.0",
            name="测试任务", created_by="tester", inputs=inputs, input_file_ids=[], metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
        repos.set_task_status(conn, task["id"], "validating")
        return task["id"]
    finally:
        conn.close()


def test_execute_success_full_event_sequence(tmp_path: Path) -> None:
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="hello_agent", inputs={"name": "世界"})

    result = runtime.execute(task_id)

    assert result["status"] == "completed"
    assert result["task"]["status"] == "completed"

    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        event_types = [e["event_type"] for e in events]
        assert event_types == [
            "validation_started",
            "agent_log",  # 折叠自 workflow 的 "agent_started"
            "tool_started",
            "tool_finished",
            "agent_log",  # 折叠自 workflow 的 "agent_completed"
            "task_completed",
        ]
        folded_types = [e["payload"]["workflow_event_type"] for e in events if e["event_type"] == "agent_log"]
        assert folded_types == ["agent_started", "agent_completed"]

        files = conn.execute(
            "SELECT * FROM files WHERE task_id = ? AND kind = 'output'", (task_id,)
        ).fetchall()
        assert len(files) == 1
        assert files[0]["filename"] == "hello_output.json"

        samples = repos.list_samples(conn, task_id)
        assert len(samples) == 1
        assert samples[0]["input"] == {"name": "世界"}

        tool_runs = repos.list_tool_runs(conn, task_id)
        assert len(tool_runs) == 1
        assert tool_runs[0]["status"] == "success"
        assert tool_runs[0]["mock"] is True
    finally:
        conn.close()


def test_execute_validation_failure(tmp_path: Path) -> None:
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="hello_agent", inputs={})  # 缺 name

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert result["task"]["status"] == "failed"

    conn = get_conn(db_path)
    try:
        event_types = [e["event_type"] for e in repos.list_events(conn, task_id)]
        assert event_types == ["validation_started", "validation_failed", "task_failed"]
        assert repos.list_tool_runs(conn, task_id) == []
    finally:
        conn.close()


def test_execute_workflow_exception_does_not_crash(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    broken_dir = agents_dir / "broken_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", broken_dir)

    yaml_path = broken_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8").replace("id: hello_agent", "id: broken_agent")
    yaml_path.write_text(yaml_text, encoding="utf-8")

    (broken_dir / "workflow.py").write_text(
        "def run(context):\n"
        "    raise ValueError('boom - simulated workflow crash')\n",
        encoding="utf-8",
    )

    runtime, db_path = _make_runtime(agents_dir, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="broken_agent", inputs={"name": "x"})

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert result["task"]["status"] == "failed"
    assert "boom" in result["task"]["error_message"]

    conn = get_conn(db_path)
    try:
        event_types = [e["event_type"] for e in repos.list_events(conn, task_id)]
        assert event_types == ["validation_started", "task_failed"]
        assert "boom" in repos.list_events(conn, task_id)[-1]["message"]
    finally:
        conn.close()


def test_tool_call_outside_agent_whitelist_denied_with_event(tmp_path: Path) -> None:
    """P1-A default-deny witness：mock_echo 已在 Tool Registry 注册，但 Agent 的
    agent.yaml.tools 白名单为空——调用必须被拒（ToolNotAllowedError→任务 failed）、
    留 tool_failed 事件（payload.denied 标注）、且绝不触达 Registry（无 tool_started、
    无 tool_runs 行）。若拆掉 _ToolRegistryContext 的白名单校验，本测试变红。
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    greedy_dir = agents_dir / "greedy_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", greedy_dir)

    yaml_path = greedy_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    yaml_text = yaml_text.replace("id: hello_agent", "id: greedy_agent")
    # 白名单清空：mock_echo 仍是已注册工具，但不在本 Agent 白名单内。
    assert "tools:\n  - mock_echo" in yaml_text, "hello_agent 样板 tools 声明形态变了，测试前提失效"
    yaml_text = yaml_text.replace("tools:\n  - mock_echo", "tools: []")
    yaml_path.write_text(yaml_text, encoding="utf-8")

    runtime, db_path = _make_runtime(agents_dir, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="greedy_agent", inputs={"name": "越权"})

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "ToolNotAllowedError" in result["task"]["error_message"]

    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        event_types = [e["event_type"] for e in events]
        assert "tool_started" not in event_types, "白名单拒绝必须发生在触达 Registry 之前"
        denied_events = [
            e for e in events
            if e["event_type"] == "tool_failed" and e["payload"].get("denied") == "not_in_agent_whitelist"
        ]
        assert len(denied_events) == 1
        assert denied_events[0]["payload"]["tool_id"] == "mock_echo"
        assert repos.list_tool_runs(conn, task_id) == [], "被拒调用不应产生 tool_runs 行"
    finally:
        conn.close()


def test_tool_call_inside_whitelist_still_works(tmp_path: Path) -> None:
    """P1-A 反面对照：白名单内的 mock_echo 正常路径回归不碎（真实 hello_agent 全链）。"""
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="hello_agent", inputs={"name": "合法调用"})
    result = runtime.execute(task_id)
    assert result["status"] == "completed"


# ── P2-1：model_call 事件（无事件=没发生）────────────────────────────────


class _StubOkGateway:
    def chat(self, profile, messages, **kwargs):
        return {"content": "你好", "token_usage": None, "model_name": "stub"}

    def embed(self, profile, text, **kwargs):
        return {"vector": [0.1], "model_name": "stub"}


class _StubBoomGateway:
    def chat(self, profile, messages, **kwargs):
        raise RuntimeError("上游炸了（测试注入）")


def _make_conn(tmp_path: Path):
    db_path = tmp_path / "ctx_test.db"
    init_db(db_path)
    return get_conn(db_path)


def _make_task(conn, task_id: str) -> None:
    repos.create_task(
        conn, task_id=task_id, agent_id="hello_agent", agent_version="0.1.0",
        name="ctx 测试", created_by="tester", inputs={}, input_file_ids=[], metadata={},
    )


def test_model_gateway_context_emits_model_call_event_on_success(tmp_path: Path) -> None:
    from backend.app.runtime.runtime import _ModelGatewayContext

    conn = _make_conn(tmp_path)
    try:
        _make_task(conn, "task_mc_ok")
        ctx = _ModelGatewayContext(_StubOkGateway(), conn, "task_mc_ok", "hello_agent")

        result = ctx.chat("reasoning", [{"role": "user", "content": "hi"}])
        assert result["content"] == "你好"
        ctx.embed("fast", "text")

        events = repos.list_events(conn, "task_mc_ok")
        mc = [e for e in events if e["event_type"] == "model_call"]
        assert len(mc) == 2
        assert mc[0]["level"] == "info"
        assert mc[0]["payload"] == {"profile": "reasoning", "kind": "chat"}
        assert mc[1]["payload"] == {"profile": "fast", "kind": "embed"}
    finally:
        conn.close()


def test_model_gateway_context_emits_error_model_call_event_and_reraises(tmp_path: Path) -> None:
    from backend.app.runtime.runtime import _ModelGatewayContext

    conn = _make_conn(tmp_path)
    try:
        _make_task(conn, "task_mc_boom")
        ctx = _ModelGatewayContext(_StubBoomGateway(), conn, "task_mc_boom", "hello_agent")

        with pytest.raises(RuntimeError):
            ctx.chat("reasoning", [{"role": "user", "content": "hi"}])

        events = repos.list_events(conn, "task_mc_boom")
        mc = [e for e in events if e["event_type"] == "model_call"]
        assert len(mc) == 1
        assert mc[0]["level"] == "error"
        assert mc[0]["payload"]["profile"] == "reasoning"
        assert mc[0]["payload"]["kind"] == "chat"
        assert "上游炸了" in mc[0]["payload"]["error"]
    finally:
        conn.close()


# ── P2-2：工具契约可恢复失败（status:"failed"）如实记 tool_failed ─────────


class _FailedStatusToolRegistry:
    """契约内可恢复失败：不抛异常，返回 status:"failed"。

    说明：真实 mock_echo 的失败分支（message 缺失/非 object）会先被 Registry 的
    input_schema 校验拦截、走异常路径，无法穿透到「契约内 failed 返回」这条路，
    故此处用 stub 构造（返回形状对齐 ToolRegistry.call 的输出契约）。
    """

    def call(self, tool_id, payload, *, conn=None, task_id=None):
        return {"status": "failed", "echoed": {}, "error_message": "case 级可恢复失败（测试注入）"}


def test_tool_context_reports_tool_failed_on_failed_status(tmp_path: Path) -> None:
    from backend.app.runtime.runtime import _ToolRegistryContext

    conn = _make_conn(tmp_path)
    try:
        _make_task(conn, "task_tool_softfail")
        ctx = _ToolRegistryContext(
            _FailedStatusToolRegistry(), conn, "task_tool_softfail", "hello_agent",
            frozenset({"soft_fail_tool"}),
        )

        result = ctx.call("soft_fail_tool", {"message": {"x": 1}})
        assert result["status"] == "failed"  # 结果原样透传给 workflow，由其决定单 case 处置

        events = repos.list_events(conn, "task_tool_softfail")
        event_types = [e["event_type"] for e in events]
        assert event_types == ["tool_started", "tool_failed"], "status:failed 不得误报 tool_finished"
        failed = events[-1]
        assert failed["level"] == "error"
        assert failed["payload"]["output_status"] == "failed"
        assert "case 级可恢复失败" in failed["payload"]["error"]
    finally:
        conn.close()


def test_execute_skips_missing_input_file_id_with_warning_event(tmp_path: Path) -> None:
    """P3-4：input_file_ids 引用了不存在的 file_id——context.files 必须跳过该项，
    且不得静默消失，须发一条 warning 事件留痕（修此前 _build_context 的静默跳过）。
    """
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    conn = get_conn(db_path)
    try:
        task = repos.create_task(
            conn, task_id="task_missing_file", agent_id="hello_agent", agent_version="0.1.0",
            name="缺文件引用测试", created_by="tester", inputs={"name": "世界"},
            input_file_ids=["file_does_not_exist"], metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
        repos.set_task_status(conn, task["id"], "validating")
    finally:
        conn.close()

    result = runtime.execute("task_missing_file")
    assert result["status"] == "completed", "缺失文件引用不应阻断任务本身（hello_agent 不消费 files）"

    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, "task_missing_file")
        warning_events = [e for e in events if e["event_type"] == "warning"]
        assert len(warning_events) == 1
        assert warning_events[0]["payload"]["missing_file_id"] == "file_does_not_exist"
        assert warning_events[0]["level"] == "warning"
    finally:
        conn.close()


def test_execute_requires_human_review(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    review_dir = agents_dir / "review_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", review_dir)

    yaml_path = review_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    yaml_text = yaml_text.replace("id: hello_agent", "id: review_agent")
    yaml_text = yaml_text.replace("requires_human_review: false", "requires_human_review: true")
    yaml_path.write_text(yaml_text, encoding="utf-8")

    runtime, db_path = _make_runtime(agents_dir, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="review_agent", inputs={"name": "世界"})

    result = runtime.execute(task_id)

    assert result["status"] == "waiting_review"
    assert result["task"]["status"] == "waiting_review"

    conn = get_conn(db_path)
    try:
        event_types = [e["event_type"] for e in repos.list_events(conn, task_id)]
        assert event_types == [
            "validation_started",
            "agent_log",
            "tool_started",
            "tool_finished",
            "agent_log",
            "review_requested",
        ]
        assert "task_completed" not in event_types
        # 即使等人工放行，样本/产物依然在收尾前完成沉淀（spec：先注册产物+样本，再判 review/completed）。
        assert len(repos.list_samples(conn, task_id)) == 1
    finally:
        conn.close()


def test_review_requested_event_failure_keeps_waiting_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """展示性 review_requested 写失败时，已提交的人工审核态仍须安全返回。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    review_dir = agents_dir / "review_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", review_dir)

    yaml_path = review_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    yaml_text = yaml_text.replace("id: hello_agent", "id: review_agent")
    yaml_text = yaml_text.replace("requires_human_review: false", "requires_human_review: true")
    yaml_path.write_text(yaml_text, encoding="utf-8")

    runtime, db_path = _make_runtime(agents_dir, tmp_path)
    task_id = _create_and_queue_task(db_path, agent_id="review_agent", inputs={"name": "世界"})
    real_append_event = repos.append_event

    def fail_review_requested(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("event_type") == "review_requested":
            raise RuntimeError("模拟 review_requested 入库失败")
        return real_append_event(*args, **kwargs)

    monkeypatch.setattr(repos, "append_event", fail_review_requested)
    result = runtime.execute(task_id)

    assert result["status"] == "waiting_review"
    assert result["task"]["status"] == "waiting_review"
    conn = get_conn(db_path)
    try:
        task = repos.get_task(conn, task_id)
        event_types = [event["event_type"] for event in repos.list_events(conn, task_id)]
    finally:
        conn.close()
    assert task["status"] == "waiting_review"
    assert "review_requested" not in event_types
    assert "task_failed" not in event_types
