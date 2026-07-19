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


def test_main_selfcheck_and_report_share_canonical_outcome_contract() -> None:
    from backend.app import main as main_mod
    from scripts import usage_report

    assert main_mod._outcome_schema_witnesses is outcome_schema.outcome_schema_witnesses
    assert deploy_selfcheck._outcome_schema_witnesses is outcome_schema.outcome_schema_witnesses
    assert usage_report._outcome_schema_witnesses is outcome_schema.outcome_schema_witnesses
    assert set(deploy_selfcheck._OUTCOME_SCHEMA_WITNESS_LABELS) == _WITNESS_KEYS
    assert "artifact_outcome_events" in deploy_selfcheck.REQUIRED_TABLES
    assert config.WORKER_GENERATION.endswith("+adr36-outcome-flow")


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
        {"outcome_telemetry_axis": True, "outcome_schema_witnesses": valid},
    )
    assert deploy_selfcheck.check_live_outcome_generation("http://api").ok is True

    _fake_health(
        monkeypatch,
        {"outcome_telemetry_axis": 1, "outcome_schema_witnesses": valid},
    )
    assert deploy_selfcheck.check_live_outcome_generation("http://api").ok is False
    broken = dict(valid)
    broken["required_triggers"] = 1
    _fake_health(
        monkeypatch,
        {"outcome_telemetry_axis": True, "outcome_schema_witnesses": broken},
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
