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
