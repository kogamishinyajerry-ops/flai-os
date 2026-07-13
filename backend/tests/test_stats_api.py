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
