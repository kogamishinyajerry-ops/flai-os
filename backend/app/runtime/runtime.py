"""Agent Runtime：驱动单个任务从 validating 走完整生命周期（docs/05）。

状态机口径说明（偏离 M1 接口契约文字、以 docs/05 + 已交付 statemachine.py 为准，
详见本文件末尾模块级注释）：`running` 成功收尾时**不**直接转 `completed`，
而是先经 `analyzing` 再转 `completed`——docs/05 §2 强制规则原文：
「`running` 不得跳过 `analyzing` 直接进入 `completed`……即使 Agent 没有独立的
"分析"业务逻辑（如 hello_agent），也必须显式迁移，不得省略」，且
`backend/app/core/statemachine.py` 的 TRANSITIONS 里 `running` 集合本就不含
`completed`（该文件已由地基路先行交付并如此实现，若走"running 直转 completed"
会被 `assert_transition` 拒绝，技术上也走不通）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..storage import repos

# event.schema.json 的 event_type 枚举（供折叠判断参考；本文件不据此做「豁免」——
# ADR-0008 原文「workflow 自定义事件统一折叠为 agent_log」是无条件折叠，见
# `_WorkflowEventLogger.log()`，这里留作文档标注用途）。
_EVENT_ENUM = frozenset(
    {
        "task_created", "validation_started", "validation_failed", "case_generated",
        "tool_started", "tool_finished", "tool_failed", "model_call",
        "review_requested", "review_approved", "review_rejected", "summary_generated",
        "task_completed", "task_failed", "task_cancelled", "feedback_received",
        "warning", "error", "agent_log",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _WorkflowEventLogger:
    """context["event_logger"]：workflow.py 唯一可见的事件出口。

    ADR-0008：「workflow 自定义事件统一折叠为 agent_log」——无条件折叠，
    原始类型进 payload.workflow_event_type，事件枚举不因业务 Agent 膨胀。
    """

    def __init__(self, conn: sqlite3.Connection, task_id: str, agent_id: str) -> None:
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id

    def log(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        payload = dict(payload or {})
        payload["workflow_event_type"] = event_type
        repos.append_event(
            self._conn,
            task_id=self._task_id,
            agent_id=self._agent_id,
            event_type="agent_log",
            level="info",
            message=f"workflow 上报事件：{event_type}",
            payload=payload,
        )


class _ToolRegistryContext:
    """context["tool_registry"]：包一层，自动带 conn/task_id，前后发 tool_started/finished|failed。"""

    def __init__(self, tool_registry: Any, conn: sqlite3.Connection, task_id: str, agent_id: str) -> None:
        self._tool_registry = tool_registry
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id

    def call(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        repos.append_event(
            self._conn, task_id=self._task_id, agent_id=self._agent_id,
            event_type="tool_started", level="info",
            message=f"开始调用工具 {tool_id}", payload={"tool_id": tool_id, "input": payload},
        )
        try:
            result = self._tool_registry.call(tool_id, payload, conn=self._conn, task_id=self._task_id)
        except Exception as exc:
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="tool_failed", level="error",
                message=f"工具 {tool_id} 调用失败：{exc}", payload={"tool_id": tool_id, "error": str(exc)},
            )
            raise
        repos.append_event(
            self._conn, task_id=self._task_id, agent_id=self._agent_id,
            event_type="tool_finished", level="info",
            message=f"工具 {tool_id} 调用完成", payload={"tool_id": tool_id, "output_status": result.get("status")},
        )
        return result


class _ModelGatewayContext:
    """context["model_gateway"]：包一层，自动带 task_id/agent_id（model_calls 落库由 Gateway 自身负责）。"""

    def __init__(self, model_gateway: Any, task_id: str, agent_id: str) -> None:
        self._model_gateway = model_gateway
        self._task_id = task_id
        self._agent_id = agent_id

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return self._model_gateway.chat(profile, messages, task_id=self._task_id, agent_id=self._agent_id, **kwargs)

    def embed(self, profile: str, text: str, **kwargs: Any) -> dict[str, Any]:
        return self._model_gateway.embed(profile, text, task_id=self._task_id, agent_id=self._agent_id, **kwargs)

    def vision(self, profile: str, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return self._model_gateway.vision(
            profile, image_path, prompt, task_id=self._task_id, agent_id=self._agent_id, **kwargs
        )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_workflow_module(agent_id: str, workflow_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"flai_agent_{agent_id}_workflow", workflow_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 workflow.py：{workflow_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentRuntime:
    """驱动单个任务从 validating 走完整生命周期：校验 -> running -> (analyzing) -> 终态。"""

    def __init__(
        self,
        agent_registry: Any,
        tool_registry: Any,
        model_gateway: Any,
        conn_factory: Callable[[], sqlite3.Connection],
        task_runs_dir: str | Path,
    ) -> None:
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry
        self.model_gateway = model_gateway
        self.conn_factory = conn_factory
        self.task_runs_dir = Path(task_runs_dir)

    def execute(self, task_id: str) -> dict[str, Any]:
        """驱动任务 task_id（调用前须已处于 validating 态）走完生命周期，返回最终 task dict。"""
        conn = self.conn_factory()
        try:
            return self._execute(conn, task_id)
        finally:
            conn.close()

    def _execute(self, conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        task = repos.get_task(conn, task_id)
        if task is None:
            return {"status": "failed", "error_message": f"任务不存在：{task_id}"}

        agent_id = task["agent_id"]
        agent = self.agent_registry.get(agent_id)
        if agent is None:
            repos.set_task_status(conn, task_id, "failed", error_message=f"Agent 未注册：{agent_id}")
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=f"Agent 未注册：{agent_id}",
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        pkg_dir = self.agent_registry.package_dir(agent_id)

        # 1) 输入校验
        repos.append_event(
            conn, task_id=task_id, agent_id=agent_id, event_type="validation_started",
            level="info", message="开始校验输入",
        )
        try:
            self._validate_inputs(pkg_dir, agent, task["inputs"])
        except Exception as exc:
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="validation_failed",
                level="error", message=f"输入校验未通过：{exc}",
            )
            repos.set_task_status(conn, task_id, "failed", error_message=f"输入校验未通过：{exc}")
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=f"输入校验未通过：{exc}",
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # 2) 进入 running，构建 context 并调用 workflow.run()
        repos.set_task_status(conn, task_id, "running")
        output_dir = self.task_runs_dir / task_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        context = self._build_context(conn, task, agent, pkg_dir, output_dir)

        try:
            workflow_module = _load_workflow_module(agent_id, pkg_dir / "workflow.py")
            result = workflow_module.run(context)
        except Exception as exc:
            error_message = f"{exc.__class__.__name__}: {exc}"
            repos.set_task_status(conn, task_id, "failed", error_message=error_message)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=f"workflow 执行异常：{error_message}",
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        if not isinstance(result, dict) or result.get("status") != "success":
            error_message = (result or {}).get("error_message", "workflow 返回失败态") if isinstance(result, dict) else "workflow 返回值非法"
            repos.set_task_status(conn, task_id, "failed", error_message=error_message)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=error_message,
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # 3) 成功：注册产物 + 样本沉淀
        output_file_ids = self._register_outputs(conn, task_id, output_dir)
        repos.set_task_outputs(conn, task_id, output_file_ids)

        if agent.get("data_asset", {}).get("collect_samples"):
            repos.record_sample(
                conn,
                task_id=task_id,
                agent_id=agent_id,
                agent_version=task["agent_version"],
                input_json=task["inputs"],
                output_json=result,
            )

        if agent.get("workflow", {}).get("requires_human_review"):
            repos.set_task_status(conn, task_id, "waiting_review")
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="review_requested",
                level="info", message="任务需要人工审核放行",
            )
            return {"status": "waiting_review", "task": repos.get_task(conn, task_id)}

        # docs/05 §2 强制规则：running 不得跳过 analyzing 直接进 completed。
        repos.set_task_status(conn, task_id, "analyzing")
        repos.set_task_status(conn, task_id, "completed")
        repos.append_event(
            conn, task_id=task_id, agent_id=agent_id, event_type="task_completed",
            level="info", message="任务完成",
        )
        return {"status": "completed", "task": repos.get_task(conn, task_id)}

    def _validate_inputs(self, pkg_dir: Path, agent: dict[str, Any], inputs: dict[str, Any]) -> None:
        import json

        from jsonschema import validate as jsonschema_validate

        schema_name = agent.get("input", {}).get("schema")
        if not schema_name:
            return
        schema_path = pkg_dir / schema_name
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema_validate(inputs, schema)

    def _build_context(
        self,
        conn: sqlite3.Connection,
        task: dict[str, Any],
        agent: dict[str, Any],
        pkg_dir: Path,
        output_dir: Path,
    ) -> dict[str, Any]:
        agent_id = task["agent_id"]
        files: list[dict[str, Any]] = []
        for fid in task.get("input_file_ids", []):
            f = repos.get_file(conn, fid)
            if f is None:
                # P3-4：引用不存在的 file_id 不得静默消失——发 warning 事件留痕，
                # 再跳过该项（无事件=没发生的另一面：数据缺失也要留痕，不能只是
                # context.files 悄悄变短）。
                repos.append_event(
                    conn, task_id=task["id"], agent_id=agent_id, event_type="warning",
                    level="warning",
                    message=f"输入文件引用不存在，已跳过：file_id={fid}",
                    payload={"missing_file_id": fid},
                )
                continue
            files.append(f)
        return {
            "task": task,
            "inputs": task["inputs"],
            "files": files,
            "model_gateway": _ModelGatewayContext(self.model_gateway, task["id"], agent_id),
            "tool_registry": _ToolRegistryContext(self.tool_registry, conn, task["id"], agent_id),
            "event_logger": _WorkflowEventLogger(conn, task["id"], agent_id),
            "output_dir": str(output_dir),
            "agent_config": agent,
        }

    def _register_outputs(self, conn: sqlite3.Connection, task_id: str, output_dir: Path) -> list[str]:
        file_ids: list[str] = []
        if not output_dir.is_dir():
            return file_ids
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            file_id = str(uuid.uuid4())
            repos.create_file(
                conn,
                file_id=file_id,
                task_id=task_id,
                kind="output",
                filename=path.name,
                path=str(path),
                size_bytes=path.stat().st_size,
                sha256=_sha256_file(path),
            )
            file_ids.append(file_id)
        return file_ids
