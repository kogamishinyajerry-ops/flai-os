"""P2.6 lifecycle generation and exact served-DB deployment gates."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.storage import db as db_mod
from backend.app.storage import repos
from backend.app.storage.conversation_lifecycle_schema import (
    CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS,
    conversation_lifecycle_schema_witnesses,
)
from scripts import deploy_selfcheck


def _replace_trigger_with_noop(
    conn: sqlite3.Connection, trigger_name: str
) -> None:
    row = conn.execute(
        "SELECT tbl_name FROM sqlite_master WHERE type='trigger' AND name=?",
        (trigger_name,),
    ).fetchone()
    assert row is not None
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(
        f'CREATE TRIGGER "{trigger_name}" BEFORE INSERT ON "{row[0]}" '
        "BEGIN SELECT 1; END"
    )


def test_supported_legacy_rows_migrate_without_inventing_lifecycle_events(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-conversations.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                recommendation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO conversations VALUES
                ('conv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'guide_agent',
                 'active', '旧用户', NULL,
                 '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
                ('conv_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'guide_agent',
                 'concluded', '旧用户', NULL,
                 '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            """
        )
    finally:
        conn.close()

    db_mod.init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        projections = conn.execute(
            "SELECT title, lifecycle_revision, archived_at FROM conversations "
            "ORDER BY id"
        ).fetchall()
        event_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_lifecycle_events"
        ).fetchone()[0]
        witnesses = conversation_lifecycle_schema_witnesses(conn)
    finally:
        conn.close()

    assert projections == [(None, 0, None), (None, 0, None)]
    assert event_count == 0
    assert all(
        witnesses.get(key) is True
        for key in CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
    )


def test_nonempty_lifecycle_ledger_tamper_fails_restart_before_repair(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tampered-ledger.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_" + "c" * 32,
            agent_id="guide_agent",
            created_by="测试工程师",
            created_by_username="test_engineer",
        )
        repos.append_conversation_lifecycle_event(
            conn,
            conversation_id="conv_" + "c" * 32,
            event_type="renamed",
            actor_username="test_engineer",
            lifecycle_revision=0,
            title="原标题",
        )
        conn.execute("DROP TRIGGER trg_conversation_lifecycle_events_no_update")
        conn.execute(
            "UPDATE conversation_lifecycle_events SET title='被篡改'"
        )
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="lifecycle schema witness"):
        db_mod.init_db(db_path)


def test_health_readyz_and_local_selfcheck_fail_closed_on_noop_trigger(
    app_env,
) -> None:
    client, app = app_env
    healthy = client.get("/api/health")
    assert healthy.status_code == 200
    assert healthy.json()["conversation_lifecycle_axis"] is True
    assert all(
        healthy.json()["conversation_lifecycle_schema_witnesses"].get(key)
        is True
        for key in CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
    )

    conn = app.state.conn_factory()
    try:
        assert deploy_selfcheck.check_conversation_lifecycle_schema(conn).ok is True
        _replace_trigger_with_noop(
            conn, "trg_conversation_lifecycle_events_no_update"
        )
        local_check = deploy_selfcheck.check_conversation_lifecycle_schema(conn)
    finally:
        conn.close()
    assert local_check.ok is False

    degraded_health = client.get("/api/health").json()
    assert degraded_health["conversation_lifecycle_schema_witnesses"][
        "required_triggers"
    ] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    lifecycle = ready.json()["conversation_lifecycle"]
    assert lifecycle["runtime_generation"] is True
    assert lifecycle["schema_ready"] is False
    assert lifecycle["schema_witnesses"]["required_triggers"] is False


def test_live_selfcheck_requires_exact_axis_and_every_remote_witness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    witnesses = {
        key: True for key in CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
    }

    def serve(payload: dict[str, object]) -> None:
        monkeypatch.setattr(
            deploy_selfcheck,
            "_http_get",
            lambda _url: (200, json.dumps(payload).encode("utf-8")),
        )

    serve(
        {
            "conversation_lifecycle_axis": True,
            "conversation_lifecycle_schema_witnesses": witnesses,
        }
    )
    assert deploy_selfcheck.check_live_conversation_lifecycle_generation(
        "http://new-api"
    ).ok is True

    for invalid_axis in (1, "true", None):
        serve(
            {
                "conversation_lifecycle_axis": invalid_axis,
                "conversation_lifecycle_schema_witnesses": witnesses,
            }
        )
        assert deploy_selfcheck.check_live_conversation_lifecycle_generation(
            "http://old-api"
        ).ok is False

    missing = dict(witnesses)
    missing["persisted_event_chains"] = False
    serve(
        {
            "conversation_lifecycle_axis": True,
            "conversation_lifecycle_schema_witnesses": missing,
        }
    )
    assert deploy_selfcheck.check_live_conversation_lifecycle_generation(
        "http://broken-api"
    ).ok is False


def test_main_and_selfcheck_share_the_exact_lifecycle_witness_contract() -> None:
    from backend.app import main as main_mod

    assert (
        main_mod._conversation_lifecycle_schema_witnesses
        is conversation_lifecycle_schema_witnesses
    )
    assert (
        deploy_selfcheck._conversation_lifecycle_schema_witnesses
        is conversation_lifecycle_schema_witnesses
    )
    assert set(deploy_selfcheck._CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_LABELS) == set(
        CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
    )
