"""版本化 DAG 来源绑定的持久化契约（invalid/legacy first）。

本文件只覆盖仓储与 File API 的不可变证据基础；会话创建重放冲突与 DAG
编译语义由上层服务测试负责。
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from jsonschema import ValidationError, validate

from backend.app.config import CONTRACTS_DIR
from backend.app.storage import db as db_mod
from backend.app.storage import repos
from conftest import TEST_USERNAME


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "source-binding.db"
    db_mod.init_db(db_path)
    connection = db_mod.get_conn(db_path)
    yield connection
    connection.close()


def _source_binding(*, file_id: str = "file-source-1") -> dict:
    return {
        "version": "task_source.v1",
        "graph_digest": "a" * 64,
        "node_id": "prepare",
        "request_id": "request-source-001",
        "params": {
            "kind": "current_turn_json",
            "json_pointer": "/inputs_by_agent/control_logic_agent",
            "value_digest": "b" * 64,
        },
        "attachments": [
            {
                "slot": "input_file_ids",
                "file_id": file_id,
                "conversation_id": "conversation-source-1",
                "uploaded_by_username": "alice",
                "sha256": "c" * 64,
                "classification": "internal",
                "kind": "input",
                "task_id": None,
            }
        ],
    }


def _create_task(conn: sqlite3.Connection, *, task_id: str, source_binding=None):
    return repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="来源绑定测试",
        created_by="Alice",
        created_by_username="alice",
        source_binding=source_binding,
    )


def test_fresh_schema_has_nullable_source_identity_columns_and_partial_unique_index(
    conn: sqlite3.Connection,
) -> None:
    file_cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(files)")}
    task_cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(tasks)")}
    conversation_cols = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(conversations)")
    }

    assert file_cols["uploaded_by_username"]["notnull"] == 0
    assert task_cols["source_binding_json"]["notnull"] == 0
    assert conversation_cols["creation_request_id"]["notnull"] == 0

    index = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' "
        "AND name='uq_conversations_owner_creation_request'"
    ).fetchone()
    assert index is not None
    normalized = " ".join(index["sql"].split()).lower()
    assert "unique index" in normalized
    assert "(created_by_username, creation_request_id)" in normalized
    assert "where creation_request_id is not null" in normalized


def test_legacy_rows_migrate_with_source_identity_columns_left_null(tmp_path) -> None:
    db_path = tmp_path / "legacy-source-binding.db"
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.executescript(
            """
            CREATE TABLE files (
                id TEXT PRIMARY KEY, task_id TEXT, kind TEXT NOT NULL,
                filename TEXT NOT NULL, path TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                classification TEXT NOT NULL DEFAULT 'internal', uploaded_by TEXT
            );
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, agent_version TEXT NOT NULL,
                name TEXT, status TEXT NOT NULL, created_by TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, started_at TEXT,
                finished_at TEXT, input_file_ids TEXT NOT NULL DEFAULT '[]',
                output_file_ids TEXT NOT NULL DEFAULT '[]', inputs_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
                conversation_id TEXT, origin TEXT NOT NULL DEFAULT 'user',
                data_classification TEXT, depends_on TEXT, input_binding TEXT,
                created_by_username TEXT
            );
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, status TEXT NOT NULL,
                created_by TEXT NOT NULL, created_by_username TEXT,
                recommendation_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO files VALUES (
                'legacy-file', NULL, 'input', 'legacy.txt', '/tmp/legacy.txt', 1,
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                '2026-01-01T00:00:00+00:00', 'internal', 'Legacy Display'
            );
            INSERT INTO tasks (
                id, agent_id, agent_version, name, status, created_by, created_at, updated_at
            ) VALUES (
                'legacy-task', 'hello_agent', '0.1.0', 'legacy', 'created', 'Legacy Display',
                '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            );
            INSERT INTO conversations VALUES (
                'legacy-conversation', 'guide_agent', 'active', 'Legacy Display', NULL,
                NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            );
            """
        )
    finally:
        legacy.close()

    db_mod.init_db(db_path)
    db_mod.init_db(db_path)
    migrated = db_mod.get_conn(db_path)
    try:
        assert repos.get_file(migrated, "legacy-file")["uploaded_by_username"] is None
        assert repos.get_task(migrated, "legacy-task")["source_binding"] is None
        assert (
            repos.get_conversation(migrated, "legacy-conversation")["creation_request_id"]
            is None
        )
    finally:
        migrated.close()


def test_create_file_roundtrips_immutable_uploader_username_and_evidence(
    conn: sqlite3.Connection,
) -> None:
    created = repos.create_file(
        conn,
        file_id="file-source-1",
        kind="input",
        filename="source.txt",
        path="/tmp/source.txt",
        size_bytes=7,
        sha256="c" * 64,
        classification="internal",
        uploaded_by="Alice Display",
        uploaded_by_username="alice",
    )

    assert {
        key: created[key]
        for key in (
            "id",
            "kind",
            "task_id",
            "sha256",
            "classification",
            "uploaded_by_username",
        )
    } == {
        "id": "file-source-1",
        "kind": "input",
        "task_id": None,
        "sha256": "c" * 64,
        "classification": "internal",
        "uploaded_by_username": "alice",
    }
    assert repos.get_file(conn, "file-source-1") == created
    assert repos.list_files_by_ids(conn, ["file-source-1"]) == [created]


def test_upload_file_records_authenticated_username(app_env) -> None:
    client, _app = app_env
    response = client.post(
        "/api/files/upload",
        files={"file": ("source.txt", b"payload", "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["uploaded_by_username"] == TEST_USERNAME


def test_create_task_roundtrips_versioned_source_binding_and_task_schema(
    conn: sqlite3.Connection,
) -> None:
    binding = _source_binding()
    task = _create_task(conn, task_id="task-source-1", source_binding=binding)

    assert task["source_binding"] == binding
    assert repos.get_task(conn, task["id"])["source_binding"] == binding

    schema = json.loads((CONTRACTS_DIR / "task.schema.json").read_text(encoding="utf-8"))
    validate(task, schema)
    legacy_payload = dict(task)
    legacy_payload.pop("source_binding")
    validate(legacy_payload, schema)


def test_create_task_source_binding_defaults_to_none(conn: sqlite3.Connection) -> None:
    task = _create_task(conn, task_id="task-source-none")
    assert task["source_binding"] is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda binding: binding.update(version="task_source.v2"),
        lambda binding: binding.pop("params"),
        lambda binding: binding["attachments"][0].update(untrusted_extra=True),
        lambda binding: binding["attachments"][0].update(classification="sensitive"),
        lambda binding: binding["attachments"][0].update(kind="output"),
        lambda binding: binding["attachments"][0].update(task_id="already-owned"),
    ],
    ids=[
        "unknown-version",
        "missing-params",
        "attachment-extra-field",
        "sensitive-attachment",
        "output-attachment",
        "owned-attachment",
    ],
)
def test_task_schema_rejects_noncanonical_source_binding(
    conn: sqlite3.Connection, mutate
) -> None:
    task = _create_task(
        conn, task_id=f"task-invalid-{mutate.__name__}", source_binding=_source_binding()
    )
    mutate(task["source_binding"])
    schema = json.loads((CONTRACTS_DIR / "task.schema.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        validate(task, schema)


def test_conversation_creation_request_roundtrip_lookup_and_partial_uniqueness(
    conn: sqlite3.Connection,
) -> None:
    created = repos.create_conversation(
        conn,
        conversation_id="conversation-create-1",
        agent_id="guide_agent",
        created_by="Alice",
        created_by_username="alice",
        creation_request_id="creation-request-001",
    )
    assert created["creation_request_id"] == "creation-request-001"
    assert repos.get_conversation_by_creation_request(
        conn,
        created_by_username="alice",
        creation_request_id="creation-request-001",
    ) == created

    with pytest.raises(sqlite3.IntegrityError):
        repos.create_conversation(
            conn,
            conversation_id="conversation-create-conflict",
            agent_id="guide_agent",
            created_by="Alice",
            created_by_username="alice",
            creation_request_id="creation-request-001",
        )

    other_owner = repos.create_conversation(
        conn,
        conversation_id="conversation-create-other-owner",
        agent_id="guide_agent",
        created_by="Bob",
        created_by_username="bob",
        creation_request_id="creation-request-001",
    )
    assert other_owner["creation_request_id"] == "creation-request-001"

    for suffix in ("a", "b"):
        legacy = repos.create_conversation(
            conn,
            conversation_id=f"conversation-without-key-{suffix}",
            agent_id="guide_agent",
            created_by="Alice",
            created_by_username="alice",
        )
        assert legacy["creation_request_id"] is None
