"""ADR-0036 deployment witnesses: live API, exact schema, and worker generation."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from backend.app import config
from backend.app.storage import outcome_schema, repos
from scripts import deploy_selfcheck


_WITNESS_KEYS = set(outcome_schema.OUTCOME_SCHEMA_WITNESS_KEYS)


def _fake_health(monkeypatch, payload: dict[str, object]) -> None:
    monkeypatch.setattr(
        deploy_selfcheck,
        "_http_get",
        lambda _url: (200, json.dumps(payload).encode("utf-8")),
    )


def _seed_captured_artifact(conn: sqlite3.Connection) -> str:
    task_id = "epoch-source"
    file_id = "epoch-file"
    repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="epoch witness",
        created_by="测试工程师",
        created_by_username="test_engineer",
        inputs={},
        input_file_ids=[],
        metadata={},
        origin="user",
    )
    repos.create_file(
        conn,
        file_id=file_id,
        task_id=task_id,
        kind="output",
        filename="epoch.txt",
        path="/tmp/epoch.txt",
        size_bytes=5,
        sha256="a" * 64,
        classification="internal",
    )
    repos.set_task_outputs(conn, task_id, [file_id])
    for status in ("queued", "validating", "running", "waiting_review"):
        repos.set_task_status(conn, task_id, status)
    repos.apply_human_review(
        conn,
        task_id,
        action="approve",
        reviewer="测试工程师",
        reviewer_username="test_engineer",
        reason_code=None,
        comment="epoch baseline",
    )
    return file_id


def test_main_selfcheck_and_report_share_canonical_outcome_contract() -> None:
    from backend.app import main as main_mod
    from scripts import usage_report

    assert main_mod._outcome_schema_witnesses is outcome_schema.outcome_schema_witnesses
    assert deploy_selfcheck._outcome_schema_witnesses is outcome_schema.outcome_schema_witnesses
    assert usage_report._outcome_schema_witnesses is outcome_schema.outcome_schema_witnesses
    assert set(deploy_selfcheck._OUTCOME_SCHEMA_WITNESS_LABELS) == _WITNESS_KEYS
    assert "artifact_outcome_events" in deploy_selfcheck.REQUIRED_TABLES
    assert config.WORKER_GENERATION.endswith(
        "+adr36-outcome-flow+jerryagent-layer-v1"
    )


def test_outcome_probe_contract_loads_with_stdlib_only() -> None:
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from scripts import deploy_selfcheck, usage_report; "
            "from backend.app.storage import outcome_schema; "
            "assert deploy_selfcheck._outcome_schema_witnesses "
            "is outcome_schema.outcome_schema_witnesses; "
            "assert usage_report._outcome_schema_witnesses "
            "is outcome_schema.outcome_schema_witnesses",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_live_outcome_generation_requires_exact_true_and_all_witnesses(monkeypatch) -> None:
    valid = {key: True for key in _WITNESS_KEYS}
    _fake_health(
        monkeypatch,
        {
            "outcome_telemetry_axis": True,
            "outcome_telemetry_generation": config.OUTCOME_TELEMETRY_GENERATION,
            "outcome_schema_witnesses": valid,
        },
    )
    assert deploy_selfcheck.check_live_outcome_generation("http://api").ok is True

    _fake_health(
        monkeypatch,
        {
            "outcome_telemetry_axis": 1,
            "outcome_telemetry_generation": config.OUTCOME_TELEMETRY_GENERATION,
            "outcome_schema_witnesses": valid,
        },
    )
    assert deploy_selfcheck.check_live_outcome_generation("http://api").ok is False
    _fake_health(
        monkeypatch,
        {
            "outcome_telemetry_axis": True,
            "outcome_telemetry_generation": "adr36-stale-api",
            "outcome_schema_witnesses": valid,
        },
    )
    assert deploy_selfcheck.check_live_outcome_generation("http://api").ok is False
    broken = dict(valid)
    broken["required_triggers"] = 1
    _fake_health(
        monkeypatch,
        {
            "outcome_telemetry_axis": True,
            "outcome_telemetry_generation": config.OUTCOME_TELEMETRY_GENERATION,
            "outcome_schema_witnesses": broken,
        },
    )
    assert deploy_selfcheck.check_live_outcome_generation("http://api").ok is False


def test_fresh_outcome_schema_passes_local_health_and_readyz(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=config.WORKER_GENERATION)
        assert deploy_selfcheck.check_outcome_schema(conn).ok is True
    finally:
        conn.close()

    health = client.get("/api/health").json()
    assert health["outcome_telemetry_axis"] is True
    assert (
        health["outcome_telemetry_generation"]
        == config.OUTCOME_TELEMETRY_GENERATION
    )
    assert set(health["outcome_schema_witnesses"]) == _WITNESS_KEYS
    assert all(value is True for value in health["outcome_schema_witnesses"].values())
    ready = client.get("/api/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["outcome_telemetry"]["schema_ready"] is True
    assert body["outcome_telemetry"]["worker_generation_ready"] is True


def test_same_name_noop_outcome_trigger_fails_health_readyz_and_local_gate(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=config.WORKER_GENERATION)
        conn.execute("DROP TRIGGER trg_artifact_outcomes_no_update")
        conn.execute(
            "CREATE TRIGGER trg_artifact_outcomes_no_update "
            "BEFORE UPDATE ON artifact_outcome_events BEGIN SELECT 1; END"
        )
        assert deploy_selfcheck.check_outcome_schema(conn).ok is False
    finally:
        conn.close()

    health = client.get("/api/health").json()
    assert health["outcome_schema_witnesses"]["required_triggers"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["outcome_telemetry"]["schema_ready"] is False


def test_extra_unique_index_that_would_collapse_downloads_fails_exact_gate(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=config.WORKER_GENERATION)
        conn.execute(
            "CREATE UNIQUE INDEX malicious_dedupe_downloads "
            "ON artifact_outcome_events(source_file_id, actor_username, event_type)"
        )
        assert deploy_selfcheck.check_outcome_schema(conn).ok is False
    finally:
        conn.close()
    assert client.get("/api/health").json()["outcome_schema_witnesses"]["required_indexes"] is False
    assert client.get("/api/readyz").status_code == 503


def test_source_task_guard_uses_bounded_index(app_env) -> None:
    _client, app = app_env
    conn = app.state.conn_factory()
    try:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT 1 FROM artifact_outcome_events "
            "WHERE source_task_id = ? LIMIT 1",
            ("missing",),
        ).fetchall()
    finally:
        conn.close()
    detail = " ".join(str(row[3]) for row in plan)
    assert "idx_artifact_outcomes_source_task_created" in detail
    assert "SEARCH" in detail


def test_health_and_readyz_deep_recheck_persisted_provenance(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=config.WORKER_GENERATION)
    finally:
        conn.close()

    original = outcome_schema._provenance_integrity
    calls = 0

    def count_deep_rechecks(conn):
        nonlocal calls
        calls += 1
        return original(conn)

    monkeypatch.setattr(outcome_schema, "_provenance_integrity", count_deep_rechecks)
    health = client.get("/api/health")
    ready = client.get("/api/readyz")
    assert health.status_code == 200
    assert health.json()["outcome_schema_witnesses"]["provenance_integrity"] is True
    assert ready.status_code == 200
    assert (
        ready.json()["outcome_telemetry"]["schema_witnesses"][
            "provenance_integrity"
        ]
        is True
    )
    assert calls == 2


def test_health_deep_recheck_stays_red_after_guard_drop_and_restore(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=config.WORKER_GENERATION)
        file_id = _seed_captured_artifact(conn)
        trigger_names = (
            "trg_witnessed_artifact_files_no_update",
            "trg_review_package_files_no_update",
        )
        trigger_sql = {
            name: conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (name,),
            ).fetchone()[0]
            for name in trigger_names
        }
        conn.execute("BEGIN IMMEDIATE")
        for name in trigger_names:
            conn.execute(f"DROP TRIGGER {name}")
        conn.execute("UPDATE files SET kind = 'input' WHERE id = ?", (file_id,))
        for name in trigger_names:
            conn.execute(trigger_sql[name])
        conn.execute("COMMIT")
        assert outcome_schema.outcome_schema_witnesses(conn)[
            "provenance_integrity"
        ] is False
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    witnesses = health.json()["outcome_schema_witnesses"]
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["outcome_telemetry"]["schema_witnesses"][
        "provenance_integrity"
    ] is False


def test_readyz_rejects_fresh_old_worker_generation_even_with_exact_schema(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation="pre-adr36-worker")
    finally:
        conn.close()

    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    body = ready.json()
    assert body["worker"]["fresh"] is True
    assert body["worker"]["generation_ready"] is False
    assert body["outcome_telemetry"]["worker_generation_ready"] is False
