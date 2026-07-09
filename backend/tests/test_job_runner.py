"""JobRunner 单元测试：run_once 拾取/空跑语义，脱离 FastAPI 直接装配依赖。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.jobs.runner import JobRunner
from backend.app.model_gateway.gateway import ModelGateway
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.tools.registry import ToolRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def runtime_env(tmp_path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)

    agent_registry = AgentRegistry(REPO_ROOT / "agents", REPO_ROOT / "contracts" / "agent.schema.json")
    agent_registry.scan()
    tool_registry = ToolRegistry(REPO_ROOT / "tools_impl", REPO_ROOT / "contracts" / "tool.schema.json")
    tool_registry.scan()

    conn = get_conn(db_path)
    try:
        agent_registry.sync_to_db(conn)
    finally:
        conn.close()

    def conn_factory():
        return get_conn(db_path)

    model_gateway = ModelGateway(
        REPO_ROOT / "backend" / "app" / "model_gateway" / "profiles.yaml", conn_factory=conn_factory
    )

    task_runs_dir = tmp_path / "task_runs"
    runtime = AgentRuntime(agent_registry, tool_registry, model_gateway, conn_factory, task_runs_dir)
    return {
        "conn_factory": conn_factory,
        "runtime": runtime,
    }


def test_run_once_returns_false_when_no_queued_task(runtime_env) -> None:
    runner = JobRunner(runtime_env["runtime"], runtime_env["conn_factory"])
    assert runner.run_once() is False


def test_run_once_executes_queued_hello_agent_task(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    conn = conn_factory()
    try:
        task = repos.create_task(
            conn,
            task_id="task_job_runner_case",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="job runner 测试",
            created_by="tester",
            inputs={"name": "小红"},
            input_file_ids=[],
            metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
    finally:
        conn.close()

    runner = JobRunner(runtime_env["runtime"], conn_factory)
    assert runner.run_once() is True

    conn = conn_factory()
    try:
        finished = repos.get_task(conn, "task_job_runner_case")
        events = repos.list_events(conn, "task_job_runner_case")
    finally:
        conn.close()

    assert finished["status"] == "completed"
    assert any(e["event_type"] == "task_completed" for e in events)

    # 无更多 queued 任务，第二次 run_once 应为空跑。
    runner2 = JobRunner(runtime_env["runtime"], conn_factory)
    assert runner2.run_once() is False


# ── P2-5：cancel 竞态兜底，run_once 绝不裸抛 ──────────────────────────────


class _CancelRaceRuntime:
    """测试用 runtime 包装：真正 execute() 前，先用另一条连接把任务从
    validating 抢先转去 cancelled，确定性模拟"claim 到 validating 后被外部
    竞态取消"的时序（单线程测试里没法用真并发复现，但效果等价：真实
    AgentRuntime.execute() 内部随后会尝试 validating -> running，读到的却已是
    cancelled，assert_transition 必炸 IllegalTransitionError——这正是
    JobRunner.run_once 需要兜住的场景）。
    """

    def __init__(self, real_runtime: AgentRuntime, conn_factory) -> None:
        self._real = real_runtime
        self._conn_factory = conn_factory

    def execute(self, task_id: str) -> dict[str, Any]:
        conn = self._conn_factory()
        try:
            repos.set_task_status(conn, task_id, "cancelled")
        finally:
            conn.close()
        return self._real.execute(task_id)


def test_run_once_survives_cancel_race_illegal_transition(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    conn = conn_factory()
    try:
        task = repos.create_task(
            conn,
            task_id="task_cancel_race",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="cancel 竞态测试",
            created_by="tester",
            inputs={"name": "竞态"},
            input_file_ids=[],
            metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
    finally:
        conn.close()

    racing_runtime = _CancelRaceRuntime(runtime_env["runtime"], conn_factory)
    runner = JobRunner(racing_runtime, conn_factory)

    # 核心断言：run_once 不裸抛 IllegalTransitionError，进程性存活。
    did_work = runner.run_once()
    assert did_work is True

    conn = conn_factory()
    try:
        final_task = repos.get_task(conn, "task_cancel_race")
        events = repos.list_events(conn, "task_cancel_race")
    finally:
        conn.close()

    # 竞态发生时任务已被"抢先取消"，且非法迁移被 BEGIN IMMEDIATE 事务整体回滚，
    # 不会留下半吊子的 running 态。
    assert final_task["status"] == "cancelled"
    warning_events = [e for e in events if e["event_type"] == "warning"]
    assert len(warning_events) == 1
    assert warning_events[0]["payload"]["race"] == "illegal_transition"

    # runner 存活：紧接着的下一次 run_once 仍能正常空跑，不受上次异常影响。
    runner2 = JobRunner(racing_runtime, conn_factory)
    assert runner2.run_once() is False


class _ExplodingRuntime:
    """runtime.execute 直接抛普通异常——模拟 AgentRuntime 内部兜底之外的
    意外炸点（如 conn 故障），驱动 run_once 的通用 `except Exception` 分支。
    """

    def execute(self, task_id: str) -> dict[str, Any]:
        raise RuntimeError("runtime 意外炸裂（测试注入）")


def test_run_once_generic_exception_marks_task_failed(runtime_env) -> None:
    """通用异常兜底 witness（loop-auditor 收口审计 gap-2）：run_once 绝不裸抛，
    任务被尽力置 failed 且留 task_failed 事件——若删除 runner.py 的
    `except Exception` 分支或 `_mark_failed_best_effort`，本测试变红。
    """
    conn_factory = runtime_env["conn_factory"]
    conn = conn_factory()
    try:
        task = repos.create_task(
            conn,
            task_id="task_generic_boom",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="通用异常兜底测试",
            created_by="tester",
            inputs={"name": "炸"},
            input_file_ids=[],
            metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
    finally:
        conn.close()

    runner = JobRunner(_ExplodingRuntime(), conn_factory)
    did_work = runner.run_once()
    assert did_work is True

    conn = conn_factory()
    try:
        final_task = repos.get_task(conn, "task_generic_boom")
        events = repos.list_events(conn, "task_generic_boom")
    finally:
        conn.close()

    assert final_task["status"] == "failed"
    assert "RuntimeError" in (final_task.get("error_message") or "")
    failed_events = [e for e in events if e["event_type"] == "task_failed"]
    assert len(failed_events) == 1
    assert "兜底" in failed_events[0]["message"]
