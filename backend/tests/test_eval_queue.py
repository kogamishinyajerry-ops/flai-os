"""T1 异步评测队列 + 配额（可信结论内核硬化，GH #2）。

存储层原子原语 `claim_next_queued_eval_run(quota)` 是配额门的确定性核：
「统计 running + 挑最旧 queued + CAS 置 running」在单个 BEGIN IMMEDIATE 写锁内
完成，配额上限内放行、超限返回 None（排队不拒）。这条被 tamper（拆掉配额判定）
必红——即本文件末尾的变异咬合。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


@pytest.fixture()
def conn_factory(tmp_path: Path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)

    def factory():
        return get_conn(db_path)

    return factory


def _seed_queued(conn_factory, agent_id: str, n: int) -> list[str]:
    """种 n 条 queued eval_run，返回 run_id 列表（enqueue 顺序）。"""
    ids: list[str] = []
    conn = conn_factory()
    try:
        for i in range(n):
            run_id = f"eval_{agent_id}_{i:03d}"
            repos.create_eval_run(
                conn,
                run_id=run_id,
                agent_id=agent_id,
                agent_version="0.1.0",
                triggered_by="tester",
                status="queued",
            )
            ids.append(run_id)
    finally:
        conn.close()
    return ids


def test_create_eval_run_defaults_to_running_but_accepts_queued(conn_factory) -> None:
    conn = conn_factory()
    try:
        default_run = repos.create_eval_run(
            conn, run_id="eval_default", agent_id="a", agent_version="0.1.0",
            triggered_by="t",
        )
        queued_run = repos.create_eval_run(
            conn, run_id="eval_queued", agent_id="a", agent_version="0.1.0",
            triggered_by="t", status="queued",
        )
    finally:
        conn.close()
    assert default_run["status"] == "running"  # 既有同步路径向后兼容
    assert queued_run["status"] == "queued"


def test_claim_respects_quota_and_queues_excess(conn_factory) -> None:
    """配额=2，种 3 条 queued：前两次 claim 成功置 running，第三次因配额满返回
    None（排队不拒）；finish 掉一条后第三次 claim 又能成功——排队的最终执行。"""
    _seed_queued(conn_factory, "agent_x", 3)
    quota = 2

    claimed = []
    conn = conn_factory()
    try:
        for _ in range(3):
            run = repos.claim_next_queued_eval_run(conn, quota=quota)
            claimed.append(run)
    finally:
        conn.close()

    assert claimed[0] is not None and claimed[0]["status"] == "running"
    assert claimed[1] is not None and claimed[1]["status"] == "running"
    assert claimed[2] is None, "配额满时第三条必须排队（返回 None），绝不第三个 running"

    # 腾一个 running 名额 → 排队那条可被认领执行
    conn = conn_factory()
    try:
        repos.finish_eval_run(
            conn, claimed[0]["id"], status="completed", total=0, passed=0,
            failed=0, skipped=0, case_results=[], draft_cases=[], eval_cases_digest=None,
        )
        third = repos.claim_next_queued_eval_run(conn, quota=quota)
        running_now = conn.execute(
            "SELECT COUNT(*) FROM eval_runs WHERE status='running'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert third is not None and third["status"] == "running", "腾出名额后排队的必执行"
    assert running_now == quota, "running 数恒不超配额"


def test_claim_picks_oldest_queued_first(conn_factory) -> None:
    ids = _seed_queued(conn_factory, "agent_y", 3)
    conn = conn_factory()
    try:
        first = repos.claim_next_queued_eval_run(conn, quota=10)
    finally:
        conn.close()
    assert first is not None and first["id"] == ids[0], "FIFO：最旧 queued 先被认领"


def test_claim_returns_none_when_no_queued(conn_factory) -> None:
    conn = conn_factory()
    try:
        assert repos.claim_next_queued_eval_run(conn, quota=5) is None
    finally:
        conn.close()


def test_claim_never_exceeds_quota_under_repeated_calls(conn_factory) -> None:
    """配额=1，种 5 条：反复 claim 任意次，running 恒 ≤ 1（配额门是硬上限）。"""
    _seed_queued(conn_factory, "agent_z", 5)
    conn = conn_factory()
    try:
        for _ in range(5):
            repos.claim_next_queued_eval_run(conn, quota=1)
        running = conn.execute(
            "SELECT COUNT(*) FROM eval_runs WHERE status='running'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert running == 1, "配额=1 时 running 恒为 1，绝不因反复 claim 溢出"


# ── Codex R1 审 P1 修复回归护栏 ───────────────────────────────────────────
from backend.app.governance import eval_runner  # noqa: E402
from backend.app.governance.eval_worker import EvalRunner  # noqa: E402


def test_eval_run_once_does_not_claim_when_fault_arrives_after_outer_precheck(
    conn_factory,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外层预查后才建立的 fault 也不得把 queued eval run 改成 running。"""

    _seed_queued(conn_factory, "fault_race", 1)
    rival = conn_factory()
    outer_precheck_seen = False
    queue_probe_seen = False
    begin_interposed = False
    fault_inserted = False
    callback_errors: list[Exception] = []

    def trace(statement: str) -> None:
        nonlocal outer_precheck_seen, queue_probe_seen
        nonlocal begin_interposed, fault_inserted
        normalized = " ".join(statement.upper().split())
        if normalized.startswith(
            "SELECT * FROM WORKER_HEARTBEATS WHERE WORKER_ID ="
        ):
            outer_precheck_seen = True
        elif normalized.startswith(
            "SELECT 1 FROM EVAL_RUNS WHERE STATUS = 'QUEUED' LIMIT 1"
        ):
            queue_probe_seen = True
        elif (
            normalized.startswith("BEGIN IMMEDIATE")
            and outer_precheck_seen
            and queue_probe_seen
            and not begin_interposed
        ):
            begin_interposed = True
            try:
                fault_inserted = repos.record_promotion_attestation_fault(
                    rival,
                    detail='{"reason":"test-eval-claim-race"}',
                )
            except Exception as exc:  # trace callback 异常会被 sqlite 吞掉
                callback_errors.append(exc)

    def racing_conn_factory():
        racing_conn = conn_factory()
        racing_conn.set_trace_callback(trace)
        return racing_conn

    # 旧实现会认领后创建执行线程；禁用线程启动只为冻结状态观察点，不介入
    # storage claim 裁决。修复后在 claim 内即返回，根本不会走到线程创建。
    import threading

    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    worker = EvalRunner(
        agent_registry=None,
        runtime=None,
        conn_factory=racing_conn_factory,
        uploads_dir=tmp_path,
        task_runs_dir=tmp_path,
        quota=1,
    )
    try:
        did_work = worker.run_once()
    finally:
        rival.close()

    conn = conn_factory()
    try:
        queued_after = repos.get_eval_run(conn, "eval_fault_race_000")
    finally:
        conn.close()
    assert outer_precheck_seen is True
    assert queue_probe_seen is True
    assert begin_interposed is True
    assert fault_inserted is True
    assert callback_errors == []
    assert did_work is False
    assert queued_after is not None
    assert queued_after["status"] == "queued"


def test_recover_interrupted_frees_quota(conn_factory, tmp_path) -> None:
    """P1（Codex R1）：上次 worker 崩溃遗留的 running 行是无执行线程的僵尸，永久占配额
    （quota=1 立即锁死队列）。recover_interrupted() 收口 error 释放名额。"""
    conn = conn_factory()
    try:
        repos.create_eval_run(conn, run_id="eval_zombie", agent_id="a",
                              agent_version="0.1.0", triggered_by="t", status="running")
        repos.create_eval_run(conn, run_id="eval_waiting", agent_id="a",
                              agent_version="0.1.0", triggered_by="t", status="queued")
    finally:
        conn.close()

    worker = EvalRunner(agent_registry=None, runtime=None, conn_factory=conn_factory,
                        uploads_dir=tmp_path, task_runs_dir=tmp_path, quota=1)

    # 恢复前：quota=1 下僵尸占满名额，queued 认领不到（配额门挡回 None）
    conn = conn_factory()
    try:
        assert repos.claim_next_queued_eval_run(conn, quota=1) is None, "僵尸未清时队列锁死"
    finally:
        conn.close()

    assert worker.recover_interrupted() == 1

    conn = conn_factory()
    try:
        zombie = repos.get_eval_run(conn, "eval_zombie")
        claimed = repos.claim_next_queued_eval_run(conn, quota=1)
    finally:
        conn.close()
    assert zombie["status"] == "error", "崩溃遗留 running 必被收口 error"
    assert claimed is not None and claimed["id"] == "eval_waiting", "配额释放后 queued 可被认领"


def test_execute_terminalizes_on_version_skew(conn_factory, tmp_path) -> None:
    """P1（Codex R1）：入队登记版本 ≠ worker 执行时活版本（分离部署只重启一侧）→
    fail-closed 收口 error，绝不用错版本认证评测，且短路在读包之前。"""
    conn = conn_factory()
    try:
        repos.create_eval_run(conn, run_id="eval_skew", agent_id="a",
                              agent_version="9.9.9", triggered_by="t", status="running")
    finally:
        conn.close()

    class _SkewRegistry:
        def get(self, agent_id):
            return {"id": agent_id, "version": "0.1.0", "workflow": {}}  # 活 0.1.0 ≠ 入队 9.9.9

        def package_dir(self, agent_id):
            # 短语刻意不含 skew 断言的关键词——否则 skew 门被 tamper 掉时本测经此
            # 异常路径仍误绿（假绿）。禁掉 skew 门后本测必红。
            raise AssertionError("不应读包目录")

    result = eval_runner.execute_eval_run(
        run_id="eval_skew", conn_factory=conn_factory, agent_registry=_SkewRegistry(),
        runtime=None, uploads_dir=tmp_path, task_runs_dir=tmp_path,
    )
    assert result["status"] == "error"
    assert "入队登记" in result["case_results"][0]["detail"], "必须走版本漂移收口而非读包异常"


def test_terminalize_zombie_finishes_running_row(conn_factory, tmp_path) -> None:
    """P1（Codex R1）：_execute_claimed 的兜底——仍 running 的行被收口 error（配额释放）。"""
    conn = conn_factory()
    try:
        repos.create_eval_run(conn, run_id="eval_z", agent_id="a", agent_version="0.1.0",
                              triggered_by="t", status="running")
    finally:
        conn.close()
    worker = EvalRunner(agent_registry=None, runtime=None, conn_factory=conn_factory,
                        uploads_dir=tmp_path, task_runs_dir=tmp_path, quota=1)
    worker._terminalize_zombie("eval_z")
    conn = conn_factory()
    try:
        assert repos.get_eval_run(conn, "eval_z")["status"] == "error"
    finally:
        conn.close()


def test_worker_path_never_leaves_zombie_on_prelude_exception(conn_factory, tmp_path) -> None:
    """P1（Codex R1）：prelude（package_dir 等）抛异常时 worker 执行路径绝不留 running
    僵尸——execute 自收口 + _execute_claimed 兜底，终态必 error（配额不泄）。"""
    conn = conn_factory()
    try:
        repos.create_eval_run(conn, run_id="eval_prelude", agent_id="a",
                              agent_version="0.1.0", triggered_by="t", status="running")
    finally:
        conn.close()

    class _BoomRegistry:
        def get(self, agent_id):
            return {"id": agent_id, "version": "0.1.0", "workflow": {}}  # 版本匹配，过 skew 门

        def package_dir(self, agent_id):
            raise RuntimeError("模拟包目录解析故障")

    worker = EvalRunner(agent_registry=_BoomRegistry(), runtime=None, conn_factory=conn_factory,
                        uploads_dir=tmp_path, task_runs_dir=tmp_path, quota=1)
    worker._execute_claimed("eval_prelude")  # 真实 worker 认领后的执行入口

    conn = conn_factory()
    try:
        assert repos.get_eval_run(conn, "eval_prelude")["status"] == "error", "prelude 异常绝不留僵尸 running"
    finally:
        conn.close()


def test_base_exception_in_execution_still_terminalizes(conn_factory, tmp_path) -> None:
    """P1（Codex R1 复审）：workflow 抛 BaseException（SystemExit 等 `except Exception` 拦不住
    的）时，执行线程边界的 finally 仍收口 error，绝不留 running 僵尸泄配额。"""
    conn = conn_factory()
    try:
        repos.create_eval_run(conn, run_id="eval_be", agent_id="a", agent_version="0.1.0",
                              triggered_by="t", status="running")
    finally:
        conn.close()

    class _BaseBoomRegistry:
        def get(self, agent_id):
            return {"id": agent_id, "version": "0.1.0", "workflow": {}}

        def package_dir(self, agent_id):
            raise SystemExit("模拟 BaseException 中断")

    worker = EvalRunner(agent_registry=_BaseBoomRegistry(), runtime=None, conn_factory=conn_factory,
                        uploads_dir=tmp_path, task_runs_dir=tmp_path, quota=1)
    with pytest.raises(SystemExit):  # 收口后 BaseException 继续透传（daemon 线程内只杀本线程）
        worker._execute_claimed("eval_be")

    conn = conn_factory()
    try:
        assert repos.get_eval_run(conn, "eval_be")["status"] == "error", "BaseException 也不留僵尸"
    finally:
        conn.close()


def test_thread_start_failure_terminalizes_and_frees_quota(conn_factory, tmp_path, monkeypatch) -> None:
    """P2（Codex R1 复审）：claim 已置 running 后 thread.start() 失败（线程耗尽/关停）→ 收口
    error 释放配额，绝不留认领态却无执行者的僵尸（run_forever 会吞异常继续轮询）。"""
    _seed_queued(conn_factory, "a", 1)
    worker = EvalRunner(agent_registry=None, runtime=None, conn_factory=conn_factory,
                        uploads_dir=tmp_path, task_runs_dir=tmp_path, quota=1)

    import threading as _threading

    def _boom(self):
        raise RuntimeError("模拟线程耗尽")

    monkeypatch.setattr(_threading.Thread, "start", _boom)
    claimed = worker.run_once()
    monkeypatch.undo()  # 立即恢复，避免影响后续任何线程创建

    assert claimed is False, "启动失败时 run_once 返回 False（未认领到可执行的）"
    conn = conn_factory()
    try:
        statuses = [r["status"] for r in conn.execute("SELECT status FROM eval_runs").fetchall()]
    finally:
        conn.close()
    assert statuses == ["error"], f"启动失败的认领行必收口 error（配额释放），实际 {statuses}"


def test_reap_retries_terminalization_after_transient_db_failure(conn_factory, tmp_path) -> None:
    """P1（Codex R2 复审）：finally 兜底收口遇瞬时 DB 故障失败后，_reap 绝不遗忘僵尸——死
    线程的 running 行保留在 _active（配额不误放），DB 恢复后下个 _reap 收口 error 并摘除。"""
    import sqlite3
    import threading as _threading

    conn = conn_factory()
    try:
        repos.create_eval_run(conn, run_id="eval_orphan", agent_id="a", agent_version="0.1.0",
                              triggered_by="t", status="running")
    finally:
        conn.close()

    worker = EvalRunner(agent_registry=None, runtime=None, conn_factory=conn_factory,
                        uploads_dir=tmp_path, task_runs_dir=tmp_path, quota=1)
    orig_cf = worker._conn_factory
    dead = _threading.Thread(target=lambda: None)  # 立即结束=已死线程，模拟执行线程已退出
    dead.start()
    dead.join()
    worker._active["eval_orphan"] = dead

    # 首个 reap：conn_factory 瞬时故障 → 收口失败 → 不摘除、行仍 running、配额不误放
    def _broken():
        raise sqlite3.OperationalError("模拟瞬时 DB 故障")

    worker._conn_factory = _broken
    worker._reap()
    assert "eval_orphan" in worker._active, "收口失败时绝不遗忘僵尸（保留 _active 重试）"
    conn = conn_factory()
    try:
        assert repos.get_eval_run(conn, "eval_orphan")["status"] == "running", "收口失败不误标"
    finally:
        conn.close()

    # DB 恢复 → 下个 reap 收口 error 并摘除，配额释放
    worker._conn_factory = orig_cf
    worker._reap()
    assert "eval_orphan" not in worker._active, "恢复后摘除 _active"
    conn = conn_factory()
    try:
        assert repos.get_eval_run(conn, "eval_orphan")["status"] == "error", "恢复后收口 error"
    finally:
        conn.close()
