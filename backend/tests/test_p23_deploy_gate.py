"""P2.3 deployment witnesses: live code generation and SQLite schema shape.

These checks deliberately witness only code/schema presence.  They do not infer
that historical rows have an owner or that any Question has been answered.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.storage import db as db_mod
from backend.app.storage import p23_schema
from backend.app.storage import repos
from scripts import deploy_selfcheck


_P23_WITNESS_KEYS = {
    "conversation_table_shape",
    "message_table_shape",
    "question_table_shape",
    "required_indexes",
    "required_triggers",
}
_P23_REQUIRED_INDEX_NAMES = (
    "idx_conversations_created_by_username",
    "idx_conversation_messages_conversation_id",
    "idx_conversation_messages_message_id",
    "idx_conversation_questions_conversation_id",
    "idx_conversation_questions_prompt_message_id",
    "idx_conversation_questions_one_unresolved",
    "idx_conversation_questions_answer_message_id",
    "idx_conversation_questions_response_message_id",
)
_P23_REQUIRED_TRIGGER_NAMES = (
    "trg_conversations_id_required",
    "trg_conversations_lifecycle_initial_state",
    "trg_conversations_owner_immutable",
    "trg_conversations_no_conflicting_insert",
    "trg_conversations_identity_immutable",
    "trg_conversations_no_delete",
    "trg_conversations_no_conflicting_insert_v2",
    "trg_conversations_positive_rowid",
    "trg_conversations_lifecycle_event_required",
    "trg_conversation_messages_public_id_required",
    "trg_conversation_messages_no_update",
    "trg_conversation_messages_no_delete",
    "trg_conversation_messages_no_conflicting_insert",
    "trg_conversation_messages_positive_internal_id",
    "trg_conversation_questions_public_id_required",
    "trg_conversation_questions_timestamp_canonical",
    "trg_conversation_questions_ttl_24h",
    "trg_conversation_questions_owner_exact",
    "trg_conversation_questions_initially_unresolved",
    "trg_conversation_questions_prompt_message",
    "trg_conversation_questions_spec_immutable",
    "trg_conversation_questions_rowid_immutable",
    "trg_conversation_questions_positive_rowid",
    "trg_conversation_questions_resolution_once",
    "trg_conversation_questions_answer_refs_unique",
    "trg_conversation_questions_answer_messages",
    "trg_conversation_questions_answer_before_expiry",
    "trg_conversation_questions_resolution_timestamp",
    "trg_conversation_questions_no_delete",
    "trg_conversation_questions_no_conflicting_insert",
    "trg_conversation_questions_no_conflicting_insert_v2",
)


def _fake_health(monkeypatch, payload: dict[str, object]) -> None:
    def fake_get(_url: str) -> tuple[int, bytes]:
        return 200, json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(deploy_selfcheck, "_http_get", fake_get)


def _fresh_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "p23-deploy.db"
    db_mod.init_db(db_path)
    return db_path


def _replace_trigger_with_noop(conn: sqlite3.Connection, trigger_name: str) -> None:
    row = conn.execute(
        "SELECT tbl_name FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()
    assert row is not None, f"missing fixture trigger {trigger_name}"
    table = row[0]
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(
        f'CREATE TRIGGER "{trigger_name}" BEFORE INSERT ON "{table}" '
        "BEGIN SELECT 1; END"
    )


def _rebuild_question_table(
    conn: sqlite3.Connection, replace: tuple[str, str]
) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'conversation_questions'"
    ).fetchone()
    assert row is not None
    original_sql = str(row[0])
    old, new = replace
    assert old in original_sql, f"canonical table fragment drifted: {old}"
    mutated_sql = original_sql.replace(old, new, 1)

    conn.execute("DROP TABLE conversation_questions")
    conn.execute(mutated_sql)
    for statement in db_mod._INDEX_DDL:
        conn.execute(statement)


def _rebuild_message_table(
    conn: sqlite3.Connection, replace: tuple[str, str]
) -> None:
    message_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'conversation_messages'"
    ).fetchone()
    question_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'conversation_questions'"
    ).fetchone()
    assert message_row is not None and question_row is not None
    old, new = replace
    message_sql = str(message_row[0])
    assert old in message_sql

    conn.execute("DROP TABLE conversation_questions")
    conn.execute("DROP TABLE conversation_messages")
    conn.execute(message_sql.replace(old, new, 1))
    conn.execute(str(question_row[0]))
    for statement in db_mod._INDEX_DDL:
        conn.execute(statement)


def _rebuild_conversation_table(
    conn: sqlite3.Connection, replace: tuple[str, str]
) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'conversations'"
    ).fetchone()
    assert row is not None
    original_sql = str(row[0])
    old, new = replace
    assert old in original_sql, f"canonical table fragment drifted: {old}"

    assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    conn.execute("DROP TABLE conversations")
    conn.execute(original_sql.replace(old, new, 1))
    for statement in db_mod._INDEX_DDL:
        conn.execute(statement)


def test_pre_p23_live_api_marker_fails_even_with_older_username_axis(monkeypatch) -> None:
    """The pre-P2.3 owner marker must never stand in for structured Questions."""
    _fake_health(
        monkeypatch,
        {
            "status": "ok",
            "classification_axis": True,
            "created_by_username_axis": True,
            "eval_snapshot_axis": True,
        },
    )

    check = deploy_selfcheck.check_live_structured_question_generation("http://old-api")

    assert check.ok is False
    assert "structured_question_axis" in check.detail


def test_live_p23_generation_requires_exact_true_and_all_remote_schema_witnesses(
    monkeypatch,
) -> None:
    valid_witnesses = {key: True for key in _P23_WITNESS_KEYS}
    _fake_health(
        monkeypatch,
        {
            "structured_question_axis": True,
            "p23_schema_witnesses": valid_witnesses,
        },
    )
    assert deploy_selfcheck.check_live_structured_question_generation("http://new-api").ok is True

    for invalid_axis in (1, "true", None):
        _fake_health(
            monkeypatch,
            {
                "structured_question_axis": invalid_axis,
                "p23_schema_witnesses": valid_witnesses,
            },
        )
        assert (
            deploy_selfcheck.check_live_structured_question_generation("http://new-api").ok
            is False
        )

    missing_witness = dict(valid_witnesses)
    missing_witness["required_triggers"] = False
    _fake_health(
        monkeypatch,
        {
            "structured_question_axis": True,
            "p23_schema_witnesses": missing_witness,
        },
    )
    assert deploy_selfcheck.check_live_structured_question_generation("http://new-api").ok is False


def test_local_p23_schema_witness_passes_fresh_schema_without_claiming_data(
    tmp_path: Path,
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is True
    assert "schema" in check.detail.lower()
    assert "data" in check.detail.lower()


def test_p23_witness_accepts_supported_legacy_message_id_alter_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-message-column-position.db"
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
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                recommendation_json TEXT,
                file_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            INSERT INTO conversations VALUES (
                'conv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'guide_agent',
                'active', '旧用户', NULL,
                '2026-07-19T00:00:00+00:00', '2026-07-19T00:00:00+00:00'
            );
            INSERT INTO conversation_messages (
                conversation_id, role, content, recommendation_json,
                file_ids, created_at
            ) VALUES (
                'conv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'user', '旧消息',
                NULL, '[]', '2026-07-19T00:00:00+00:00'
            );
            """
        )
    finally:
        conn.close()

    db_mod.init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        message_row = next(
            row
            for row in conn.execute("PRAGMA table_xinfo(conversation_messages)")
            if row[1] == "message_id"
        )
        witnesses = p23_schema.p23_schema_witnesses(conn)
    finally:
        conn.close()

    assert message_row[0] != 1, "legacy ALTER appends the public-id column"
    assert witnesses == {key: True for key in _P23_WITNESS_KEYS}


def test_local_p23_schema_witness_rejects_pre_p23_columns_only(tmp_path: Path) -> None:
    db_path = tmp_path / "old-schema.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_by_username TEXT
            );
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                content TEXT NOT NULL
            );
            """
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "conversation_messages identity-critical shape" in check.detail
    assert "conversation_questions" in check.detail


@pytest.mark.parametrize(
    "replacement",
    (
        (
            "revision INTEGER NOT NULL CHECK (revision = 1)",
            "revision TEXT NOT NULL CHECK (revision = 1)",
        ),
        (
            "revision INTEGER NOT NULL CHECK (revision = 1)",
            "revision INTEGER NOT NULL",
        ),
        (
            "response_message_id TEXT,",
            "response_message_id TEXT,\n    unexpected TEXT,",
        ),
    ),
)
def test_local_p23_schema_witness_rejects_noncanonical_question_table_shape(
    tmp_path: Path, replacement: tuple[str, str]
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        _rebuild_question_table(conn, replacement)
        witnesses = p23_schema.p23_schema_witnesses(conn)
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert witnesses["question_table_shape"] is False
    assert witnesses["conversation_table_shape"] is True
    assert witnesses["message_table_shape"] is True
    assert witnesses["required_indexes"] is True
    assert witnesses["required_triggers"] is True
    assert check.ok is False
    assert "canonical table shape" in check.detail


@pytest.mark.parametrize(
    "replacement",
    (
        (
            "message_id TEXT NOT NULL UNIQUE",
            "message_id TEXT NOT NULL DEFAULT 'msg_bad' UNIQUE",
        ),
        (
            "message_id TEXT NOT NULL UNIQUE",
            "message_id TEXT GENERATED ALWAYS AS ('msg_generated') VIRTUAL UNIQUE",
        ),
    ),
)
def test_message_public_id_witness_rejects_defaulted_or_generated_lookalike(
    tmp_path: Path, replacement: tuple[str, str]
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        _rebuild_message_table(conn, replacement)
        witnesses = p23_schema.p23_schema_witnesses(conn)
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert witnesses["message_table_shape"] is False
    assert witnesses["question_table_shape"] is True
    assert check.ok is False
    assert "conversation_messages identity-critical shape" in check.detail


@pytest.mark.parametrize(
    "replacement",
    (
        (
            "created_by_username TEXT,",
            "created_by_username TEXT UNIQUE,",
        ),
        (
            "created_by_username TEXT,",
            "created_by_username TEXT "
            "CHECK (created_by_username IS NULL OR length(created_by_username) = 5),",
        ),
        (
            "created_by_username TEXT,",
            "created_by_username TEXT REFERENCES users(username),",
        ),
        ("id TEXT PRIMARY KEY NOT NULL,", "id TEXT,"),
        (
            "archived_at TEXT\n)",
            "archived_at TEXT\n) STRICT",
        ),
        (
            "archived_at TEXT\n)",
            "archived_at TEXT,\n    CHECK (1 = 1)\n)",
        ),
    ),
)
def test_conversation_table_witness_rejects_hidden_or_core_identity_drift(
    tmp_path: Path, replacement: tuple[str, str]
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        _rebuild_conversation_table(conn, replacement)
        witnesses = p23_schema.p23_schema_witnesses(conn)
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert witnesses["conversation_table_shape"] is False
    assert check.ok is False
    assert "conversations identity-critical shape" in check.detail


@pytest.mark.parametrize(
    "replacement",
    (
        (
            "message_id TEXT NOT NULL UNIQUE,",
            "message_id TEXT NOT NULL UNIQUE REFERENCES users(username),",
        ),
        (
            "message_id TEXT NOT NULL UNIQUE,",
            "message_id TEXT NOT NULL UNIQUE CHECK (length(message_id) = 1),",
        ),
        (
            "id INTEGER PRIMARY KEY AUTOINCREMENT,",
            "id INTEGER,",
        ),
        (
            "conversation_id TEXT NOT NULL,",
            "conversation_id TEXT NOT NULL UNIQUE,",
        ),
    ),
)
def test_message_table_witness_rejects_hidden_or_core_identity_drift(
    tmp_path: Path, replacement: tuple[str, str]
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        _rebuild_message_table(conn, replacement)
        witnesses = p23_schema.p23_schema_witnesses(conn)
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert witnesses["message_table_shape"] is False
    assert check.ok is False
    assert "conversation_messages identity-critical shape" in check.detail


@pytest.mark.parametrize("index_name", _P23_REQUIRED_INDEX_NAMES)
def test_local_p23_schema_witness_rejects_each_missing_required_index(
    tmp_path: Path, index_name: str
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP INDEX {index_name}")
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "index" in check.detail.lower()


def test_local_p23_schema_witness_rejects_wrong_index_columns_or_predicate(
    tmp_path: Path,
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP INDEX idx_conversations_created_by_username")
        conn.execute(
            "CREATE INDEX idx_conversations_created_by_username ON conversations(id)"
        )
        check = deploy_selfcheck.check_p23_schema(conn)
        assert check.ok is False

        conn.execute("DROP INDEX idx_conversations_created_by_username")
        conn.execute(
            "CREATE INDEX idx_conversations_created_by_username "
            "ON conversations(created_by_username)"
        )
        conn.execute("DROP INDEX idx_conversation_questions_one_unresolved")
        conn.execute(
            "CREATE UNIQUE INDEX idx_conversation_questions_one_unresolved "
            "ON conversation_questions(conversation_id, asked_to_username) "
            "WHERE closed_reason IS NOT NULL"
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "index" in check.detail.lower()


@pytest.mark.parametrize("trigger_name", _P23_REQUIRED_TRIGGER_NAMES)
def test_local_p23_schema_witness_rejects_each_missing_required_trigger(
    tmp_path: Path, trigger_name: str
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP TRIGGER {trigger_name}")
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "trigger" in check.detail.lower()


@pytest.mark.parametrize("trigger_name", _P23_REQUIRED_TRIGGER_NAMES)
def test_local_p23_schema_witness_rejects_each_same_name_same_table_noop_trigger(
    tmp_path: Path, trigger_name: str
) -> None:
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        _replace_trigger_with_noop(conn, trigger_name)
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "trigger" in check.detail.lower()


def test_main_and_selfcheck_share_one_p23_schema_witness_contract() -> None:
    from backend.app import main as main_mod

    assert main_mod._p23_schema_witnesses is p23_schema.p23_schema_witnesses
    assert deploy_selfcheck._p23_schema_witnesses is p23_schema.p23_schema_witnesses
    assert set(deploy_selfcheck._P23_SCHEMA_WITNESS_LABELS) == set(
        p23_schema.P23_SCHEMA_WITNESS_KEYS
    )
    assert set(_P23_REQUIRED_TRIGGER_NAMES) == set(
        p23_schema.p23_required_trigger_names()
    )
    assert set(_P23_REQUIRED_INDEX_NAMES) == set(
        p23_schema.p23_required_index_names()
    )


def test_offline_probe_and_shared_schema_contract_load_with_stdlib_only() -> None:
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from scripts import deploy_selfcheck; "
            "from backend.app.storage import p23_schema; "
            "assert len(p23_schema.p23_required_trigger_names()) == 31; "
            "assert len(p23_schema.p23_required_index_names()) == 8; "
            "assert deploy_selfcheck._p23_schema_witnesses "
            "is p23_schema.p23_schema_witnesses",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_health_reports_p23_generation_and_actual_schema_witnesses(app_env) -> None:
    client, _app = app_env

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["structured_question_axis"] is True
    witnesses = body["p23_schema_witnesses"]
    assert set(witnesses) == _P23_WITNESS_KEYS
    assert all(value is True for value in witnesses.values())


def test_unknown_trigger_on_p23_table_fails_closed_until_explicitly_managed(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        conn.execute(
            "CREATE TRIGGER trg_future_conversation_metadata "
            "AFTER UPDATE ON conversations BEGIN SELECT 1; END"
        )
        assert deploy_selfcheck.check_p23_schema(conn).ok is False
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["p23_schema_witnesses"]["required_triggers"] is False
    assert client.get("/api/readyz").status_code == 503


def test_unknown_future_column_fails_until_explicitly_registered(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        _rebuild_conversation_table(
            conn,
            (
                "created_by_username TEXT,",
                "created_by_username TEXT,\n    future_metadata TEXT,",
            ),
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "conversations identity-critical shape" in check.detail
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["p23_schema_witnesses"]["conversation_table_shape"] is False
    assert client.get("/api/readyz").status_code == 503


def test_unknown_unique_index_on_future_column_still_fails_closed(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        _rebuild_conversation_table(
            conn,
            (
                "created_by_username TEXT,",
                "created_by_username TEXT,\n    future_metadata TEXT,",
            ),
        )
        conn.execute(
            "CREATE UNIQUE INDEX idx_future_unique_metadata "
            "ON conversations(future_metadata) "
            "WHERE future_metadata IS NOT NULL"
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "required indexes" in check.detail
    assert client.get("/api/health").json()["p23_schema_witnesses"][
        "required_indexes"
    ] is False
    assert client.get("/api/readyz").status_code == 503


def test_unknown_nonunique_expression_index_fails_closed(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        conn.execute(
            "CREATE INDEX idx_owner_json_expression_drift "
            "ON conversations(json_extract(created_by_username, '$'))"
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "required indexes" in check.detail
    assert client.get("/api/health").json()["p23_schema_witnesses"][
        "required_indexes"
    ] is False
    assert client.get("/api/readyz").status_code == 503


def test_post_start_owner_unique_index_fails_all_deployment_witnesses(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        conn.execute(
            "CREATE UNIQUE INDEX idx_owner_singleton_drift "
            "ON conversations(created_by_username) "
            "WHERE created_by_username IS NOT NULL"
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "conversations identity-critical shape" in check.detail
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["p23_schema_witnesses"]["conversation_table_shape"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["p23"]["schema_ready"] is False


def test_post_start_hidden_message_check_fails_all_deployment_witnesses(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        _rebuild_message_table(
            conn,
            (
                "message_id TEXT NOT NULL UNIQUE,",
                "message_id TEXT NOT NULL UNIQUE "
                "CHECK (length(message_id) = 1),",
            ),
        )
        check = deploy_selfcheck.check_p23_schema(conn)
    finally:
        conn.close()

    assert check.ok is False
    assert "conversation_messages identity-critical shape" in check.detail
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["p23_schema_witnesses"]["message_table_shape"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["p23"]["schema_ready"] is False


def test_readyz_fails_closed_when_p23_schema_witness_breaks(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        conn.execute("DROP TRIGGER trg_conversation_questions_spec_immutable")
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["structured_question_axis"] is True
    assert health.json()["p23_schema_witnesses"]["required_triggers"] is False

    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    payload = ready.json()
    assert payload["status"] == "degraded"
    assert payload["structured_question_axis"] is True
    assert payload["p23"]["runtime_generation"] is True
    assert payload["p23"]["schema_ready"] is False


def test_health_and_readyz_fail_closed_for_same_name_same_table_noop_trigger(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        _replace_trigger_with_noop(
            conn, "trg_conversation_questions_spec_immutable"
        )
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["p23_schema_witnesses"]["required_triggers"] is False

    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["p23"]["schema_ready"] is False


def test_health_readyz_and_selfcheck_fail_for_question_table_missing_check(
    app_env,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation=deploy_selfcheck.WORKER_GENERATION)
        _rebuild_question_table(
            conn,
            (
                "revision INTEGER NOT NULL CHECK (revision = 1)",
                "revision INTEGER NOT NULL",
            ),
        )
        assert deploy_selfcheck.check_p23_schema(conn).ok is False
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["p23_schema_witnesses"]["question_table_shape"] is False

    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["p23"]["schema_ready"] is False
