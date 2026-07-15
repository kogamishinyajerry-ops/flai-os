"""Gate2-T1-M1 per-task 墙钟 reaper 单测 + tamper 见证。

覆盖：
- reaper 成功路径（执行态任务超时 → failed + payload.reaper='wall_timeout' 事件）；
- 人签保护（waiting_review/终态 → reaper 拒绝置 failed，记 auto_fail_refused）；
- run_once 集成主 witness（挂死任务被 reap + 队列继续认领下一条）——**M1 主 tamper 锚**；
- 正常任务不误杀（reaper 只咬真挂死，快任务照常 completed）；
- fail-closed（reaper 内部异常 → worker 存活、状态不动）；
- 后置副作用面（owner 加验收 #5：reaped 终态受 assert_transition 保护，僵尸续写不翻转终态）；
- 1s 墙钟下限 load-bearing（env=0 被 max(1.0,…) 夹到 1.0，防秒杀合法任务）。

每处 tamper（拆一层→对应断言红）标在测试 docstring。
"""

from __future__ import annotations

import contextlib
import importlib
import sqlite3
import threading
import types
from pathlib import Path

import pytest

from backend.app.core.errors import IllegalTransitionError
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
    """真 registry + hello_agent + mock_echo（确定性、无 LLM）装配在 tmp DB，绝不碰 data/。"""
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
    runtime = AgentRuntime(
        agent_registry, tool_registry, model_gateway, conn_factory, tmp_path / "task_runs"
    )
    return {"conn_factory": conn_factory, "runtime": runtime}


def _create_queued(conn_factory, task_id: str, *, name: str = "小挂") -> None:
    conn = conn_factory()
    try:
        repos.create_task(
            conn, task_id=task_id, agent_id="hello_agent", agent_version="0.1.0",
            name="reaper 测试", created_by="tester", inputs={"name": name},
            input_file_ids=[], metadata={},
        )
        repos.set_task_status(conn, task_id, "queued")
    finally:
        conn.close()


def _drive_to(conn_factory, task_id: str, statuses: tuple[str, ...]) -> None:
    conn = conn_factory()
    try:
        repos.create_task(
            conn, task_id=task_id, agent_id="hello_agent", agent_version="0.1.0",
            name="reaper 状态测试", created_by="tester", inputs={"name": "态"},
            input_file_ids=[], metadata={},
        )
        for status in statuses:
            repos.set_task_status(conn, task_id, status)
    finally:
        conn.close()


def _status_counts(conn_factory, task_ids: tuple[str, ...]) -> dict[str, int]:
    conn = conn_factory()
    try:
        counts: dict[str, int] = {}
        for tid in task_ids:
            st = repos.get_task(conn, tid)["status"]
            counts[st] = counts.get(st, 0) + 1
        return counts
    finally:
        conn.close()


class _BlockingRuntime:
    """execute() 阻塞在 release Event 上（永不自行改 DB 状态），确定性模拟'任务在
    runtime.execute 内挂死'。用于驱动 run_once 的墙钟 reaper 路径。绝不写库 → reaper 的
    BEGIN IMMEDIATE 无写锁竞争，reaper 路径干净可测。"""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls: list[str] = []

    def execute(self, task_id: str) -> dict:
        self.calls.append(task_id)
        self.release.wait(timeout=30.0)  # 兜底上限；正常由测试 finally/看门狗释放
        return {"status": "completed"}


# ── reaper 成功路径：执行态任务超时 → failed 留痕 ──────────────────────────

def test_reaper_fails_execution_state_task_with_event(runtime_env) -> None:
    """reaper 把执行态（validating）任务置 failed，并留 payload.reaper='wall_timeout' 的
    task_failed 事件。tamper：删 _reap_timed_out_task 的 fail_task_from_execution 调用 →
    状态不变 + 无事件 → 本测试红。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "m1_reap_ok"
    _drive_to(conn_factory, tid, ("queued", "validating"))

    JobRunner(object(), conn_factory)._reap_timed_out_task(tid, 0.05)

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
        events = repos.list_events(conn, tid)
    finally:
        conn.close()
    assert task["status"] == "failed"  # 真失败/红——绝不伪造 completed（假绿死罪）
    assert "墙钟上限" in (task.get("error_message") or "")
    reaped = [e for e in events if e["event_type"] == "task_failed"
              and e["payload"].get("reaper") == "wall_timeout"]
    assert len(reaped) == 1
    assert reaped[0]["payload"]["wall_s"] == 0.05


# ── 人签保护：reaper 拒绝覆盖 waiting_review/终态 ──────────────────────────

def test_reaper_refuses_waiting_review(runtime_env) -> None:
    """人是唯一签发者：任务已在 waiting_review（待人签）时 reaper 拒绝自动置 failed，
    只记 auto_fail_refused warning。tamper：把 fail_task_from_execution 白名单放开到含
    waiting_review → 状态被 reaper 改成 failed → 本测试红。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "m1_reap_review_guard"
    _drive_to(conn_factory, tid, ("queued", "validating", "running", "waiting_review"))

    JobRunner(object(), conn_factory)._reap_timed_out_task(tid, 0.05)

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
        events = repos.list_events(conn, tid)
    finally:
        conn.close()
    assert task["status"] == "waiting_review"  # 人签闸未被越过
    assert not any(e["event_type"] == "task_failed" for e in events)
    refused = [e for e in events if e["event_type"] == "warning"
               and e["payload"].get("action") == "auto_fail_refused"]
    assert len(refused) == 1
    assert refused[0]["level"] == "error"


def test_reaper_refuses_terminal_completed(runtime_env) -> None:
    """终态 completed 同样拒绝覆盖（reaper 绝不把已完成任务翻成 failed）。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "m1_reap_completed_guard"
    _drive_to(conn_factory, tid, ("queued", "validating", "running", "analyzing", "completed"))

    JobRunner(object(), conn_factory)._reap_timed_out_task(tid, 0.05)

    conn = conn_factory()
    try:
        assert repos.get_task(conn, tid)["status"] == "completed"
        assert not any(e["event_type"] == "task_failed" for e in repos.list_events(conn, tid))
    finally:
        conn.close()


# ── 集成主 witness：挂死任务被 reap + 队列继续 ────────────────────────────

def test_run_once_reaps_hung_task_and_queue_continues(runtime_env) -> None:
    """★M1 主 tamper 锚：把 run_once 改回同步直调 execute()（删 daemon 线程包裹 + join +
    is_alive() reaper 分支）→ 挂死任务永不置 failed 且 run_once 在同步 execute 内永久阻塞
    （队列冻结），看门狗解楔后同步版仍停在 validating → 'failed==1' 断言变红。

    极小墙钟经 JobRunner(wall_timeout_s=0.05) 显式注入（owner Q1 后墙钟按 runtime.tool_registry
    动态派生，测试用显式参数绕派生令 reaper 立即触发）；单串行 worker 下证'一条挂死不冻结整条队列'。"""
    conn_factory = runtime_env["conn_factory"]
    task_ids = ("m1_hang_a", "m1_hang_b")
    for tid in task_ids:
        _create_queued(conn_factory, tid)

    stub = _BlockingRuntime()
    runner = JobRunner(stub, conn_factory, wall_timeout_s=0.05)

    # 看门狗：即便 reaper 被拆（同步 execute 阻塞），3s 后解楔令断言得以运行（红），不无限挂起。
    watchdog = threading.Timer(3.0, stub.release.set)
    watchdog.daemon = True
    watchdog.start()
    try:
        assert runner.run_once() is True
        counts1 = _status_counts(conn_factory, task_ids)
        assert counts1.get("failed", 0) == 1  # 一条被 reap 置 failed
        assert counts1.get("queued", 0) == 1  # 另一条仍在排队（未被冻结/丢弃）

        assert runner.run_once() is True
        counts2 = _status_counts(conn_factory, task_ids)
        assert counts2.get("failed", 0) == 2  # 队列继续：第二条被认领并 reap
        assert counts2.get("queued", 0) == 0
    finally:
        watchdog.cancel()
        stub.release.set()  # 释放所有孤儿执行线程

    conn = conn_factory()
    try:
        for tid in task_ids:
            reaped = [e for e in repos.list_events(conn, tid)
                      if e["event_type"] == "task_failed"
                      and e["payload"].get("reaper") == "wall_timeout"]
            assert len(reaped) == 1
    finally:
        conn.close()


# ── 不误杀：正常快任务照常 completed，reaper 不触发 ────────────────────────

def test_normal_fast_task_completes_not_reaped(runtime_env) -> None:
    """默认派生墙钟（owner Q1 后 ≥ 硬地板 600s）下 hello_agent 毫秒级完成，join 先返回、
    reaper 不触发 → completed，且无 wall_timeout 事件。证 reaper 只咬真挂死、不误杀合法任务。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "m1_normal_fast"
    _create_queued(conn_factory, tid, name="小红")

    assert JobRunner(runtime_env["runtime"], conn_factory).run_once() is True

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
        events = repos.list_events(conn, tid)
    finally:
        conn.close()
    assert task["status"] == "completed"
    assert not any(e["payload"].get("reaper") == "wall_timeout" for e in events)


# ── fail-closed：reaper 内部异常 → worker 存活、状态不动 ──────────────────

def test_reaper_survives_internal_error(runtime_env, monkeypatch) -> None:
    """fail-closed：reaper 内 fail_task_from_execution 抛异常 → 只记日志、绝不上抛炸 worker；
    任务状态不被改动。tamper：删 _reap_timed_out_task 里包裹 fail_task 的 try/except →
    RuntimeError 逃逸 → 本测试红（pytest.raises 之外抛出）。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "m1_reaper_boom"
    _drive_to(conn_factory, tid, ("queued", "validating"))

    def _boom(*args, **kwargs):
        raise RuntimeError("DB 炸（测试注入）")

    monkeypatch.setattr(repos, "fail_task_from_execution", _boom)
    # 不抛即通过（worker 存活）。
    JobRunner(object(), conn_factory)._reap_timed_out_task(tid, 0.05)

    monkeypatch.undo()  # 还原后再读，避免 get_task 受影响
    conn = conn_factory()
    try:
        assert repos.get_task(conn, tid)["status"] == "validating"  # 状态未被改动
    finally:
        conn.close()


# ── 后置副作用：reaped 终态抗僵尸续写（owner 加验收 #5 / 完备性批判 #2）─────

def test_reaped_task_terminal_state_survives_zombie_writes(runtime_env) -> None:
    """reaper 置 failed 后，被放弃的僵尸执行线程可能续写。失败终态 + assert_transition
    （既有保护）挡住状态翻转：failed→running 非法、fail_task_from_execution 对非执行态返
    None、append_event 只追加不改状态。tamper：若 failed 不是终态 / set_task_status 不
    assert_transition，则僵尸 running 写入翻 failed→running → 本测试红。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "m1_zombie_guard"
    _drive_to(conn_factory, tid, ("queued", "validating"))
    JobRunner(object(), conn_factory)._reap_timed_out_task(tid, 0.05)

    conn = conn_factory()
    try:
        assert repos.get_task(conn, tid)["status"] == "failed"
        # 僵尸线程续跑 execute() 会尝试推进状态——被终态 + assert_transition 挡死。
        with pytest.raises(IllegalTransitionError):
            repos.set_task_status(conn, tid, "running")
        # 僵尸再次触发 runtime 兜底 fail_task_from_execution：非执行态 → None no-op。
        assert repos.fail_task_from_execution(conn, tid, "zombie 二次") is None
        # 追加事件是 append-only（允许），但终态不被翻转。
        repos.append_event(conn, task_id=tid, agent_id="hello_agent",
                           event_type="agent_log", level="info", message="zombie 续写")
        assert repos.get_task(conn, tid)["status"] == "failed"
    finally:
        conn.close()


# ── A1（owner Q1）宽墙钟派生：保证墙钟 ≥ 任何合法工具预算 ─────────────────────

def test_derive_wall_timeout_guarantees_ge_tool_budget_above_floor(monkeypatch) -> None:
    """★A1-② tamper 锚：墙钟派生结构性保证 ≥ max_tool_budget（工具预算+生成余量）。用一个
    超过硬地板的预算（700s）令 budget+margin 项 load-bearing（否则硬地板 600s 会遮蔽）。
    tamper：删 derive 里的 (budget + margin) 候选（只留 floor/env）→ derive(700)=600 < 700 →
    合法 700s 工具被 reaper 假杀 → 本断言红。"""
    from backend.app import config as cfg

    monkeypatch.delenv("FLAI_TASK_WALL_TIMEOUT_S", raising=False)
    importlib.reload(cfg)
    try:
        assert cfg.derive_task_wall_timeout_s(700.0) >= 700.0  # ≥ 工具预算（budget+margin 项承重）
        # cfd_solve_launch=360s 的真实预算：派生墙钟必 ≥ 360（含余量，绝不再被假杀）。
        assert cfg.derive_task_wall_timeout_s(360.0) >= 360.0
    finally:
        importlib.reload(cfg)


def test_derive_wall_timeout_covers_serial_tool_lifecycle_not_just_single_tool(monkeypatch) -> None:
    """★R2-P1-3 tamper 锚（Codex R2）：墙钟派生须覆盖单任务**串行多次**调工具的合法生命周期，非只
    单次最长工具预算。performance_disk_agent 逐行调 mock(10s)+parser+writer，1000 行批最坏远超单次
    工具预算——旧派生只算 1× 最长工具 → 合法批被 reaper 假杀。tamper：把 derive 里 tool_lifecycle 的
    × MAX_SEQUENTIAL_TOOL_CALLS_PER_TASK 改回 × 1（只算单次工具）→ derived < budget×N → 本断言红。"""
    from backend.app import config as cfg

    monkeypatch.delenv("FLAI_TASK_WALL_TIMEOUT_S", raising=False)
    importlib.reload(cfg)
    try:
        budget = 360.0
        n = cfg.MAX_SEQUENTIAL_TOOL_CALLS_PER_TASK
        assert n >= 32                                       # 默认覆盖已知最深 cfd 部署（360×32 ≥ 最坏）
        derived = cfg.derive_task_wall_timeout_s(budget)
        # 结构性保证：墙钟 ≥ 串行工具生命周期（单次预算 × 串行上界），非仅 1× budget。
        assert derived >= budget * n
        # 且 load-bearing（串行项 > 硬地板，证不是被地板遮蔽的假通过）。
        assert budget * n > cfg.TASK_WALL_TIMEOUT_FLOOR_S
        # 工具 + LLM 生命周期**相加**（既串行调工具又串行调模型的任务，加总是安全上界）。
        assert cfg.derive_task_wall_timeout_s(budget, cfg.DEFAULT_LLM_LIFECYCLE_BUDGET_S) >= budget * n + cfg.DEFAULT_LLM_LIFECYCLE_BUDGET_S
    finally:
        importlib.reload(cfg)


def test_derive_wall_timeout_env_override_cannot_lower_below_tool_budget(monkeypatch) -> None:
    """A1：env 覆盖只能上抬墙钟，绝不下压到工具预算以下（fail-safe，owner Q1）。env=60 < 工具
    预算 360 → 派生墙钟仍 ≥ 360（env 被 max() 兜底忽略）。tamper：把 derive 改成直接返回 env
    覆盖（无 max 兜底）→ 60 < 360 → 合法 cfd 被假杀 → 本断言红。"""
    from backend.app import config as cfg

    monkeypatch.setenv("FLAI_TASK_WALL_TIMEOUT_S", "60")
    importlib.reload(cfg)
    try:
        assert cfg.TASK_WALL_TIMEOUT_ENV_OVERRIDE == 60.0
        assert cfg.derive_task_wall_timeout_s(360.0) >= 360.0  # env=60 被兜底夹到 ≥ 工具预算
    finally:
        monkeypatch.delenv("FLAI_TASK_WALL_TIMEOUT_S", raising=False)
        importlib.reload(cfg)


def test_jobrunner_derives_wall_from_tool_registry_ge_cfd_budget(runtime_env) -> None:
    """集成：JobRunner 启动处据 runtime.tool_registry 派生墙钟，覆盖真实 registry（含
    cfd_solve_launch=360s）→ 派生墙钟 ≥ 360（+余量，实为 ≥660）。证派生真读了工具预算、不是
    静态旧默认 180s（旧默认 < 360 会假杀 cfd）。tamper：派生忽略 tool_registry 回退低值 → 红。"""
    conn_factory = runtime_env["conn_factory"]
    runner = JobRunner(runtime_env["runtime"], conn_factory)
    assert runner._wall_timeout_s >= 360.0  # ≥ cfd_solve_launch 工具预算（旧静态 180 会红）
    # 并证 ≥ budget + 生成余量（真读了 registry 最大预算 360 而非仅硬地板）。
    from backend.app import config as cfg
    assert runner._wall_timeout_s >= 360.0 + cfg.TASK_WALL_TIMEOUT_GENERATION_MARGIN_S


# ── A2（C1-P1-2）僵尸线程产物发布守卫：reap 后线程绝不污染已 failed 任务 ─────

def test_zombie_thread_does_not_publish_after_reaper_failed(runtime_env, monkeypatch) -> None:
    """★A2 tamper 锚（Codex R1-P1-a → R2-P1 原子发布）：模拟「reaper 墙钟超时把执行中任务置 failed，
    被放弃的僵尸执行线程仍跑到 workflow 成功尾部」。产物发布经 repos.finalize_publish 在同一
    BEGIN IMMEDIATE 内 re-check 执行态 + attach 产物 + 翻终态：任务已 failed（非执行态）→ 返 None →
    放弃整个发布块（已注册产物成 orphan 不 attach、不写 sim_run_ref、不记 success 样本），任务保持
    failed。tamper：把 runtime._execute 的 `finalize_publish(...) is None → return failed` 换成无条件
    裸 set_task_outputs/record_sample（即回退非原子发布）→ 僵尸线程给已 failed 任务写 output_file_ids
    （脏发布）→ 本断言 output_file_ids==[] / 无 success 样本变红。"""
    from backend.app.runtime import runtime as runtime_mod

    conn_factory = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    tid = "m1_zombie_publish_guard"
    _create_queued(conn_factory, tid)
    # 认领到 validating（execute 的合法入口态）。
    conn = conn_factory()
    try:
        repos.claim_next_queued(conn)  # queued → validating
    finally:
        conn.close()

    def _fake_run(context):
        # 模拟 reaper 在 workflow 执行中途把任务从执行态置 failed（另开连接，与 execute 的连接不同）。
        c = conn_factory()
        try:
            repos.fail_task_from_execution(c, context["task"]["id"], "reaper 墙钟超时（测试注入）")
        finally:
            c.close()
        # 产出一个文件：若发布块被执行，_register_outputs 会把它注册进 output_file_ids（脏）。
        out = Path(context["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "zombie.txt").write_text("dirty", encoding="utf-8")
        return {"status": "success", "outputs": [{"sim_run_ref": "cfd@20250101-000000"}]}

    monkeypatch.setattr(
        runtime_mod, "_load_workflow_module",
        lambda *a, **k: types.SimpleNamespace(run=_fake_run),
    )

    result = runtime.execute(tid)

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
        samples = repos.list_samples(conn, tid)
    finally:
        conn.close()
    assert result["status"] == "failed"                     # 守卫在→返回 failed（不假绿）
    assert task["status"] == "failed"                        # 任务保持 failed（未被翻回成功态）
    assert task["output_file_ids"] == []                     # 产物未注册（脏发布被挡）
    assert "sim_run_ref" not in (task.get("metadata") or {})  # sim_run_ref 未回填
    assert not any(s.get("validation_status") == "success" for s in samples)  # 无 success 样本


# ── R1-P1-b（Codex R1）墙钟派生覆盖串行 LLM 生命周期（8 问 knowledge_qa 不假杀）─────

def test_derive_wall_timeout_covers_serial_llm_lifecycle(monkeypatch) -> None:
    """★R1-P1-b tamper 锚（Codex R1）：墙钟派生须覆盖单任务**串行多次**模型调用的合法生命周期，
    非只单次最长工具。knowledge_qa 按 input maxItems 逐问 chat，8 问最坏 8×(LLM_TIMEOUT×尝试数)。
    tamper：把 derive 的 max_llm_lifecycle 项去掉（回退只算工具预算+地板）→ derive(0, lifecycle)
    退回地板 600 < 8 问真实生命周期 1920 → 8 问合法任务被 reaper 假杀 → 本断言红。"""
    from backend.app import config as cfg

    monkeypatch.delenv("FLAI_TASK_WALL_TIMEOUT_S", raising=False)
    importlib.reload(cfg)
    try:
        # 8 问 agent 的最坏合法 LLM 生命周期（真实上界，非派生假设值）。
        worst_case_8q = 8 * cfg.LLM_TIMEOUT_S * cfg.LLM_MAX_ATTEMPTS_PER_CALL
        derived = cfg.derive_task_wall_timeout_s(0.0, cfg.DEFAULT_LLM_LIFECYCLE_BUDGET_S)
        assert derived >= worst_case_8q                     # 覆盖 8 问最坏生命周期（不假杀）
        assert derived > cfg.TASK_WALL_TIMEOUT_FLOOR_S       # lifecycle 项 load-bearing（>地板）
        assert cfg.MAX_SEQUENTIAL_LLM_CALLS_PER_TASK >= 8    # 默认覆盖现役最深 agent（8）
        # 工具 + LLM 生命周期**相加**（一个任务可能既编排工具又串行调模型，加总是安全上界）。
        assert cfg.derive_task_wall_timeout_s(360.0, cfg.DEFAULT_LLM_LIFECYCLE_BUDGET_S) >= 360.0 + worst_case_8q
    finally:
        importlib.reload(cfg)


def test_jobrunner_wall_covers_llm_lifecycle_not_just_tool_budget(runtime_env) -> None:
    """集成：JobRunner 派生墙钟 ≥ 工具预算(360) + 8 问 LLM 生命周期(1920)——证真读了 LLM 生命周期
    项而非仅工具预算。tamper：_derive_wall_timeout_for_runtime 不传 lifecycle → 墙钟 ≈660 < 2280 → 红。"""
    from backend.app import config as cfg
    runner = JobRunner(runtime_env["runtime"], runtime_env["conn_factory"])
    worst_case_8q = 8 * cfg.LLM_TIMEOUT_S * cfg.LLM_MAX_ATTEMPTS_PER_CALL
    assert runner._wall_timeout_s >= 360.0 + worst_case_8q  # 工具预算 + 8 问生命周期都覆盖


# ── R2-P1（Codex R2）finalize_publish 原子发布：attach 产物 + 记样本 + 翻终态合一事务 ─────

def test_finalize_publish_running_to_waiting_review_attaches_outputs(runtime_env) -> None:
    """认领 running→waiting_review（单跳，人签态）+ **同事务 attach 产物清单**（R1 的裸 set_task_outputs
    并入原子事务，R2-P1）→ 返回 status=waiting_review 且 output_file_ids 已落。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "fp_wr"
    _drive_to(conn_factory, tid, ("queued", "validating", "running"))
    conn = conn_factory()
    try:
        claimed = repos.finalize_publish(conn, tid, "waiting_review", output_file_ids=["f_a", "f_b"])
        assert claimed is not None
        assert claimed["status"] == "waiting_review"
        assert claimed["output_file_ids"] == ["f_a", "f_b"]  # attach 与 flip 同事务原子
    finally:
        conn.close()


def test_finalize_publish_completed_passes_through_analyzing(runtime_env) -> None:
    """认领 running→completed：同事务内经 analyzing（docs/05 §2 running 不得跳过 analyzing）到
    completed，finished_at 落、产物已 attach。tamper：把 completed 分支改成 running→completed 直翻
    （跳 analyzing）→ assert_transition 炸 IllegalTransitionError（审计轨保护），本用例 raise。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "fp_done"
    _drive_to(conn_factory, tid, ("queued", "validating", "running"))
    conn = conn_factory()
    try:
        claimed = repos.finalize_publish(conn, tid, "completed", output_file_ids=["f_x"])
        assert claimed is not None
        assert claimed["status"] == "completed"
        assert claimed["finished_at"] is not None
        assert claimed["output_file_ids"] == ["f_x"]
    finally:
        conn.close()


def test_finalize_publish_records_sample_atomically_with_flip(runtime_env) -> None:
    """★R2-P1 核心：sample_spec 非 None → success 样本在**同一 BEGIN IMMEDIATE**内与 attach/flip 同
    落（R1 曾在翻态后事务外裸 record_sample，翻态成功但样本写抛异常=样本缺失且任务已终态）。本用例
    证认领成功时样本随事务一并落库。tamper：把 finalize_publish 里 record_sample 移出事务（翻态后再
    调）→ 原子性破，但本正向断言仍绿；负向由 reaper-won 用例（样本绝不落）把关。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "fp_sample"
    _drive_to(conn_factory, tid, ("queued", "validating", "running"))
    conn = conn_factory()
    try:
        spec = {
            "task_id": tid, "agent_id": "a", "agent_version": "v1",
            "input_json": {"q": "x"}, "output_json": {"ok": True},
            "validation_status": "success", "classification": "internal",
        }
        claimed = repos.finalize_publish(conn, tid, "completed", output_file_ids=["f1"], sample_spec=spec)
        assert claimed is not None and claimed["status"] == "completed"
        samples = repos.list_samples(conn, tid)
        assert len(samples) == 1
        assert samples[0]["validation_status"] == "success"
    finally:
        conn.close()


def test_finalize_publish_returns_none_when_reaper_already_failed_no_attach_no_sample(runtime_env) -> None:
    """★R2-P1 原子性地基：任务已被 reaper 置 failed（非执行态）→ 认领返 None（放弃整个发布）。锁内
    re-check 执行态失败即整体 abort：产物**不 attach**、样本**不落**、任务保持 failed。tamper：把
    finalize 的执行态白名单检查删掉（无条件翻 target）→ 已 failed 任务被认领成 completed（un-fail）+
    脏 attach + 脏样本 → 本断言 is None / output_file_ids==[] / 无样本 全红。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "fp_failed"
    _drive_to(conn_factory, tid, ("queued", "validating", "running"))
    conn = conn_factory()
    try:
        assert repos.fail_task_from_execution(conn, tid, "reaper 抢先") is not None  # running→failed
        spec = {
            "task_id": tid, "agent_id": "a", "agent_version": "v1",
            "input_json": {"q": "x"}, "output_json": {"ok": True},
            "validation_status": "success", "classification": "internal",
        }
        assert repos.finalize_publish(conn, tid, "completed", output_file_ids=["dirty"], sample_spec=spec) is None
        task = repos.get_task(conn, tid)
        assert task["status"] == "failed"          # 保持 failed（未 un-fail）
        assert task["output_file_ids"] == []       # 产物未 attach（脏发布被挡）
        assert repos.list_samples(conn, tid) == []  # 样本未落（原子 abort）
    finally:
        conn.close()


def test_finalize_publish_rejects_unknown_target(runtime_env) -> None:
    """target 白名单仅 {waiting_review, completed}——传其他终态（如 failed/cancelled）raise
    ValueError（防误用把发布闸当通用状态机入口）。"""
    conn_factory = runtime_env["conn_factory"]
    tid = "fp_bad_target"
    _drive_to(conn_factory, tid, ("queued", "validating", "running"))
    conn = conn_factory()
    try:
        with pytest.raises(ValueError):
            repos.finalize_publish(conn, tid, "failed", output_file_ids=[])
    finally:
        conn.close()


def test_register_outputs_raise_leaves_task_recoverable_not_stuck_terminal(runtime_env, monkeypatch) -> None:
    """★R2-P1 tamper 锚（Codex R2）：发布期物理产物注册若抛异常，任务须留在**执行态**（reaper/
    _mark_failed 可回收），绝不卡死「终态但产物缺失」。本次改「物理 I/O 前置」：_register_outputs 在
    执行态做（抛则任务未翻终态），finalize_publish 仅在注册成功后原子 attach+flip。tamper：把发布块
    改回 flip-first（先 finalize 翻终态、再 register）→ register 抛时任务已 completed/waiting_review
    但无产物 → 本断言 status not in 终态 红（实为终态）。"""
    from backend.app.runtime import runtime as runtime_mod

    conn_factory = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    tid = "r2p1_register_raise"
    _create_queued(conn_factory, tid)
    conn = conn_factory()
    try:
        repos.claim_next_queued(conn)  # queued → validating
    finally:
        conn.close()

    def _fake_run(context):
        out = Path(context["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "ok.txt").write_text("ok", encoding="utf-8")
        return {"status": "success", "outputs": []}

    monkeypatch.setattr(
        runtime_mod, "_load_workflow_module",
        lambda *a, **k: types.SimpleNamespace(run=_fake_run),
    )

    def _boom(*a, **k):
        raise OSError("disk full (注入：模拟产物注册磁盘 I/O 失败)")

    monkeypatch.setattr(runtime, "_register_outputs", _boom)

    with contextlib.suppress(Exception):
        runtime.execute(tid)  # register 抛异常传播或被 execute 吞成 failed，两者均可

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
    finally:
        conn.close()
    # 核心不变量：注册抛异常时任务**未翻终态成功态**（留执行态可回收 / 或 failed），绝不 completed/
    # waiting_review（那才是「终态但产物缺失」的卡死，本次修的正是它）。
    assert task["status"] not in ("completed", "waiting_review")
    assert task["output_file_ids"] == []


# ── R1-P2（Codex R1）执行线程 start() 失败：已认领任务就地置 failed 不搁浅 ─────────

def test_thread_startup_failure_fails_claimed_task_not_stranded(runtime_env, monkeypatch) -> None:
    """★R1-P2 tamper 锚：执行线程 start() 失败（系统拒绝新线程/资源耗尽）时，已 claim 到 validating
    的任务必被就地置 failed（不永久搁浅）。tamper：拆掉 run_once 的 thread.start try/except（或
    _fail_thread_startup）→ start 抛后任务卡 validating（无执行线程、无 reaper 触达）→ 本断言
    status=='failed' 红（实为 validating）。"""
    conn_factory = runtime_env["conn_factory"]
    runner = JobRunner(runtime_env["runtime"], conn_factory)
    tid = "m1_start_fail"
    _create_queued(conn_factory, tid)

    def _boom_start(self):  # 模拟系统拒绝新线程
        raise RuntimeError("can't start new thread (test injection)")
    monkeypatch.setattr(threading.Thread, "start", _boom_start)

    handled = runner.run_once()
    assert handled is True  # 认领了一条即返 True（即便启动失败，worker 继续认领下一条）

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
    finally:
        conn.close()
    assert task["status"] == "failed"                        # ★就地置 failed，不搁浅在 validating
    assert "线程无法启动" in (task.get("error_message") or "")


def test_execute_raising_baseexception_marks_failed_not_stranded(runtime_env, monkeypatch) -> None:
    """★R2-P1-2 tamper 锚（Codex R2）：execute() 抛 **BaseException**（SystemExit/KeyboardInterrupt，
    非 Exception 子类）时，任务须被就地置 failed 并留下**具体**异常痕迹，绝不搁浅执行态被新鲜心跳
    掩盖。_execute_in_thread 用 `except BaseException` 捕获 → box["exc"] → _mark_failed_best_effort
    以「SystemExit: ...」为 error_message。tamper：把 `except BaseException` 改回 `except Exception`
    → SystemExit 不是 Exception 子类 → 逃出 try、box 空、退回 `elif "done" not in box` 兜底网记**通用**
    message（不含 SystemExit）→ 本断言 error_message 含 'SystemExit' 红（防御从「具体归因」退化为
    「泛化兜底」即被逮）。注：任务仍会 failed（兜底网在），故 witness 落在 error_message 归因精度上。"""
    conn_factory = runtime_env["conn_factory"]
    runner = JobRunner(runtime_env["runtime"], conn_factory)
    tid = "m1_execute_baseexc"
    _create_queued(conn_factory, tid)

    def _boom_execute(task_id):  # execute 抛 BaseException（非 Exception）
        raise SystemExit("worker 执行线程被 BaseException 打断（test injection）")
    monkeypatch.setattr(runner._runtime, "execute", _boom_execute)

    handled = runner.run_once()
    assert handled is True  # 认领了一条即返 True（execute 抛 BaseException 亦不炸 worker 主循环）

    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
    finally:
        conn.close()
    assert task["status"] == "failed"                            # ★置 failed，不搁浅执行态
    assert "SystemExit" in (task.get("error_message") or "")      # ★具体归因（tamper 退化为通用即红）


def test_reap_transient_conn_failure_pending_retry_not_stranded(runtime_env) -> None:
    """★R3-P1 tamper 锚（Codex R3 verbatim）：墙钟 reap 时 conn_factory 抛**瞬时**存储故障（SQLite
    打开/锁超时）——任务已离 queued，旧行为异常逃逸 run_forever 只记日志、再无人触达=永久搁浅执行态
    （心跳仍新鲜掩盖）。修后 reap 失败登记 pending 重试账本，下一轮 run_once 先重放终态化 → 任务最终
    failed。tamper：删 _reap_timed_out_task 的 `self._pending_fails[task_id] = ...` 登记（回退只记日志
    即丢）→ 重放无从发生、任务卡 running → 本断言 failed 红。"""
    conn_factory = runtime_env["conn_factory"]
    runner = JobRunner(runtime_env["runtime"], conn_factory)
    tid = "r3_reap_transient"
    _drive_to(conn_factory, tid, ("queued", "validating", "running"))

    # 第一次 reap：注入「conn 打开即炸」的瞬时故障 → 置 failed 未达成，必须登记 pending。
    def _boom_factory():
        raise sqlite3.OperationalError("unable to open database file (test injection)")
    runner._conn_factory = _boom_factory
    runner._reap_timed_out_task(tid, 1.0)          # 不上抛（best-effort 契约）
    assert tid in runner._pending_fails, "瞬时故障必须登记 pending 重试（否则任务永久搁浅执行态）"

    conn = conn_factory()
    try:
        assert repos.get_task(conn, tid)["status"] == "running"  # 此刻仍搁浅（重放尚未发生）
    finally:
        conn.close()

    # 存储恢复：run_once 开头先重放 pending → 任务补置 failed、出账。
    runner._conn_factory = conn_factory
    runner.run_once()
    conn = conn_factory()
    try:
        task = repos.get_task(conn, tid)
    finally:
        conn.close()
    assert task["status"] == "failed", "存储恢复后 pending 重放必须补上终态化（不搁浅）"
    assert "超墙钟" in (task.get("error_message") or "")          # 归因仍是墙钟超时（同一收口动作重放）
    assert tid not in runner._pending_fails, "重放成功必须出账（不无限重试）"
