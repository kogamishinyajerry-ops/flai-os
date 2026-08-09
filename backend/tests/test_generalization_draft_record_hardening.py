"""Adversarial evidence for Issue #75's exact R2 draft-record contract.

These tests intentionally exercise public runtime seams and a real SQLite file.
Migration fault tests wrap the connection returned to ``init_db`` so failures can
be injected after SQLite has executed a stage, without adding production hooks.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Mapping

import pytest

from backend.app.runtime.generalization_draft_record import (
    GeneralizationDraftPayloadError,
    GeneralizationDraftRecordIntegrityError,
    create_generalization_draft_record,
    load_verified_generalization_draft_record,
    normalize_generalization_draft_payload,
    project_conversation_messages,
)
from backend.app.storage import db as db_module
from backend.app.storage import repos
from backend.app.storage.db import (
    DatabaseSchemaIntegrityError,
    get_conn,
    init_db,
)


_RECORD_COLUMNS = (
    "id",
    "schema_version",
    "payload_schema_version",
    "state",
    "review_status",
    "payload_json",
    "content_digest",
    "record_digest",
    "source_context_json",
    "source_context_digest",
    "conversation_id",
    "owner_username",
    "source_user_message_id",
    "source_assistant_message_id",
    "source_task_id",
    "model_call_id",
    "model_call_kind",
    "model_profile",
    "model_name",
    "model_agent_id",
    "agent_version",
    "created_at",
)


def _payload(**changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Cafe\u0301  检查",
        "trigger": "收到试验异常",
        "desired_outcome": "形成可复核结论",
        "inputs": ["试验记录"],
        "outputs": ["检查说明"],
        "steps": ["核对来源", "形成草稿"],
        "evidence_requirements": ["原始记录位置"],
        "human_decision_points": ["工程师复核"],
        "limitations": ["不得替代签发"],
    }
    payload.update(changes)
    return payload


def _create_conversation(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    owner_username: str = "owner",
    agent_id: str = "life_guide_agent",
) -> None:
    repos.create_conversation(
        conn,
        conversation_id=conversation_id,
        agent_id=agent_id,
        created_by="Owner",
        created_by_username=owner_username,
    )


def _append_round(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    suffix: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    user = repos.append_message(
        conn,
        conversation_id=conversation_id,
        role="user",
        content=f"一次真实工作{suffix}",
    )
    assistant = repos.append_message(
        conn,
        conversation_id=conversation_id,
        role="assistant",
        content=f"已形成待审草稿{suffix}",
    )
    return user, assistant


def _record_call(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    status: str = "success",
    model_name: str = "test-model",
    agent_id: str = "life_guide_agent",
) -> dict[str, Any]:
    return repos.record_model_call(
        conn,
        conversation_id=conversation_id,
        agent_id=agent_id,
        model_profile="deep_reasoning",
        model_name=model_name,
        status=status,
    )


def _receipt(row: Mapping[str, Any], *, kind: str = "chat") -> dict[str, Any]:
    return {
        "model_call_id": row["id"],
        "kind": kind,
        "status": row["status"],
        "task_id": row["task_id"],
        "conversation_id": row["conversation_id"],
        "agent_id": row["agent_id"],
        "model_profile": row["model_profile"],
        "model_name": row["model_name"],
    }


def _create_record_fixture(
    db_path: Path,
    *,
    conversation_id: str = "conv_hardening",
) -> tuple[sqlite3.Connection, dict[str, Any], dict[str, Any]]:
    init_db(db_path)
    conn = get_conn(db_path)
    _create_conversation(conn, conversation_id)
    user, assistant = _append_round(conn, conversation_id)
    call = _record_call(conn, conversation_id)
    conn.execute("BEGIN IMMEDIATE")
    record = create_generalization_draft_record(
        conn,
        payload=_payload(),
        conversation_id=conversation_id,
        owner_username="owner",
        source_user_message_id=user["id"],
        source_assistant_message_id=assistant["id"],
        model_call_receipt=_receipt(call),
        agent_version="1.0.0",
    )
    conn.execute("COMMIT")
    return conn, record, {"user": user, "assistant": assistant, "call": call}


def _raw_record(
    *,
    conversation_id: str,
    user_message_id: int,
    assistant_message_id: int,
    model_call_id: int,
    marker: str = "a",
) -> dict[str, Any]:
    return {
        "id": f"gdr_{marker * 32}",
        "schema_version": "generalization_draft_record.v1",
        "payload_schema_version": "life_generalization.v1",
        "state": "model_draft",
        "review_status": "waiting_review",
        "payload_json": '{"title":"raw"}',
        "content_digest": f"sha256:{marker * 64}",
        "record_digest": f"sha256:{marker * 64}",
        "source_context_json": '{"source":"raw"}',
        "source_context_digest": f"sha256:{marker * 64}",
        "conversation_id": conversation_id,
        "owner_username": "owner",
        "source_user_message_id": user_message_id,
        "source_assistant_message_id": assistant_message_id,
        "source_task_id": None,
        "model_call_id": model_call_id,
        "model_call_kind": "chat",
        "model_profile": "deep_reasoning",
        "model_name": "test-model",
        "model_agent_id": "life_guide_agent",
        "agent_version": "1.0.0",
        "created_at": "2026-08-09T00:00:00+00:00",
    }


def _raw_insert(conn: sqlite3.Connection, record: Mapping[str, Any]) -> None:
    columns = ", ".join(_RECORD_COLUMNS)
    placeholders = ", ".join("?" for _ in _RECORD_COLUMNS)
    conn.execute(
        f"INSERT INTO generalization_draft_records ({columns}) "
        f"VALUES ({placeholders})",
        tuple(record[column] for column in _RECORD_COLUMNS),
    )


def _raw_parent_set(
    conn: sqlite3.Connection,
    *,
    conversation_id: str = "conv_raw",
    suffix: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if repos.get_conversation(conn, conversation_id) is None:
        _create_conversation(conn, conversation_id)
    user, assistant = _append_round(conn, conversation_id, suffix=suffix)
    call = _record_call(conn, conversation_id, model_name=f"test-model{suffix}")
    return user, assistant, call


def _schema_sql(db_path: Path, object_name: str) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?", (object_name,)
        ).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def test_fresh_init_installs_ledger_only_inside_locked_migration(tmp_path) -> None:
    db_path = tmp_path / "fresh.sqlite3"
    assert "generalization_draft_records" not in db_module._DDL

    init_db(db_path)

    conn = get_conn(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 0
        assert {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name = 'generalization_draft_records' "
                "OR name LIKE 'trg_generalization_draft_records_%' "
                "OR name LIKE 'idx_generalization_draft_records_%'"
            ).fetchall()
        } == {
            "generalization_draft_records",
            "trg_generalization_draft_records_no_update",
            "trg_generalization_draft_records_no_delete",
            "idx_generalization_draft_records_conversation_message",
            "idx_generalization_draft_records_source_task",
        }
    finally:
        conn.close()


def test_legacy_init_adds_exact_empty_ledger_without_backfill(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    legacy = sqlite3.connect(db_path)
    try:
        legacy.executescript(db_module._DDL)
        legacy.execute(
            "INSERT INTO conversations "
            "(id, agent_id, status, created_by, created_by_username, created_at, updated_at) "
            "VALUES ('legacy_conv', 'life_guide_agent', 'active', 'Owner', 'owner', "
            "'2026-08-09T00:00:00+00:00', '2026-08-09T00:00:00+00:00')"
        )
        legacy.execute(
            "INSERT INTO conversation_messages "
            "(conversation_id, role, content, file_ids, created_at) "
            "VALUES ('legacy_conv', 'assistant', '历史 response-only 草稿', '[]', "
            "'2026-08-09T00:00:00+00:00')"
        )
        legacy.commit()
    finally:
        legacy.close()

    init_db(db_path)

    conn = get_conn(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT content FROM conversation_messages"
        ).fetchone()[0] == "历史 response-only 草稿"
    finally:
        conn.close()


def test_init_is_idempotent_and_preserves_existing_record(tmp_path) -> None:
    db_path = tmp_path / "idempotent.sqlite3"
    conn, record, _parents = _create_record_fixture(db_path)
    conn.close()
    before = _schema_sql(db_path, "generalization_draft_records")

    init_db(db_path)
    init_db(db_path)

    assert _schema_sql(db_path, "generalization_draft_records") == before
    conn = get_conn(db_path)
    try:
        assert [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM generalization_draft_records"
            ).fetchall()
        ] == [record["id"]]
    finally:
        conn.close()


def test_get_conn_retries_short_wal_transition_lock(tmp_path) -> None:
    db_path = tmp_path / "wal-transition-lock.sqlite3"
    holder_ready = Event()
    release_holder = Event()
    contender_started = Event()

    def hold_pre_wal_write_lock() -> None:
        conn = sqlite3.connect(db_path, isolation_level=None)
        try:
            conn.execute("CREATE TABLE seed(id INTEGER)")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO seed VALUES (1)")
            holder_ready.set()
            assert release_holder.wait(timeout=5)
            conn.execute("ROLLBACK")
        finally:
            conn.close()

    def open_and_close_contender() -> None:
        contender_started.set()
        conn = get_conn(db_path)
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        finally:
            conn.close()

    holder = Thread(target=hold_pre_wal_write_lock)
    holder.start()
    assert holder_ready.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        contender = pool.submit(open_and_close_contender)
        assert contender_started.wait(timeout=5)
        time.sleep(0.05)
        release_holder.set()
        contender.result(timeout=5)

    holder.join(timeout=5)
    assert not holder.is_alive()


def test_concurrent_init_installs_one_exact_schema(tmp_path) -> None:
    db_path = tmp_path / "concurrent.sqlite3"

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(init_db, db_path) for _ in range(16)]
        for future in futures:
            future.result(timeout=20)

    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name = 'generalization_draft_records' "
            "OR name LIKE 'trg_generalization_draft_records_%' "
            "OR name LIKE 'idx_generalization_draft_records_%'"
        ).fetchall()
    finally:
        conn.close()
    assert {(row["type"], row["name"]) for row in rows} == {
        ("table", "generalization_draft_records"),
        ("trigger", "trg_generalization_draft_records_no_update"),
        ("trigger", "trg_generalization_draft_records_no_delete"),
        ("index", "idx_generalization_draft_records_conversation_message"),
        ("index", "idx_generalization_draft_records_source_task"),
    }


@pytest.mark.parametrize("weak_object", ["table", "trigger", "index"])
def test_init_rejects_and_never_repairs_weak_same_name_object(
    tmp_path, weak_object: str
) -> None:
    db_path = tmp_path / f"weak-{weak_object}.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        if weak_object == "table":
            conn.execute("DROP TRIGGER trg_generalization_draft_records_no_update")
            conn.execute("DROP TRIGGER trg_generalization_draft_records_no_delete")
            conn.execute("DROP TABLE generalization_draft_records")
            weak_ddl = db_module._GENERALIZATION_DRAFT_RECORD_TABLE_DDL.replace(
                "CHECK (state = 'model_draft')",
                "CHECK (state IN ('model_draft', 'approved'))",
            )
            conn.execute(weak_ddl)
            object_name = "generalization_draft_records"
        elif weak_object == "trigger":
            object_name = "trg_generalization_draft_records_no_update"
            conn.execute(f"DROP TRIGGER {object_name}")
            conn.execute(
                f"CREATE TRIGGER {object_name} BEFORE UPDATE OF created_at "
                "ON generalization_draft_records BEGIN SELECT 1; END"
            )
        else:
            object_name = "idx_generalization_draft_records_conversation_message"
            conn.execute(f"DROP INDEX {object_name}")
            conn.execute(
                f"CREATE INDEX {object_name} "
                "ON generalization_draft_records(conversation_id)"
            )
    finally:
        conn.close()
    weak_sql = _schema_sql(db_path, object_name)

    with pytest.raises(DatabaseSchemaIntegrityError):
        init_db(db_path)

    assert _schema_sql(db_path, object_name) == weak_sql


class _FailAfterStageConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        predicate: Callable[[str], bool],
    ) -> None:
        self._connection = connection
        self._predicate = predicate
        self._failed = False

    def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
        cursor = self._connection.execute(sql, *args)
        if not self._failed and self._predicate(" ".join(sql.split())):
            self._failed = True
            raise RuntimeError("injected migration stage failure")
        return cursor

    def executescript(self, sql: str) -> sqlite3.Cursor:
        return self._connection.executescript(sql)

    def close(self) -> None:
        self._connection.close()


@pytest.mark.parametrize(
    "stage,predicate",
    [
        (
            "table",
            lambda sql: sql.startswith(
                "CREATE TABLE IF NOT EXISTS generalization_draft_records"
            ),
        ),
        (
            "trigger",
            lambda sql: sql.startswith(
                "CREATE TRIGGER IF NOT EXISTS trg_generalization_draft_records_no_update"
            ),
        ),
        (
            "index",
            lambda sql: "idx_generalization_draft_records_conversation_message"
            in sql,
        ),
        (
            "audit",
            lambda sql: sql.startswith(
                "SELECT type, name, tbl_name, sql FROM sqlite_master"
            ),
        ),
    ],
)
def test_migration_stage_failure_rolls_back_every_draft_schema_object(
    tmp_path, monkeypatch, stage: str, predicate: Callable[[str], bool]
) -> None:
    db_path = tmp_path / f"fail-{stage}.sqlite3"
    real_connection = get_conn(db_path)
    proxy = _FailAfterStageConnection(real_connection, predicate)
    monkeypatch.setattr(db_module, "get_conn", lambda _path: proxy)

    with pytest.raises(RuntimeError, match="injected migration stage failure"):
        init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name = 'generalization_draft_records' "
                "OR name LIKE 'trg_generalization_draft_records_%' "
                "OR name LIKE 'idx_generalization_draft_records_%'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert names == set()


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("id", "gdr_" + "A" * 32),
        ("schema_version", "generalization_draft_record.v2"),
        ("payload_schema_version", "life_generalization.v2"),
        ("state", "approved"),
        ("review_status", "approved"),
        ("payload_json", "[]"),
        ("content_digest", "sha256:" + "G" * 64),
        ("record_digest", "sha256:" + "G" * 64),
        ("source_context_json", "[]"),
        ("source_context_digest", "sha256:" + "G" * 64),
        ("conversation_id", "missing-conversation"),
        ("owner_username", ""),
        ("owner_username", "o" * 129),
        ("source_user_message_id", 999_991),
        ("source_assistant_message_id", 999_992),
        ("source_task_id", "must-stay-null"),
        ("model_call_id", 999_993),
        ("model_call_kind", "vision"),
        ("model_profile", "  "),
        ("model_name", "  "),
        ("model_agent_id", "  "),
        ("agent_version", "  "),
        ("created_at", "  "),
        ("source_assistant_message_id", "same-as-user"),
    ],
)
def test_sqlite_rejects_every_invalid_check_or_parent_binding(
    tmp_path, field: str, bad_value: Any
) -> None:
    db_path = tmp_path / "constraint.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        user, assistant, call = _raw_parent_set(conn)
        record = _raw_record(
            conversation_id="conv_raw",
            user_message_id=user["id"],
            assistant_message_id=assistant["id"],
            model_call_id=call["id"],
        )
        record[field] = user["id"] if bad_value == "same-as-user" else bad_value
        with pytest.raises(sqlite3.IntegrityError):
            _raw_insert(conn, record)
    finally:
        conn.close()


@pytest.mark.parametrize(
    "unique_field",
    [
        "id",
        "record_digest",
        "source_user_message_id",
        "source_assistant_message_id",
        "model_call_id",
    ],
)
def test_sqlite_rejects_every_exact_unique_binding(
    tmp_path, unique_field: str
) -> None:
    db_path = tmp_path / "unique.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        user1, assistant1, call1 = _raw_parent_set(conn, suffix="-1")
        user2, assistant2, call2 = _raw_parent_set(conn, suffix="-2")
        first = _raw_record(
            conversation_id="conv_raw",
            user_message_id=user1["id"],
            assistant_message_id=assistant1["id"],
            model_call_id=call1["id"],
            marker="a",
        )
        second = _raw_record(
            conversation_id="conv_raw",
            user_message_id=user2["id"],
            assistant_message_id=assistant2["id"],
            model_call_id=call2["id"],
            marker="b",
        )
        _raw_insert(conn, first)
        second[unique_field] = first[unique_field]
        with pytest.raises(sqlite3.IntegrityError):
            _raw_insert(conn, second)
    finally:
        conn.close()


def test_sqlite_enforces_all_five_foreign_keys(tmp_path) -> None:
    db_path = tmp_path / "foreign-keys.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        actual = {
            (row["table"], row["from"], row["to"])
            for row in conn.execute(
                "PRAGMA foreign_key_list(generalization_draft_records)"
            ).fetchall()
        }
    finally:
        conn.close()
    assert actual == {
        ("conversations", "conversation_id", "id"),
        ("conversation_messages", "source_user_message_id", "id"),
        ("conversation_messages", "source_assistant_message_id", "id"),
        ("tasks", "source_task_id", "id"),
        ("model_calls", "model_call_id", "id"),
    }


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_immutable_triggers_reject_any_row_change(tmp_path, operation: str) -> None:
    db_path = tmp_path / "immutable.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        user, assistant, call = _raw_parent_set(conn)
        record = _raw_record(
            conversation_id="conv_raw",
            user_message_id=user["id"],
            assistant_message_id=assistant["id"],
            model_call_id=call["id"],
        )
        _raw_insert(conn, record)
        sql = (
            "UPDATE generalization_draft_records SET created_at = created_at"
            if operation == "update"
            else "DELETE FROM generalization_draft_records"
        )
        with pytest.raises(sqlite3.IntegrityError, match="rows are immutable"):
            conn.execute(sql)
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_exact_earlier_receipt_survives_later_interloper_call(tmp_path) -> None:
    db_path = tmp_path / "receipt-interloper.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_receipt")
        user, assistant = _append_round(conn, "conv_receipt")
        exact = _record_call(conn, "conv_receipt", model_name="exact-model")
        _record_call(conn, "conv_receipt", model_name="later-interloper")
        conn.execute("BEGIN IMMEDIATE")
        record = create_generalization_draft_record(
            conn,
            payload=_payload(),
            conversation_id="conv_receipt",
            owner_username="owner",
            source_user_message_id=user["id"],
            source_assistant_message_id=assistant["id"],
            model_call_receipt=_receipt(exact),
            agent_version="1.0.0",
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    assert record["model_attribution"]["model_call_id"] == exact["id"]
    assert record["model_attribution"]["model_name"] == "exact-model"


@pytest.mark.parametrize("case", ["missing", "interloper", "multiple", "failed", "non-chat"])
def test_draft_creation_rejects_non_exact_receipt(tmp_path, case: str) -> None:
    db_path = tmp_path / f"receipt-{case}.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_receipt")
        user, assistant = _append_round(conn, "conv_receipt")
        call = _record_call(
            conn,
            "conv_receipt",
            status="failed" if case == "failed" else "success",
        )
        receipt: Any = _receipt(call, kind="vision" if case == "non-chat" else "chat")
        if case == "missing":
            receipt["model_call_id"] = 999_999
        elif case == "interloper":
            receipt["model_name"] = "not-the-persisted-row"
        elif case == "multiple":
            receipt = [receipt, copy.deepcopy(receipt)]
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            create_generalization_draft_record(
                conn,
                payload=_payload(),
                conversation_id="conv_receipt",
                owner_username="owner",
                source_user_message_id=user["id"],
                source_assistant_message_id=assistant["id"],
                model_call_receipt=receipt,
                agent_version="1.0.0",
            )
        conn.execute("ROLLBACK")
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_used_receipt_cannot_be_reused_for_another_record(tmp_path) -> None:
    db_path = tmp_path / "receipt-reuse.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_receipt")
        user1, assistant1 = _append_round(conn, "conv_receipt", suffix="-1")
        call = _record_call(conn, "conv_receipt")
        conn.execute("BEGIN IMMEDIATE")
        create_generalization_draft_record(
            conn,
            payload=_payload(),
            conversation_id="conv_receipt",
            owner_username="owner",
            source_user_message_id=user1["id"],
            source_assistant_message_id=assistant1["id"],
            model_call_receipt=_receipt(call),
            agent_version="1.0.0",
        )
        conn.execute("COMMIT")
        user2, assistant2 = _append_round(conn, "conv_receipt", suffix="-2")
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            create_generalization_draft_record(
                conn,
                payload=_payload(title="另一份草稿"),
                conversation_id="conv_receipt",
                owner_username="owner",
                source_user_message_id=user2["id"],
                source_assistant_message_id=assistant2["id"],
                model_call_receipt=_receipt(call),
                agent_version="1.0.0",
            )
        conn.execute("ROLLBACK")
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_non_life_agent_is_rejected_before_insert_even_if_caller_commits(
    tmp_path,
) -> None:
    db_path = tmp_path / "non-life-agent.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_wrong_agent", agent_id="guide_agent")
        user, assistant = _append_round(conn, "conv_wrong_agent")
        call = _record_call(
            conn,
            "conv_wrong_agent",
            agent_id="guide_agent",
        )

        conn.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(GeneralizationDraftRecordIntegrityError):
                create_generalization_draft_record(
                    conn,
                    payload=_payload(),
                    conversation_id="conv_wrong_agent",
                    owner_username="owner",
                    source_user_message_id=user["id"],
                    source_assistant_message_id=assistant["id"],
                    model_call_receipt=_receipt(call),
                    agent_version="1.0.0",
                )
        finally:
            # The public creation seam must reject before INSERT; a trusted caller
            # catching the integrity error must not be able to commit a residue.
            if conn.in_transaction:
                conn.execute("COMMIT")

        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_payload_normalization_is_nfc_order_stable_and_preserves_inner_whitespace() -> None:
    first = _payload(title="  Cafe\u0301  检查  ", trigger="外层\n\n  内层")
    second = dict(reversed(list(_payload(title="Caf\u00e9  检查", trigger="外层\n\n  内层").items())))

    normalized_first = normalize_generalization_draft_payload(first)
    normalized_second = normalize_generalization_draft_payload(second)

    assert normalized_first == normalized_second
    assert normalized_first["title"] == "Caf\u00e9  检查"
    assert normalized_first["trigger"] == "外层\n\n  内层"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: {**value, "unexpected": "field"},
        lambda value: {**value, "title": float("nan")},
        lambda value: {**value, "title": "\ud800"},
    ],
    ids=["extra-key", "nan", "invalid-unicode"],
)
def test_payload_normalizer_rejects_noncanonical_model_values(
    mutation: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    with pytest.raises(GeneralizationDraftPayloadError):
        normalize_generalization_draft_payload(mutation(_payload()))


@pytest.mark.parametrize(
    "field,corrupt_value",
    [
        ("content_digest", "sha256:" + "0" * 64),
        ("record_digest", "sha256:" + "0" * 64),
        ("source_context_digest", "sha256:" + "0" * 64),
    ],
)
def test_cold_read_rejects_each_digest_mutation(
    tmp_path, field: str, corrupt_value: str
) -> None:
    db_path = tmp_path / f"mutate-{field}.sqlite3"
    conn, record, _parents = _create_record_fixture(db_path)
    try:
        conn.execute("DROP TRIGGER trg_generalization_draft_records_no_update")
        conn.execute(
            f"UPDATE generalization_draft_records SET {field} = ? WHERE id = ?",
            (corrupt_value, record["id"]),
        )
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            load_verified_generalization_draft_record(
                conn,
                conversation_id="conv_hardening",
                record_id=record["id"],
                owner_username="owner",
            )
    finally:
        conn.close()


@pytest.mark.parametrize("mutation", ["whitespace", "extra", "nan"])
def test_cold_read_rejects_noncanonical_or_invalid_payload_json(
    tmp_path, mutation: str
) -> None:
    db_path = tmp_path / f"payload-json-{mutation}.sqlite3"
    conn, record, _parents = _create_record_fixture(db_path)
    try:
        conn.execute("DROP TRIGGER trg_generalization_draft_records_no_update")
        if mutation == "whitespace":
            raw = json.dumps(record["payload"], ensure_ascii=False)
        elif mutation == "extra":
            payload = {**record["payload"], "unexpected": "field"}
            raw = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            raw = json.dumps(
                {**record["payload"], "title": float("nan")},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=True,
            )
            conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute(
            "UPDATE generalization_draft_records SET payload_json = ? WHERE id = ?",
            (raw, record["id"]),
        )
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            load_verified_generalization_draft_record(
                conn,
                conversation_id="conv_hardening",
                record_id=record["id"],
                owner_username="owner",
            )
    finally:
        conn.close()


@pytest.mark.parametrize("drift", ["content", "role", "conversation"])
def test_cold_read_rejects_source_prefix_parent_drift(
    tmp_path, drift: str
) -> None:
    db_path = tmp_path / f"parent-drift-{drift}.sqlite3"
    conn, record, parents = _create_record_fixture(db_path)
    try:
        if drift == "content":
            conn.execute(
                "UPDATE conversation_messages SET content = '被篡改' WHERE id = ?",
                (parents["user"]["id"],),
            )
        elif drift == "role":
            conn.execute(
                "UPDATE conversation_messages SET role = 'user' WHERE id = ?",
                (parents["assistant"]["id"],),
            )
        else:
            _create_conversation(conn, "conv_other")
            conn.execute(
                "UPDATE conversation_messages SET conversation_id = 'conv_other' "
                "WHERE id = ?",
                (parents["user"]["id"],),
            )
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            load_verified_generalization_draft_record(
                conn,
                conversation_id="conv_hardening",
                record_id=record["id"],
                owner_username="owner",
            )
    finally:
        conn.close()


def test_later_turns_do_not_change_frozen_source_context(tmp_path) -> None:
    db_path = tmp_path / "later-turn.sqlite3"
    conn, record, _parents = _create_record_fixture(db_path)
    try:
        before = load_verified_generalization_draft_record(
            conn,
            conversation_id="conv_hardening",
            record_id=record["id"],
            owner_username="owner",
        )["source_context"]
        _append_round(conn, "conv_hardening", suffix="-later")
        after = load_verified_generalization_draft_record(
            conn,
            conversation_id="conv_hardening",
            record_id=record["id"],
            owner_username="owner",
        )["source_context"]
    finally:
        conn.close()
    assert after == before
    assert after["conversation"]["messages"][-1]["id"] == record["lineage"][
        "assistant_message_id"
    ]


def test_missing_record_is_null_but_existing_invalid_record_fails_whole_projection(
    tmp_path,
) -> None:
    db_path = tmp_path / "projection-fail-closed.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_projection")
        _user, assistant = _append_round(conn, "conv_projection")
        messages = repos.list_messages(conn, "conv_projection")
        absent = project_conversation_messages(
            conn,
            messages=messages,
            conversation_id="conv_projection",
            owner_username="owner",
        )
        assert absent[-1]["generalization_draft_record"] is None

        call = _record_call(conn, "conv_projection")
        conn.execute("BEGIN IMMEDIATE")
        record = create_generalization_draft_record(
            conn,
            payload=_payload(),
            conversation_id="conv_projection",
            owner_username="owner",
            source_user_message_id=messages[-2]["id"],
            source_assistant_message_id=assistant["id"],
            model_call_receipt=_receipt(call),
            agent_version="1.0.0",
        )
        conn.execute("COMMIT")
        conn.execute("DROP TRIGGER trg_generalization_draft_records_no_update")
        conn.execute(
            "UPDATE generalization_draft_records SET record_digest = ? WHERE id = ?",
            ("sha256:" + "0" * 64, record["id"]),
        )
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            project_conversation_messages(
                conn,
                messages=repos.list_messages(conn, "conv_projection"),
                conversation_id="conv_projection",
                owner_username="owner",
            )
    finally:
        conn.close()


def test_owner_and_cross_conversation_source_messages_fail_before_insert(
    tmp_path,
) -> None:
    db_path = tmp_path / "lineage-create.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_owner")
        _create_conversation(conn, "conv_foreign")
        _user, _assistant = _append_round(conn, "conv_owner")
        foreign_user, foreign_assistant = _append_round(conn, "conv_foreign")
        call = _record_call(conn, "conv_owner")
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            create_generalization_draft_record(
                conn,
                payload=_payload(),
                conversation_id="conv_owner",
                owner_username="another-owner",
                source_user_message_id=foreign_user["id"],
                source_assistant_message_id=foreign_assistant["id"],
                model_call_receipt=_receipt(call),
                agent_version="1.0.0",
            )
        conn.execute("ROLLBACK")

        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(GeneralizationDraftRecordIntegrityError):
            create_generalization_draft_record(
                conn,
                payload=_payload(),
                conversation_id="conv_owner",
                owner_username="owner",
                source_user_message_id=foreign_user["id"],
                source_assistant_message_id=foreign_assistant["id"],
                model_call_receipt=_receipt(call),
                agent_version="1.0.0",
            )
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_successful_no_task_draft_has_null_lineage_and_zero_task_side_effects(
    tmp_path,
) -> None:
    db_path = tmp_path / "no-task-success.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        before = {
            "tasks": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            "task_events": conn.execute(
                "SELECT COUNT(*) FROM task_events"
            ).fetchone()[0],
        }
        _create_conversation(conn, "conv_no_task")
        user, assistant = _append_round(conn, "conv_no_task")
        call = _record_call(conn, "conv_no_task")

        conn.execute("BEGIN IMMEDIATE")
        public_record = create_generalization_draft_record(
            conn,
            payload=_payload(),
            conversation_id="conv_no_task",
            owner_username="owner",
            source_user_message_id=user["id"],
            source_assistant_message_id=assistant["id"],
            model_call_receipt=_receipt(call),
            agent_version="1.0.0",
        )
        conn.execute("COMMIT")

        storage = conn.execute(
            "SELECT source_task_id, model_call_id "
            "FROM generalization_draft_records WHERE id = ?",
            (public_record["id"],),
        ).fetchone()
        persisted_model_call = repos.get_model_call(conn, storage["model_call_id"])
        after = {
            "tasks": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            "task_events": conn.execute(
                "SELECT COUNT(*) FROM task_events"
            ).fetchone()[0],
        }
    finally:
        conn.close()

    assert public_record["lineage"]["task_id"] is None
    assert storage["source_task_id"] is None
    assert persisted_model_call["task_id"] is None
    assert before == after == {"tasks": 0, "task_events": 0}


def test_round_rollback_removes_messages_and_record_but_keeps_model_audit(
    tmp_path,
) -> None:
    db_path = tmp_path / "round-rollback.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _create_conversation(conn, "conv_rollback")
        call = _record_call(conn, "conv_rollback")
        conn.execute("BEGIN IMMEDIATE")
        user, assistant = _append_round(conn, "conv_rollback")
        create_generalization_draft_record(
            conn,
            payload=_payload(),
            conversation_id="conv_rollback",
            owner_username="owner",
            source_user_message_id=user["id"],
            source_assistant_message_id=assistant["id"],
            model_call_receipt=_receipt(call),
            agent_version="1.0.0",
        )
        conn.execute("ROLLBACK")

        assert repos.list_messages(conn, "conv_rollback") == []
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 0
        assert repos.get_model_call(conn, call["id"])["status"] == "success"
    finally:
        conn.close()
