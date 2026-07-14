"""批B 只读聚合端点：全局 promotions + stats/overview。oracle=夹具种入已知
治理事件后断言精确计数；tamper 语义见各测试注释。"""
from __future__ import annotations

import json


def _insert_promotion(conn, agent_id: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO promotions (agent_id, agent_version, from_maturity, to_maturity,"
        " eval_run_id, checks_json, confirmations_json, confirmed_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (agent_id, "0.1.0", "L0", "L1", "er-1", json.dumps({}), json.dumps({}), "测试签发人", created_at),
    )
    conn.commit()


def test_global_promotions_desc_and_limit(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_promotion(conn, "hello_agent", "2026-07-13T01:00:00+00:00")
        _insert_promotion(conn, "review_agent", "2026-07-13T02:00:00+00:00")
    finally:
        conn.close()
    r = client.get("/api/promotions")
    assert r.status_code == 200
    rows = r.json()
    assert [x["agent_id"] for x in rows[:2]] == ["review_agent", "hello_agent"]  # 最近优先
    assert "checks" in rows[0] and "confirmed_by" in rows[0]
    r2 = client.get("/api/promotions", params={"limit": 1})
    assert len(r2.json()) == 1


def test_global_promotions_empty_ok(app_env):
    client, _ = app_env
    r = client.get("/api/promotions")
    assert r.status_code == 200
    assert r.json() == []


def _insert_completed_task(conn, task_id: str, finished_at: str, origin: str = "user") -> None:
    # 只填 stats 查询涉及列 + NOT NULL 列；其余可空列（started_at/error_message/
    # metadata_json/conversation_id/data_classification）留缺省，以 db.py DDL 为准。
    conn.execute(
        "INSERT INTO tasks (id, agent_id, agent_version, name, status, inputs_json,"
        " input_file_ids, output_file_ids, created_by, origin,"
        " created_at, updated_at, finished_at)"
        " VALUES (?, 'hello_agent', '0.1.0', ?, 'completed', '{}', '[]', '[]',"
        " '测试工程师', ?, ?, ?, ?)",
        (task_id, task_id, origin, finished_at, finished_at, finished_at),
    )
    conn.commit()


def _insert_review_event(conn, task_id: str, created_at: str) -> None:
    # task_events DDL：event_id NOT NULL UNIQUE + level NOT NULL + message NOT NULL
    # （无 seq 列）——event_id 用 task_id+created_at 拼保证跨行唯一。
    conn.execute(
        "INSERT INTO task_events (event_id, task_id, event_type, level, message,"
        " payload_json, created_at)"
        " VALUES (?, ?, 'review_approved', 'info', '评审通过', '{}', ?)",
        (f"evt-{task_id}-{created_at}", task_id, created_at),
    )
    conn.commit()


SINCE = "2026-07-13T00:00:00+00:00"
BEFORE = "2026-07-12T23:59:59+00:00"
AFTER = "2026-07-13T08:00:00+00:00"


def _insert_task_null_finished(conn, task_id: str, created_at: str) -> None:
    """反例见证（B-T2 审查②）：completed 但 finished_at 为 NULL 的畸形行——
    拆掉实现里 finished_at IS NOT NULL 过滤时，本行会被 >= 比较连带排除吗？
    不会（SQLite NULL >= x 为 NULL 假），但 COUNT 语义靠双条件冗余表达意图，
    真正咬合见 test_stats_overview_exact_counts 的 event_type/origin 维。"""
    conn.execute(
        "INSERT INTO tasks (id, agent_id, agent_version, name, status, inputs_json,"
        " input_file_ids, output_file_ids, created_by, origin, created_at, updated_at)"
        " VALUES (?, 'hello_agent', '0.1.0', ?, 'completed', '{}', '[]', '[]',"
        " '测试工程师', 'user', ?, ?)",
        (task_id, task_id, created_at, created_at),
    )
    conn.commit()


def _insert_other_event(conn, task_id: str, created_at: str) -> None:
    """反例见证：非 review_approved 事件——拆掉 event_type 过滤本行必混入计数。"""
    conn.execute(
        "INSERT INTO task_events (event_id, task_id, event_type, level, message,"
        " payload_json, created_at)"
        " VALUES (?, ?, 'task_created', 'info', '任务已创建', '{}', ?)",
        (f"evt-other-{task_id}-{created_at}", task_id, created_at),
    )
    conn.commit()


def test_stats_overview_exact_counts(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_completed_task(conn, "t-in", AFTER)
        _insert_completed_task(conn, "t-out", BEFORE)          # 界前不计
        _insert_completed_task(conn, "t-eval", AFTER, origin="eval")  # eval 不计
        _insert_task_null_finished(conn, "t-null", AFTER)      # NULL finished_at 不计
        _insert_review_event(conn, "t-in", AFTER)
        _insert_review_event(conn, "t-out", BEFORE)
        _insert_other_event(conn, "t-in", AFTER)               # 非 review 事件不计
        _insert_promotion(conn, "hello_agent", AFTER)
        _insert_promotion(conn, "hello_agent", BEFORE)
    finally:
        conn.close()
    r = client.get("/api/stats/overview", params={"since": SINCE})
    assert r.status_code == 200
    body = r.json()
    # tamper（B-T2 审查②变异实证后补齐反例）：拆掉实现里 event_type 过滤/
    # origin 过滤/since 比较任一，本测必红（夹具已含每一维的反例见证行）。
    assert body["tasks_completed"] == 1
    assert body["reviews_approved"] == 1
    assert body["promotions"] == 1
    assert isinstance(body["curated_cases_total"], int)


def test_stats_since_boundary_inclusive(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_completed_task(conn, "t-edge", SINCE)  # 恰在界上：计入（>=）
    finally:
        conn.close()
    body = client.get("/api/stats/overview", params={"since": SINCE}).json()
    assert body["tasks_completed"] == 1


def test_stats_since_required_and_valid(app_env):
    client, _ = app_env
    assert client.get("/api/stats/overview").status_code == 422
    assert client.get("/api/stats/overview", params={"since": "昨天"}).status_code == 422
    # naive/纯日期无确定时刻语义，fail-closed 拒收（B-T2 审查③）
    assert client.get("/api/stats/overview", params={"since": "2026-07-13"}).status_code == 422
    assert client.get("/api/stats/overview", params={"since": "2026-07-13T00:00:00"}).status_code == 422


def test_stats_since_overflow_on_utc_normalize_422_not_500(app_env):
    """治理审 R1 P2 修复回归：极端年份+大偏移在 astimezone(UTC) 归一化时会
    OverflowError（date value out of range）——fix 前该路径未被 try 覆盖会 500，
    fix 后归一化行并入同一 try，与 ValueError 同归 422 fail-closed。tamper：把
    实现里的 except 子句改回单 ValueError，本测必红（500 而非 422）。"""
    client, _ = app_env
    resp = client.get("/api/stats/overview", params={"since": "0001-01-01T00:00:00+23:59"})
    assert resp.status_code == 422


def test_stats_since_z_suffix_normalized(app_env):
    """B-T2 审查③实证的真 bug 回归：'Z' 后缀（JS toISOString 默认格式）同秒
    边界曾因 ASCII 'Z' > '.'/'+' 字典序错序漏计。归一化后 Z 表示与 +00:00
    表示必须等价计数。tamper：删掉实现里 astimezone 归一化行，本测必红。"""
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_completed_task(conn, "t-z-edge", "2026-07-13T08:00:00.123456+00:00")
    finally:
        conn.close()
    plus = client.get("/api/stats/overview", params={"since": "2026-07-13T08:00:00+00:00"}).json()
    zed = client.get("/api/stats/overview", params={"since": "2026-07-13T08:00:00Z"}).json()
    assert plus["tasks_completed"] == 1
    assert zed["tasks_completed"] == 1  # 归一化前此处为 0（漏计 bug）
    assert zed["since"] == "2026-07-13T08:00:00+00:00"  # 回显=生效窗口的归一化表示


def test_count_curated_cases_pure(tmp_path):
    from backend.app.api.stats import count_curated_cases
    d = tmp_path / "agents" / "a1" / "eval_cases"
    d.mkdir(parents=True)
    (d / "case_001_from_sample.json").write_text("{}")
    (d / "case_002_from_sample.json").write_text("{}")
    (d / "notes.md").write_text("")  # 非 case_*.json 不计
    assert count_curated_cases(tmp_path / "agents") == 2
    assert count_curated_cases(tmp_path / "不存在") == 0


def test_global_promotions_ordered_by_created_at_not_insertion(app_env):
    """Codex R2-P2 回归：恢复/回填可乱插入序——「最近」必须以 created_at 为准。
    夹具故意后插一条更早时间戳的行（id 更大但时间更早），断言时间序胜出。
    tamper：把实现改回 ORDER BY id DESC，本测必红。"""
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_promotion(conn, "agent_new", "2026-07-13T05:00:00+00:00")
        _insert_promotion(conn, "agent_backfill", "2026-07-01T00:00:00+00:00")  # 回填:id大时间早
    finally:
        conn.close()
    rows = client.get("/api/promotions").json()
    assert [x["agent_id"] for x in rows[:2]] == ["agent_new", "agent_backfill"]
