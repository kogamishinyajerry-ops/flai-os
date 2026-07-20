"""P2.8 deployment gate for exact promotion-ledger witnesses.

The seams are the stdlib-only offline deployment probe and the live health
payload consumed by that probe.  Object names alone are never sufficient:
the canonical storage witness must reject missing or same-name no-op objects.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from backend.app import config
from backend.app.storage import db as db_mod, design_promotion_schema, repos
from backend.app.storage.design_promotion_schema import (
    DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS,
    DESIGN_PROMOTION_TABLES,
)
from scripts import deploy_selfcheck


def _fresh_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "p28-deploy-gate.db"
    db_mod.init_db(db_path)
    return db_mod.get_conn(db_path)


def _serve_health(monkeypatch, payload: object) -> None:
    monkeypatch.setattr(
        deploy_selfcheck,
        "_http_get",
        lambda _url: (200, json.dumps(payload).encode("utf-8")),
    )


def test_all_six_promotion_ledgers_are_required_tables() -> None:
    assert set(DESIGN_PROMOTION_TABLES).issubset(deploy_selfcheck.REQUIRED_TABLES)


def test_missing_promotion_table_fails_local_gate(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    try:
        conn.execute("DROP TABLE design_idempotency")
        result = deploy_selfcheck.check_design_promotion_schema(conn)
    finally:
        conn.close()

    assert result.ok is False
    assert "table" in result.detail


def test_same_name_noop_promotion_trigger_fails_local_gate(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    try:
        trigger_name = "trg_design_comparisons_no_update"
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            f'CREATE TRIGGER "{trigger_name}" '
            "BEFORE UPDATE ON design_comparisons BEGIN SELECT 1; END"
        )
        result = deploy_selfcheck.check_design_promotion_schema(conn)
    finally:
        conn.close()

    assert result.ok is False
    assert "trigger" in result.detail


def test_fresh_schema_passes_local_health_and_readyz_witnesses(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=config.WORKER_GENERATION)
        assert deploy_selfcheck.check_tables(conn).ok is True
        assert deploy_selfcheck.check_design_promotion_schema(conn).ok is True
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["design_promotion_axis"] is True
    assert (
        health_body["design_promotion_generation"]
        == config.DESIGN_PROMOTION_GENERATION
    )
    assert set(health_body["design_promotion_schema_witnesses"]) == set(
        DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
    )
    assert all(
        value is True
        for value in health_body["design_promotion_schema_witnesses"].values()
    )

    ready = client.get("/api/readyz")
    assert ready.status_code == 200, json.dumps(
        ready.json(), ensure_ascii=False, indent=2
    )
    promotion = ready.json()["design_promotion"]
    assert promotion["runtime_generation"] is True
    assert promotion["generation"] == config.DESIGN_PROMOTION_GENERATION
    assert promotion["schema_ready"] is True
    assert (
        promotion["schema_witnesses"]
        == health_body["design_promotion_schema_witnesses"]
    )


def test_probe_reuses_canonical_contract_and_loads_with_stdlib_only() -> None:
    assert (
        deploy_selfcheck._design_promotion_schema_witnesses
        is design_promotion_schema.design_promotion_schema_witnesses
    )
    assert set(deploy_selfcheck._DESIGN_PROMOTION_SCHEMA_WITNESS_LABELS) == set(
        DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
    )
    assert (
        deploy_selfcheck.DESIGN_PROMOTION_GENERATION
        == config.DESIGN_PROMOTION_GENERATION
    )

    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from scripts import deploy_selfcheck; "
            "from backend.app import config; "
            "from backend.app.storage import design_promotion_schema; "
            "assert deploy_selfcheck._design_promotion_schema_witnesses "
            "is design_promotion_schema.design_promotion_schema_witnesses; "
            "assert deploy_selfcheck.DESIGN_PROMOTION_GENERATION "
            "== config.DESIGN_PROMOTION_GENERATION",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_live_promotion_generation_requires_exact_axis_generation_and_witnesses(
    monkeypatch,
) -> None:
    valid_witnesses = {
        key: True for key in DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
    }
    valid_payload = {
        "design_promotion_axis": True,
        "design_promotion_generation": config.DESIGN_PROMOTION_GENERATION,
        "design_promotion_schema_witnesses": valid_witnesses,
    }
    _serve_health(monkeypatch, valid_payload)
    assert deploy_selfcheck.check_live_design_promotion_generation(
        "http://new-api"
    ).ok is True

    for invalid_axis in (1, "true", None):
        payload = dict(valid_payload)
        payload["design_promotion_axis"] = invalid_axis
        _serve_health(monkeypatch, payload)
        assert deploy_selfcheck.check_live_design_promotion_generation(
            "http://old-api"
        ).ok is False

    stale_generation = dict(valid_payload)
    stale_generation["design_promotion_generation"] = "p28-stale-api"
    _serve_health(monkeypatch, stale_generation)
    assert deploy_selfcheck.check_live_design_promotion_generation(
        "http://stale-api"
    ).ok is False

    for non_literal_true in (1, "true", None):
        non_literal_witness = dict(valid_witnesses)
        non_literal_witness["required_triggers"] = non_literal_true
        broken_payload = dict(valid_payload)
        broken_payload["design_promotion_schema_witnesses"] = non_literal_witness
        _serve_health(monkeypatch, broken_payload)
        assert deploy_selfcheck.check_live_design_promotion_generation(
            "http://broken-api"
        ).ok is False


def test_main_runs_both_local_and_live_promotion_gates(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "selfcheck-main.db"
    db_path.touch()
    observed: list[str] = []
    promotion_ok = True

    def passed(name: str) -> deploy_selfcheck.Check:
        return deploy_selfcheck.Check(name, True, "test witness")

    monkeypatch.setattr(
        deploy_selfcheck, "check_db_file", lambda _db_path: passed("db")
    )
    for function_name in (
        "check_tables",
        "check_active_user",
        "check_classification_axis",
        "check_execution_binding_schema",
        "check_p23_schema",
        "check_conversation_lifecycle_schema",
        "check_review_route_schema",
        "check_judgment_schema",
        "check_outcome_schema",
        "check_worker_generation",
    ):
        monkeypatch.setattr(
            deploy_selfcheck,
            function_name,
            lambda _conn, name=function_name: passed(name),
        )

    def local_promotion(_conn: sqlite3.Connection) -> deploy_selfcheck.Check:
        observed.append("local")
        return deploy_selfcheck.Check(
            "local promotion", promotion_ok, "test witness"
        )

    monkeypatch.setattr(
        deploy_selfcheck, "check_design_promotion_schema", local_promotion
    )
    for function_name in (
        "check_health",
        "check_model_gateway_config",
        "check_live_classification_generation",
        "check_live_created_by_username_generation",
        "check_live_structured_question_generation",
        "check_live_conversation_lifecycle_generation",
        "check_live_eval_snapshot_generation",
        "check_live_search_addressing_generation",
        "check_live_named_review_inbox_generation",
        "check_live_judgment_generation",
        "check_live_outcome_generation",
        "check_live_agent_layer_generation",
        "check_live_agent_layer_readiness",
        "check_auth_generation",
    ):
        monkeypatch.setattr(
            deploy_selfcheck,
            function_name,
            lambda _base_url, name=function_name: passed(name),
        )

    def live_promotion(_base_url: str) -> deploy_selfcheck.Check:
        observed.append("live")
        return passed("live promotion")

    monkeypatch.setattr(
        deploy_selfcheck,
        "check_live_design_promotion_generation",
        live_promotion,
    )
    monkeypatch.setattr(
        deploy_selfcheck,
        "check_db_identity",
        lambda _base_url, _db_path: passed("identity"),
    )
    monkeypatch.setattr(
        deploy_selfcheck, "check_frontend_dist", lambda: passed("frontend")
    )
    monkeypatch.setattr(
        deploy_selfcheck, "check_writable_dirs", lambda: passed("writable")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_selfcheck.py",
            "--base-url",
            "http://p28-api",
            "--db",
            str(db_path),
        ],
    )

    assert deploy_selfcheck.main() == 0
    assert observed == ["local", "live"]

    observed.clear()
    promotion_ok = False
    assert deploy_selfcheck.main() == 1
    assert observed == ["local", "live"]
