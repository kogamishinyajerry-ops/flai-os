"""Deployment truth witnesses for the append-only judgment ledgers.

The public seams are the local deployment self-check and the unauthenticated
``/api/health`` / ``/api/readyz`` probes.  Same-name SQLite objects are not
evidence: exact table/index/trigger structure must remain canonical.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from backend.app.storage import repos, review_schema
from scripts import deploy_selfcheck


_JUDGMENT_WITNESS_KEYS = {
    "advice_table_shape",
    "human_decision_table_shape",
    "review_event_witness_table_shape",
    "required_indexes",
    "required_triggers",
    "rowid_integrity",
    "provenance_integrity",
}


def _fake_health(monkeypatch, payload: dict[str, object]) -> None:
    def fake_get(_url: str) -> tuple[int, bytes]:
        return 200, json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(deploy_selfcheck, "_http_get", fake_get)


def _replace_trigger_with_noop(
    conn: sqlite3.Connection, trigger_name: str
) -> None:
    row = conn.execute(
        "SELECT tbl_name FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()
    assert row is not None, f"missing fixture trigger {trigger_name}"
    table = str(row[0])
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(
        f'CREATE TRIGGER "{trigger_name}" BEFORE UPDATE ON "{table}" '
        "BEGIN SELECT 1; END"
    )


def test_main_and_selfcheck_share_canonical_judgment_schema_contract() -> None:
    from backend.app import main as main_mod

    assert main_mod._judgment_schema_witnesses is review_schema.judgment_schema_witnesses
    assert (
        deploy_selfcheck._judgment_schema_witnesses
        is review_schema.judgment_schema_witnesses
    )
    assert set(deploy_selfcheck._JUDGMENT_SCHEMA_WITNESS_LABELS) == set(
        review_schema.JUDGMENT_SCHEMA_WITNESS_KEYS
    )


def test_offline_probe_and_judgment_contract_load_with_stdlib_only() -> None:
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from scripts import deploy_selfcheck; "
            "from backend.app.storage import review_schema; "
            "assert deploy_selfcheck._judgment_schema_witnesses "
            "is review_schema.judgment_schema_witnesses; "
            "assert all(review_schema.judgment_schema_witnesses("
            "__import__('sqlite3').connect(':memory:')).values()) is False",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_live_judgment_generation_requires_exact_true_and_all_witnesses(
    monkeypatch,
) -> None:
    valid_witnesses = {key: True for key in _JUDGMENT_WITNESS_KEYS}
    _fake_health(
        monkeypatch,
        {
            "judgment_capture_axis": True,
            "judgment_schema_witnesses": valid_witnesses,
        },
    )
    assert deploy_selfcheck.check_live_judgment_generation("http://new-api").ok is True

    for invalid_axis in (1, "true", None):
        _fake_health(
            monkeypatch,
            {
                "judgment_capture_axis": invalid_axis,
                "judgment_schema_witnesses": valid_witnesses,
            },
        )
        assert (
            deploy_selfcheck.check_live_judgment_generation("http://new-api").ok
            is False
        )

    broken = dict(valid_witnesses)
    broken["required_triggers"] = 1
    _fake_health(
        monkeypatch,
        {
            "judgment_capture_axis": True,
            "judgment_schema_witnesses": broken,
        },
    )
    assert (
        deploy_selfcheck.check_live_judgment_generation("http://new-api").ok
        is False
    )


def test_fresh_schema_passes_local_health_and_readyz_witnesses(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        local = deploy_selfcheck.check_judgment_schema(conn)
    finally:
        conn.close()

    assert local.ok is True
    health = client.get("/api/health")
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["judgment_capture_axis"] is True
    assert set(health_body["judgment_schema_witnesses"]) == _JUDGMENT_WITNESS_KEYS
    assert all(
        value is True for value in health_body["judgment_schema_witnesses"].values()
    )

    ready = client.get("/api/readyz")
    assert ready.status_code == 200
    ready_body = ready.json()
    assert ready_body["judgment_capture_axis"] is True
    assert ready_body["judgment_capture"]["schema_ready"] is True
    assert (
        ready_body["judgment_capture"]["schema_witnesses"]
        == health_body["judgment_schema_witnesses"]
    )


def test_missing_judgment_table_fails_local_health_and_readyz(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        conn.execute("DROP TABLE task_human_decisions")
        local = deploy_selfcheck.check_judgment_schema(conn)
    finally:
        conn.close()

    assert local.ok is False
    health_body = client.get("/api/health").json()
    assert health_body["judgment_schema_witnesses"]["human_decision_table_shape"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["judgment_capture"]["schema_ready"] is False


def test_same_name_noop_judgment_trigger_fails_all_deployment_witnesses(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        _replace_trigger_with_noop(
            conn, "trg_task_human_decisions_no_update"
        )
        local = deploy_selfcheck.check_judgment_schema(conn)
    finally:
        conn.close()

    assert local.ok is False
    health_body = client.get("/api/health").json()
    assert health_body["judgment_schema_witnesses"]["required_triggers"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["judgment_capture"]["schema_ready"] is False


def test_replayed_judgment_guard_with_mutated_provenance_fails_readyz(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        task = repos.create_task(
            conn,
            task_id="judgment-provenance-readyz",
            agent_id="reviewed_agent",
            agent_version="1.0.0",
            name="provenance readyz",
            created_by="创建工程师",
            created_by_username="creator",
            inputs={},
            input_file_ids=[],
            metadata={},
        )
        call = repos.record_model_call(
            conn,
            task_id=task["id"],
            agent_id="r0_review_advisor",
            model_profile="review",
            model_name="model-a",
            status="success",
        )
        repos.record_review_advice(
            conn,
            task_id=task["id"],
            model_call_id=call["id"],
            advisor_id="r0_review_advisor",
            advisor_version="0.1.0",
            model_profile="review",
            model_name="model-a",
            advisory_outcome="clear",
            doubts=[],
        )
        trigger_name = "trg_witnessed_model_calls_no_update"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f"DROP TRIGGER {trigger_name}")
        conn.execute("UPDATE model_calls SET status = 'failed' WHERE id = ?", (call["id"],))
        conn.execute(trigger_sql)
        local = deploy_selfcheck.check_judgment_schema(conn)
    finally:
        conn.close()

    assert local.ok is False
    health_body = client.get("/api/health").json()
    assert health_body["judgment_schema_witnesses"]["required_triggers"] is True
    assert health_body["judgment_schema_witnesses"]["provenance_integrity"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["judgment_capture"]["schema_ready"] is False


def test_judgment_table_structure_drift_fails_all_deployment_witnesses(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        conn.execute("ALTER TABLE task_review_advice ADD COLUMN future_drift TEXT")
        local = deploy_selfcheck.check_judgment_schema(conn)
    finally:
        conn.close()

    assert local.ok is False
    health_body = client.get("/api/health").json()
    assert health_body["judgment_schema_witnesses"]["advice_table_shape"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["judgment_capture"]["schema_ready"] is False
