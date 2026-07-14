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
