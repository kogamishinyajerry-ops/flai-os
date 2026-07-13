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


def test_stats_overview_exact_counts(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_completed_task(conn, "t-in", AFTER)
        _insert_completed_task(conn, "t-out", BEFORE)          # 界前不计
        _insert_completed_task(conn, "t-eval", AFTER, origin="eval")  # eval 不计
        _insert_review_event(conn, "t-in", AFTER)
        _insert_review_event(conn, "t-out", BEFORE)
        _insert_promotion(conn, "hello_agent", AFTER)
        _insert_promotion(conn, "hello_agent", BEFORE)
    finally:
        conn.close()
    r = client.get("/api/stats/overview", params={"since": SINCE})
    assert r.status_code == 200
    body = r.json()
    # tamper：把实现里 event_type 过滤/origin 过滤/since 比较任一拆掉，本测必红。
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


def test_count_curated_cases_pure(tmp_path):
    from backend.app.api.stats import count_curated_cases
    d = tmp_path / "agents" / "a1" / "eval_cases"
    d.mkdir(parents=True)
    (d / "case_001_from_sample.json").write_text("{}")
    (d / "case_002_from_sample.json").write_text("{}")
    (d / "notes.md").write_text("")  # 非 case_*.json 不计
    assert count_curated_cases(tmp_path / "agents") == 2
    assert count_curated_cases(tmp_path / "不存在") == 0
