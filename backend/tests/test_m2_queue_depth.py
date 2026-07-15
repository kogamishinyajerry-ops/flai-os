"""Gate2-T1-M2（worker 可观测完整版 · M1↔M2† 协调修）单测 + tamper 见证。

分两层：
- repos.get_queue_depth 纯只读查询：计数口径（origin='user'）、最老龄期、fail-closed
  （naive/畸形 created_at → None 龄期 + malformed=True）。
- /api/readyz 就绪裁决：心跳新鲜为主锚（M2† 不回归）+ 最老 queued 龄期超阈 → degraded
  （owner Q2 协调裁定）；队列计数纯信息位不进 gate（深队列不误翻红、空队列不冒充活）。

放在**独立文件**（非 test_p0_admission_gate.py）：后者的 N2 拒载测试正被 T3「N2 放宽」
改动，避免同文件纠缠。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app import config
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def conn(tmp_path):
    """裸 tmp DB 连接——get_queue_depth 是纯只读查询，无需装 app/runtime。"""
    db_path = tmp_path / "queue.db"
    init_db(db_path)
    c = get_conn(db_path)
    try:
        yield c
    finally:
        c.close()


def _seed_task(c, task_id: str, statuses: tuple[str, ...], *, origin: str = "user") -> None:
    repos.create_task(
        c, task_id=task_id, agent_id="hello_agent", agent_version="0.1.0",
        name="queue depth 测试", created_by="tester", inputs={"name": "q"},
        input_file_ids=[], metadata={}, origin=origin,
    )
    for status in statuses:
        repos.set_task_status(c, task_id, status)


# ── repos.get_queue_depth 纯查询 ──────────────────────────────────────────

def test_get_queue_depth_empty(conn) -> None:
    """空队列：计数 0、两条龄期 None、malformed False（无停滞、不 fail-closed 误报）。
    含 A1 新增运行态龄期字段（running/oldest_running_age_s/oldest_running_malformed）。"""
    depth = repos.get_queue_depth(conn)
    assert depth == {
        "queued": 0, "waiting_review": 0, "running": 0,
        "oldest_queued_age_s": None, "oldest_queued_malformed": False,
        "oldest_running_age_s": None, "oldest_running_malformed": False,
    }


def test_get_queue_depth_counts_queued_and_waiting_review(conn) -> None:
    """queued/waiting_review 计数各按 status 精确统计（信息位）。tamper：把 get_queue_depth
    硬编码返 {queued:0,...} → 本断言红（证计数 load-bearing 非伪造）。"""
    for i in range(3):
        _seed_task(conn, f"q_{i}", ("queued",))
    for i in range(2):
        _seed_task(conn, f"wr_{i}", ("queued", "validating", "running", "waiting_review"))

    depth = repos.get_queue_depth(conn)
    assert depth["queued"] == 3
    assert depth["waiting_review"] == 2


def test_get_queue_depth_excludes_eval_origin(conn) -> None:
    """口径对齐 claim_next_queued（仅 origin='user'）：eval-origin queued 任务不计入——
    否则 eval 跑批深度污染 job 队列停滞判定。tamper：删查询的 origin='user' 过滤 → 本断言红。"""
    _seed_task(conn, "user_q", ("queued",), origin="user")
    _seed_task(conn, "eval_q", ("queued",), origin="eval")

    depth = repos.get_queue_depth(conn)
    assert depth["queued"] == 1  # 只数 user，eval 被排除


def test_get_queue_depth_oldest_age_reflects_backdate(conn) -> None:
    """最老 queued 龄期真反映**入队时刻 updated_at**（挂死冻结队列时此值无界增长=停滞信号源）。"""
    _seed_task(conn, "old_q", ("queued",))
    _seed_task(conn, "new_q", ("queued",))
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (old, "old_q"))

    depth = repos.get_queue_depth(conn)
    assert depth["oldest_queued_malformed"] is False
    assert depth["oldest_queued_age_s"] >= 3000  # ~1h，证取的是最老（backdated）那条


def test_get_queue_depth_queued_age_is_enqueue_time_not_created_at(conn) -> None:
    """★A4-P2-1 tamper 锚：queued 龄期基于**入队时刻 updated_at** 而非 created_at。依赖任务
    created 早、入队晚——created_at 老但 updated_at（入队时刻）新的任务不该被算成「排了很久」。
    tamper：把 get_queue_depth 的 MIN(updated_at) 改回 MIN(created_at) → 本任务假老 → 断言红。"""
    _seed_task(conn, "dep_q", ("queued",))
    # 依赖任务：created_at 回拨 1h（建得早），但 updated_at=入队时刻（刚才 set queued，≈now）。
    old_created = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE tasks SET created_at = ? WHERE id = ?", (old_created, "dep_q"))

    depth = repos.get_queue_depth(conn)
    assert depth["oldest_queued_malformed"] is False
    # 龄期取 updated_at（入队时刻，≈now）→ 应很小（远 < 老 created_at 的 3600s）。
    assert depth["oldest_queued_age_s"] < 60  # 若误取 created_at 会 ~3600 → 红


def test_get_queue_depth_malformed_updated_at_fail_closed(conn) -> None:
    """畸形 updated_at：无法算龄 → 龄期 None + malformed=True（绝不假报健康，fail-closed）。
    tamper：把 malformed 恒 False → readyz 会对无法算龄的停滞队列假报 ready → 下游端点红。"""
    _seed_task(conn, "bad_q", ("queued",))
    conn.execute("UPDATE tasks SET updated_at = 'not-a-timestamp' WHERE id = ?", ("bad_q",))

    depth = repos.get_queue_depth(conn)
    assert depth["queued"] == 1
    assert depth["oldest_queued_age_s"] is None
    assert depth["oldest_queued_malformed"] is True


def test_get_queue_depth_naive_updated_at_fail_closed(conn) -> None:
    """naive（无时区）updated_at 同样 fail-closed（镜像 _worker_freshness 的 naive 处理）。"""
    _seed_task(conn, "naive_q", ("queued",))
    conn.execute("UPDATE tasks SET updated_at = '2020-01-01T00:00:00' WHERE id = ?", ("naive_q",))

    depth = repos.get_queue_depth(conn)
    assert depth["oldest_queued_age_s"] is None
    assert depth["oldest_queued_malformed"] is True


def test_get_queue_depth_mixed_valid_and_malformed_still_flags(conn) -> None:
    """★R3-P2 tamper 锚（Codex R3 verbatim）：合法与畸形 queued 行**混杂**时畸形不被遮蔽。旧
    MIN(updated_at) 按字符串序取最小——合法 ISO（"2026-…"）排在 "not-a-timestamp" 之前，畸形行
    从不进 _age_seconds → malformed 恒 False，违背「无法算龄=绝不假报健康」fail-closed 方针。修后
    逐行解析：malformed=True（任一行畸形）**且**龄期取合法行里最老（畸形不遮蔽也不顶替观测）。
    tamper：把逐行解析改回 MIN 单行 → 本断言 malformed is True 红（实为 False）。"""
    _seed_task(conn, "ok_q", ("queued",))
    _seed_task(conn, "bad_q2", ("queued",))
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (old, "ok_q"))
    conn.execute("UPDATE tasks SET updated_at = 'not-a-timestamp' WHERE id = ?", ("bad_q2",))

    depth = repos.get_queue_depth(conn)
    assert depth["queued"] == 2
    assert depth["oldest_queued_malformed"] is True   # ★畸形行不被合法行的 MIN 排序遮蔽
    assert depth["oldest_queued_age_s"] is not None and depth["oldest_queued_age_s"] >= 3000
    # 龄期仍来自合法行（~1h），畸形行不顶替观测值——观测与 fail-closed 标志解耦


# ── A1 运行态龄期信号（repos.get_queue_depth）───────────────────────────────

def test_get_queue_depth_running_age_reflects_backdate(conn) -> None:
    """运行态龄期真反映最老执行态任务的 COALESCE(started_at, updated_at)（孤立挂死信号源）。
    tamper：把 running 龄期查询删掉/恒 None → 孤立挂死不可见 → readyz 假 200（下游端点红）。"""
    _seed_task(conn, "run_task", ("queued", "validating", "running"))
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE tasks SET started_at = ? WHERE id = ?", (old, "run_task"))

    depth = repos.get_queue_depth(conn)
    assert depth["running"] == 1
    assert depth["oldest_running_malformed"] is False
    assert depth["oldest_running_age_s"] >= 3000  # ~1h（backdated started_at）


def test_get_queue_depth_running_age_validating_uses_updated_at(conn) -> None:
    """validating 态 started_at 尚 NULL → 龄期回退 updated_at（认领→validating 时刻）。
    证 COALESCE 回退分支：孤立挂死可发生在 running 之前（卡校验），该态也须可见。"""
    _seed_task(conn, "val_task", ("queued", "validating"))
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (old, "val_task"))

    depth = repos.get_queue_depth(conn)
    assert depth["running"] == 1  # validating 计入执行态
    assert depth["oldest_running_age_s"] >= 3000


def test_get_queue_depth_running_excludes_eval_origin(conn) -> None:
    """运行态计数/龄期同口径 origin='user'——eval 执行态不污染孤立挂死判定。"""
    _seed_task(conn, "user_run", ("queued", "validating", "running"), origin="user")
    _seed_task(conn, "eval_run", ("queued", "validating", "running"), origin="eval")

    depth = repos.get_queue_depth(conn)
    assert depth["running"] == 1  # 只数 user


# ── /api/readyz 就绪裁决（M2† 主锚 + M1↔M2† 龄期 degrade）──────────────────
# 既有 M2† 回归（no_worker/stale → 503, fresh 空队列 → 200）在 test_p0_admission_gate.py；
# 本文件补 M2 完整版增量：队列计数信息位 + 龄期超阈 degrade。

def _beat_fresh(app) -> None:
    c = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(c, generation="test-gen")
    finally:
        c.close()


def _seed_via_app(app, task_id: str, statuses: tuple[str, ...], *, origin: str = "user") -> None:
    c = app.state.conn_factory()
    try:
        _seed_task(c, task_id, statuses, origin=origin)
    finally:
        c.close()


def test_readyz_deep_young_queue_still_ready(app_env) -> None:
    """深但年轻的队列：worker 心跳新鲜 → 仍 200（深队列绝不误翻红=无假红），且 payload
    queue.queued 反映真实计数。tamper：把 status_code 改据队列深度而非 fresh → 本测试红。"""
    client, app = app_env
    _beat_fresh(app)
    for i in range(5):
        _seed_via_app(app, f"deep_{i}", ("queued",))

    r = client.get("/api/readyz")
    assert r.status_code == 200  # 深队列 + 新鲜 worker = ready（无假红）
    body = r.json()
    assert body["status"] == "ready"
    assert body["queue"]["queued"] == 5  # 计数 load-bearing


def test_readyz_payload_counts_match_db(app_env) -> None:
    """readyz payload 的 queued/waiting_review 计数 == DB 实际。"""
    client, app = app_env
    _beat_fresh(app)
    for i in range(4):
        _seed_via_app(app, f"pc_q_{i}", ("queued",))
    for i in range(2):
        _seed_via_app(app, f"pc_wr_{i}", ("queued", "validating", "running", "waiting_review"))

    q = client.get("/api/readyz").json()["queue"]
    assert q["queued"] == 4
    assert q["waiting_review"] == 2


def test_readyz_degraded_when_oldest_queued_stalled(app_env, monkeypatch) -> None:
    """★Codex R1-P1-c 解耦后契约：worker 心跳**新鲜**但最老 queued 龄期超阈 → HTTP **200** +
    body degraded=true + status="degraded"（**不再 503**）。单串行 worker 健康 drain 合法 backlog
    时任务龄期自然增长、且合法长任务与挂死凭龄期无法区分——凭龄期 503 会假杀健康 worker（触发外部
    重启中断合法长任务）。故龄期只作可观测 degraded 软信号，503 只留心跳死（进程真 down）。
    tamper①：把 readyz degraded 计算里 queued 龄期项拿掉 → 停滞队列不再标 degraded（degraded 断言红）；
    tamper②：把 age 重新耦合进 ready 503 gate（ready = fresh and not degraded）→ 合法长任务假 503
    （status_code 200 断言红）。"""
    client, app = app_env
    _beat_fresh(app)  # 心跳新鲜
    _seed_via_app(app, "stalled_q", ("queued",))
    # 把该 queued 任务 updated_at（入队时刻）回拨 10s，阈值压到 1s → 龄期 ~10s > 1s = 停滞。
    old = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    c = app.state.conn_factory()
    try:
        c.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (old, "stalled_q"))
    finally:
        c.close()
    monkeypatch.setattr(config, "QUEUE_STALL_THRESHOLD_S", 1.0)

    r = client.get("/api/readyz")
    assert r.status_code == 200  # ★心跳新鲜=进程活→200（龄期不再 503，Codex R1-P1-c）
    body = r.json()
    assert body["status"] == "degraded"     # 队列压力软信号
    assert body["degraded"] is True
    assert body["worker"]["fresh"] is True   # 心跳仍新鲜——证是龄期（非心跳）触发的 degraded 标记
    assert body["queue"]["oldest_queued_age_s"] >= 1.0


def test_readyz_degraded_when_oldest_queued_malformed(app_env) -> None:
    """龄期无法算（畸形 updated_at）→ 观测侧 fail-closed 当停滞 → HTTP 200 + degraded=true，即便
    worker 新鲜（Codex R1-P1-c 解耦：畸形龄期是观测标记非 503 gate；503 只留心跳死）。绝不因
    '算不出龄期'就假报 ready 干净。"""
    client, app = app_env
    _beat_fresh(app)
    _seed_via_app(app, "malformed_q", ("queued",))
    c = app.state.conn_factory()
    try:
        c.execute("UPDATE tasks SET updated_at = 'garbage' WHERE id = ?", ("malformed_q",))
    finally:
        c.close()

    r = client.get("/api/readyz")
    assert r.status_code == 200  # 心跳新鲜→200
    body = r.json()
    assert body["degraded"] is True                        # 畸形龄期 fail-closed 当停滞（观测标记）
    assert body["status"] == "degraded"
    assert body["worker"]["fresh"] is True
    assert body["queue"]["oldest_queued_malformed"] is True


def test_readyz_degraded_when_running_task_stalled(app_env, monkeypatch) -> None:
    """★A1-① 孤立挂死观测 witness（补 loop-auditor 盲点）：空 queued 队列 + worker 心跳**新鲜**，
    但一条**执行态**任务龄期超 RUNNING_TASK_STALL_THRESHOLD_S → HTTP **200** + degraded=true（Codex
    R1-P1-c 解耦：运行态龄期是观测软信号非 503 gate——单串行 worker 上合法长任务 8 问 knowledge_qa
    最坏 >1900s 与挂死无法凭龄期区分，凭它 503 会假杀合法长任务；挂死兜底是宽墙钟 reaper 非 readyz）。
    运行态龄期能把「心跳看不见（daemon 恒新鲜）+ queued 龄期也看不见（队列空）」的孤立挂死以 degraded
    暴露给 operator。tamper：把 readyz degraded 计算的 running_age 项拿掉 → 孤立挂死不再标 degraded
    （degraded 断言红=观测盲区）。"""
    client, app = app_env
    _beat_fresh(app)  # 心跳新鲜
    # 一条执行态（running）任务，started_at 回拨 10s；**queued 队列为空**（孤立挂死）。
    _seed_via_app(app, "hung_running", ("queued", "validating", "running"))
    old = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    c = app.state.conn_factory()
    try:
        c.execute("UPDATE tasks SET started_at = ? WHERE id = ?", (old, "hung_running"))
    finally:
        c.close()
    monkeypatch.setattr(config, "RUNNING_TASK_STALL_THRESHOLD_S", 1.0)

    r = client.get("/api/readyz")
    assert r.status_code == 200  # ★心跳新鲜=进程活→200（运行态龄期不再 503，Codex R1-P1-c）
    body = r.json()
    assert body["status"] == "degraded"
    assert body["degraded"] is True
    assert body["worker"]["fresh"] is True   # 心跳仍新鲜——证是运行态龄期触发的 degraded 标记
    assert body["queue"]["queued"] == 0      # 空 queued 队列（孤立挂死盲点）
    assert body["queue"]["oldest_running_age_s"] >= 1.0


def test_readyz_degraded_when_running_task_malformed(app_env) -> None:
    """运行态龄期无法算（畸形 started_at）→ 观测侧 fail-closed 当停滞 → HTTP 200 + degraded=true，
    即便 worker 新鲜（Codex R1-P1-c 解耦：畸形运行态龄期是观测标记非 503 gate）。"""
    client, app = app_env
    _beat_fresh(app)
    _seed_via_app(app, "bad_running", ("queued", "validating", "running"))
    c = app.state.conn_factory()
    try:
        c.execute("UPDATE tasks SET started_at = 'garbage' WHERE id = ?", ("bad_running",))
    finally:
        c.close()

    r = client.get("/api/readyz")
    assert r.status_code == 200  # 心跳新鲜→200
    body = r.json()
    assert body["degraded"] is True
    assert body["status"] == "degraded"
    assert body["worker"]["fresh"] is True
    assert body["queue"]["oldest_running_malformed"] is True


def test_readyz_stale_worker_503_regardless_of_queue(app_env) -> None:
    """M2† 不回归：worker 心跳过期时，无论队列深浅/龄期，一律 503——心跳新鲜度仍是就绪
    的必要条件。tamper：把就绪判定去掉 `fresh is True` 项、只看队列 → 死 worker + 空队列
    会假报 200 → 本测试红。"""
    client, app = app_env
    # 写一条陈旧心跳（2020 年）+ 深队列。
    c = app.state.conn_factory()
    try:
        c.execute(
            "INSERT INTO worker_heartbeats (worker_id, generation, detail, started_at, last_beat_at) "
            "VALUES ('default', 'g', NULL, ?, ?) "
            "ON CONFLICT(worker_id) DO UPDATE SET last_beat_at = excluded.last_beat_at",
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"),
        )
        _seed_task(c, "sw_q", ("queued",))
    finally:
        c.close()

    r = client.get("/api/readyz")
    assert r.status_code == 503  # 心跳过期 → 不就绪（队列非空也不能救）
    assert r.json()["worker"]["fresh"] is False
