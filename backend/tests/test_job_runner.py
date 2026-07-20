"""JobRunner 单元测试：run_once 拾取/空跑语义，脱离 FastAPI 直接装配依赖。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.jobs import runner as runner_module
from backend.app.jobs.runner import (
    JobRunner,
    WorkerAlreadyRunningError,
    recover_interrupted_tasks,
    run_worker_forever,
    worker_singleton_lock,
)
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


def _create_task_at_status(conn_factory, task_id: str, statuses: tuple[str, ...]) -> None:
    conn = conn_factory()
    try:
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="Runner 状态兜底测试",
            created_by="tester",
            inputs={"name": "状态守卫"},
            input_file_ids=[],
            metadata={},
        )
        for status in statuses:
            repos.set_task_status(conn, task_id, status)
    finally:
        conn.close()


def test_mark_failed_best_effort_refuses_waiting_review(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    task_id = "task_waiting_review_guard"
    _create_task_at_status(
        conn_factory,
        task_id,
        ("queued", "validating", "running", "waiting_review"),
    )

    runner = JobRunner(object(), conn_factory)
    runner._mark_failed_best_effort(task_id, RuntimeError("审核事件展示失败"))

    conn = conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        events = repos.list_events(conn, task_id)
    finally:
        conn.close()

    assert task["status"] == "waiting_review"
    assert not any(event["event_type"] == "task_failed" for event in events)
    warnings = [event for event in events if event["event_type"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["level"] == "error"


def test_mark_failed_best_effort_still_fails_running_task(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    task_id = "task_running_failure_fallback"
    _create_task_at_status(conn_factory, task_id, ("queued", "validating", "running"))

    runner = JobRunner(object(), conn_factory)
    runner._mark_failed_best_effort(task_id, RuntimeError("执行阶段炸裂"))

    conn = conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        events = repos.list_events(conn, task_id)
    finally:
        conn.close()

    assert task["status"] == "failed"
    assert "RuntimeError" in task["error_message"]
    failed_events = [event for event in events if event["event_type"] == "task_failed"]
    assert len(failed_events) == 1


# ── CDX-7：worker 单实例锁与崩溃恢复 ─────────────────────────────────────


def test_recover_interrupted_tasks_fails_all_execution_states(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    execution_paths = {
        "task_interrupted_validating": ("queued", "validating"),
        "task_interrupted_running": ("queued", "validating", "running"),
        "task_interrupted_parsing": ("queued", "validating", "running", "parsing"),
        "task_interrupted_analyzing": ("queued", "validating", "running", "analyzing"),
    }
    for task_id, statuses in execution_paths.items():
        _create_task_at_status(conn_factory, task_id, statuses)

    assert recover_interrupted_tasks(conn_factory) == len(execution_paths)

    conn = conn_factory()
    try:
        for task_id in execution_paths:
            task = repos.get_task(conn, task_id)
            events = repos.list_events(conn, task_id)
            assert task["status"] == "failed"
            assert "worker_interrupted" in task["error_message"]
            failed_events = [event for event in events if event["event_type"] == "task_failed"]
            assert len(failed_events) == 1
            assert failed_events[0]["payload"] == {"worker_interrupted": True}
    finally:
        conn.close()


def test_recover_interrupted_tasks_leaves_non_execution_states_untouched(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    untouched_paths = {
        "task_interrupted_created_guard": (),
        "task_interrupted_queued_guard": ("queued",),
        "task_interrupted_review_guard": (
            "queued", "validating", "running", "waiting_review",
        ),
        "task_interrupted_completed_guard": (
            "queued", "validating", "running", "analyzing", "completed",
        ),
        "task_interrupted_failed_guard": ("queued", "validating", "failed"),
        "task_interrupted_cancelled_guard": ("queued", "cancelled"),
    }
    for task_id, statuses in untouched_paths.items():
        _create_task_at_status(conn_factory, task_id, statuses)

    assert recover_interrupted_tasks(conn_factory) == 0

    conn = conn_factory()
    try:
        expected_statuses = {
            task_id: statuses[-1] if statuses else "created"
            for task_id, statuses in untouched_paths.items()
        }
        for task_id, expected_status in expected_statuses.items():
            assert repos.get_task(conn, task_id)["status"] == expected_status
            assert repos.list_events(conn, task_id) == []
    finally:
        conn.close()


def test_recover_interrupted_tasks_is_idempotent(runtime_env) -> None:
    conn_factory = runtime_env["conn_factory"]
    task_id = "task_interrupted_idempotent"
    _create_task_at_status(conn_factory, task_id, ("queued", "validating", "running"))

    assert recover_interrupted_tasks(conn_factory) == 1
    conn = conn_factory()
    try:
        first_task = repos.get_task(conn, task_id)
        first_events = repos.list_events(conn, task_id)
    finally:
        conn.close()

    assert recover_interrupted_tasks(conn_factory) == 0
    conn = conn_factory()
    try:
        second_task = repos.get_task(conn, task_id)
        second_events = repos.list_events(conn, task_id)
    finally:
        conn.close()

    assert second_task == first_task
    assert second_events == first_events
    assert len([event for event in second_events if event["event_type"] == "task_failed"]) == 1


def test_worker_singleton_lock_rejects_second_independent_open(tmp_path) -> None:
    lock_path = tmp_path / "worker.lock"
    with worker_singleton_lock(lock_path):
        # 两个上下文会分别 open 同一路径；第二个非阻塞加锁必须立即失败。
        with pytest.raises(WorkerAlreadyRunningError):
            with worker_singleton_lock(lock_path):
                pass


def test_worker_singleton_lock_can_be_reacquired_after_release(tmp_path) -> None:
    lock_path = tmp_path / "worker.lock"
    with worker_singleton_lock(lock_path):
        pass
    with worker_singleton_lock(lock_path):
        pass


def test_worker_entrypoint_lock_conflict_exits_nonzero_before_assemble(
    tmp_path, capsys,
) -> None:
    lock_path = tmp_path / "worker.lock"
    assembled = False

    def runner_factory() -> JobRunner:
        nonlocal assembled
        assembled = True
        raise AssertionError("锁冲突时不应装配 runner")

    def conn_factory():
        raise AssertionError("锁冲突时不应连接数据库")

    with worker_singleton_lock(lock_path):
        exit_code = run_worker_forever(runner_factory, conn_factory, lock_path)

    stderr = capsys.readouterr().err
    assert exit_code != 0
    assert assembled is False
    assert "已有 worker 正在运行" in stderr
    assert "拒绝并行启动第二个 worker" in stderr


def test_worker_entrypoint_recovers_under_lock_before_polling(tmp_path, monkeypatch) -> None:
    lock_path = tmp_path / "worker.lock"
    order: list[str] = []

    class _StubRunner:
        def run_forever(self) -> None:
            order.append("poll")

        def close(self) -> None:
            order.append("close")

    def runner_factory():
        order.append("assemble")
        return _StubRunner()

    def fake_recover(conn_factory) -> int:
        order.append("recover")
        with pytest.raises(WorkerAlreadyRunningError):
            with worker_singleton_lock(lock_path):
                pass
        return 0

    monkeypatch.setattr(runner_module, "recover_interrupted_tasks", fake_recover)
    assert run_worker_forever(runner_factory, lambda: None, lock_path) == 0
    assert order == ["assemble", "recover", "poll", "close"]
