"""P2.3 storage migration contracts for stable public conversation message ids."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.storage import db as db_mod
from backend.app.storage import repos


_PUBLIC_MESSAGE_ID = re.compile(r"^msg_[a-f0-9]{32}$")


def _seed_question_context(
    conn: sqlite3.Connection,
    *,
    conversation_hex: str = "1",
    owner: str = "alice",
) -> tuple[str, str]:
    conversation_id = "conv_" + conversation_hex * 32
    repos.create_conversation(
        conn,
        conversation_id=conversation_id,
        agent_id="guide_agent",
        created_by=owner.title(),
        created_by_username=owner,
    )
    prompt_message = repos.append_message(
        conn,
        conversation_id=conversation_id,
        role="assistant",
        content="请补充一个信息。",
    )
    return conversation_id, prompt_message["message_id"]


def _direct_insert_question(
    conn: sqlite3.Connection,
    *,
    question_id: str | None,
    conversation_id: str,
    prompt_message_id: str,
    owner: str,
    created_at: str = "2026-07-19T00:00:00.000000+00:00",
    expires_at: str = "2026-07-20T00:00:00.000000+00:00",
    rowid: int | None = None,
) -> None:
    columns = [
        "id",
        "conversation_id",
        "prompt_message_id",
        "asked_to_username",
        "revision",
        "kind",
        "prompt",
        "description",
        "options_json",
        "created_at",
        "expires_at",
        "closed_reason",
        "closed_at",
        "submission_id",
        "answer_json",
        "answered_by_username",
        "answer_message_id",
        "response_message_id",
    ]
    values: list[object] = [
        question_id,
        conversation_id,
        prompt_message_id,
        owner,
        1,
        "free_text",
        "请描述边界。",
        None,
        "[]",
        created_at,
        expires_at,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    if rowid is not None:
        columns.insert(0, "rowid")
        values.insert(0, rowid)
    conn.execute(
        f"INSERT OR REPLACE INTO conversation_questions ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)})",
        values,
    )


def _seed_existing_nullable_question_schema(path: Path) -> None:
    """Create the already-deployed P2.3 shape before hardening triggers exist."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE conversation_questions (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                prompt_message_id TEXT NOT NULL,
                asked_to_username TEXT NOT NULL,
                revision INTEGER NOT NULL,
                kind TEXT NOT NULL,
                prompt TEXT NOT NULL,
                description TEXT,
                options_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                closed_reason TEXT,
                closed_at TEXT,
                submission_id TEXT,
                answer_json TEXT,
                answered_by_username TEXT,
                answer_message_id TEXT,
                response_message_id TEXT
            );
            """
        )
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def _seed_pre_p23_database(path: Path) -> tuple[str, list[str]]:
    """Create only the two pre-P2.3 conversation tables with three legacy rows."""
    conversation_id = "conv_" + "a" * 32
    contents = ["第一条旧消息", "第二条旧消息", "第三条旧消息"]
    conn = sqlite3.connect(path)
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
            """
        )
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?,?)",
            (
                conversation_id,
                "guide_agent",
                "active",
                "旧用户",
                None,
                "2025-01-01T00:00:00+00:00",
                "2025-01-01T00:00:00+00:00",
            ),
        )
        for index, content in enumerate(contents):
            conn.execute(
                """
                INSERT INTO conversation_messages
                    (conversation_id, role, content, recommendation_json, file_ids, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    conversation_id,
                    "user" if index % 2 == 0 else "assistant",
                    content,
                    None,
                    "[]",
                    f"2025-01-01T00:00:0{index}+00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return conversation_id, contents


def test_fresh_p23_schema_has_question_table_and_required_public_message_id(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "fresh-p23.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        message_columns = _columns(conn, "conversation_messages")
        assert "message_id" in message_columns
        assert message_columns["message_id"][3] == 1, "fresh rows require a public id"

        question_columns = _columns(conn, "conversation_questions")
        assert {
            "id",
            "conversation_id",
            "prompt_message_id",
            "asked_to_username",
            "revision",
            "kind",
            "prompt",
            "description",
            "options_json",
            "created_at",
            "expires_at",
            "closed_reason",
            "closed_at",
            "submission_id",
            "answer_json",
            "answered_by_username",
            "answer_message_id",
            "response_message_id",
        } <= set(question_columns)
    finally:
        conn.close()


def test_legacy_messages_receive_unique_stable_public_ids_on_idempotent_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-message-ids.db"
    conversation_id, contents = _seed_pre_p23_database(db_path)

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        first = conn.execute(
            "SELECT id, message_id, content FROM conversation_messages ORDER BY id"
        ).fetchall()
        assert [row["content"] for row in first] == contents
        first_ids = [row["message_id"] for row in first]
        assert all(_PUBLIC_MESSAGE_ID.fullmatch(value or "") for value in first_ids)
        assert len(first_ids) == len(set(first_ids)) == 3
    finally:
        conn.close()

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        second_ids = [
            row["message_id"]
            for row in conn.execute(
                "SELECT message_id FROM conversation_messages ORDER BY id"
            )
        ]
        assert second_ids == first_ids, "repeated init must never rewrite public ids"

        new_message = repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="assistant",
            content="迁移后的新消息",
        )
        assert _PUBLIC_MESSAGE_ID.fullmatch(new_message["message_id"])
        assert new_message["message_id"] not in first_ids

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO conversation_messages
                    (message_id, conversation_id, role, content,
                     recommendation_json, file_ids, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    first_ids[0],
                    conversation_id,
                    "user",
                    "试图复用 public id",
                    None,
                    "[]",
                    "2025-01-01T00:01:00+00:00",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE conversation_messages SET message_id = ? WHERE message_id = ?",
                ("msg_" + "f" * 32, first_ids[0]),
            )
    finally:
        conn.close()


def test_partial_message_id_migration_fails_on_poison_then_converges_concurrently(
    tmp_path: Path,
) -> None:
    import threading

    db_path = tmp_path / "partial-message-public-ids.db"
    _conversation_id, _contents = _seed_pre_p23_database(db_path)
    valid_id = "msg_" + "1" * 32
    repaired_id = "msg_" + "2" * 32
    poison_id = "msg_" + "A" * 32

    raw = sqlite3.connect(str(db_path))
    try:
        raw.execute("ALTER TABLE conversation_messages ADD COLUMN message_id TEXT")
        raw.execute(
            "UPDATE conversation_messages SET message_id = ? WHERE id = 1",
            (valid_id,),
        )
        raw.execute(
            "UPDATE conversation_messages SET message_id = ? WHERE id = 2",
            (poison_id,),
        )
        raw.commit()
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match="public id is invalid"):
        db_mod.init_db(db_path)

    # The failed migration is transactional: valid/invalid values are never
    # rewritten, and the NULL backfill rolls back together with the startup.
    raw = sqlite3.connect(str(db_path))
    try:
        assert raw.execute(
            "SELECT message_id FROM conversation_messages ORDER BY id"
        ).fetchall() == [(valid_id,), (poison_id,), (None,)]
        raw.execute(
            "UPDATE conversation_messages SET message_id = ? WHERE id = 2",
            (repaired_id,),
        )
        raw.commit()
    finally:
        raw.close()

    barrier = threading.Barrier(3)
    errors: list[Exception] = []

    def initialize() -> None:
        barrier.wait()
        try:
            db_mod.init_db(db_path)
        except Exception as exc:  # noqa: BLE001 - concurrent witness captures all
            errors.append(exc)

    threads = [threading.Thread(target=initialize) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    conn = db_mod.get_conn(db_path)
    try:
        first_ids = [
            row[0]
            for row in conn.execute(
                "SELECT message_id FROM conversation_messages ORDER BY id"
            )
        ]
        assert first_ids[:2] == [valid_id, repaired_id]
        assert all(_PUBLIC_MESSAGE_ID.fullmatch(value) for value in first_ids)
    finally:
        conn.close()

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        assert [
            row[0]
            for row in conn.execute(
                "SELECT message_id FROM conversation_messages ORDER BY id"
            )
        ] == first_ids
    finally:
        conn.close()


def test_noncanonical_existing_question_table_fails_startup(tmp_path: Path) -> None:
    db_path = tmp_path / "noncanonical-existing-question-schema.db"
    _seed_existing_nullable_question_schema(db_path)

    # SQLite cannot make the deployed nullable primary key equivalent to the
    # canonical NOT NULL table in place.  A trigger-only approximation is not a
    # trustworthy schema migration, so startup must fail closed without silently
    # claiming the table shape converged.
    with pytest.raises(sqlite3.IntegrityError, match="question_table_shape"):
        db_mod.init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        assert _columns(conn, "conversation_questions")["id"][3] == 0
        assert conn.execute("SELECT COUNT(*) FROM conversation_questions").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    "invalid_id",
    [None, "", "question_" + "a" * 32, "q_short", "q_" + "A" * 32],
)
def test_canonical_question_table_rejects_invalid_public_id(
    tmp_path: Path, invalid_id: str | None
) -> None:
    db_path = tmp_path / "canonical-question-public-id.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        with pytest.raises(sqlite3.IntegrityError, match="public id|required|NOT NULL"):
            _direct_insert_question(
                conn,
                question_id=invalid_id,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message_id,
                owner="alice",
            )
        assert conn.execute("SELECT COUNT(*) FROM conversation_questions").fetchone()[0] == 0
    finally:
        conn.close()


def test_question_insert_replace_cannot_delete_any_conflicting_fact(
    tmp_path: Path,
) -> None:
    """Guard every UNIQUE/rowid REPLACE surface before implicit deletion."""
    db_path = tmp_path / "question-replace-conflicts.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_1 = _seed_question_context(conn)
        q1 = "q_" + "1" * 32
        _direct_insert_question(
            conn,
            question_id=q1,
            conversation_id=conversation_id,
            prompt_message_id=prompt_1,
            owner="alice",
        )
        repos.close_unresolved_questions(
            conn,
            conversation_id,
            "alice",
            now="2026-07-19T01:00:00+00:00",
        )

        conn.execute("PRAGMA recursive_triggers=OFF")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            _direct_insert_question(
                conn,
                question_id="q_" + "2" * 32,
                conversation_id=conversation_id,
                prompt_message_id=prompt_1,
                owner="alice",
            )
        assert conn.execute(
            "SELECT id FROM conversation_questions WHERE prompt_message_id = ?",
            (prompt_1,),
        ).fetchone()[0] == q1

        prompt_2 = repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="assistant",
            content="第二个问题。",
        )["message_id"]
        q2 = "q_" + "3" * 32
        _direct_insert_question(
            conn,
            question_id=q2,
            conversation_id=conversation_id,
            prompt_message_id=prompt_2,
            owner="alice",
        )
        prompt_3 = repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="assistant",
            content="第三个问题。",
        )["message_id"]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            _direct_insert_question(
                conn,
                question_id="q_" + "4" * 32,
                conversation_id=conversation_id,
                prompt_message_id=prompt_3,
                owner="alice",
            )
        assert conn.execute(
            "SELECT id FROM conversation_questions WHERE closed_reason IS NULL"
        ).fetchone()[0] == q2

        repos.close_unresolved_questions(
            conn,
            conversation_id,
            "alice",
            now="2026-07-19T02:00:00+00:00",
        )
        q2_rowid = conn.execute(
            "SELECT rowid FROM conversation_questions WHERE id = ?", (q2,)
        ).fetchone()[0]
        other_conversation_id, other_prompt = _seed_question_context(
            conn, conversation_hex="2", owner="bob"
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            _direct_insert_question(
                conn,
                question_id="q_" + "5" * 32,
                conversation_id=other_conversation_id,
                prompt_message_id=other_prompt,
                owner="bob",
                rowid=q2_rowid,
            )
        assert {
            row[0]
            for row in conn.execute("SELECT id FROM conversation_questions ORDER BY id")
        } == {q1, q2}
    finally:
        conn.close()


def test_nonpositive_internal_id_inserts_abort_without_poisoning_auto_ids(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "positive-internal-identities.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        conn.execute("PRAGMA recursive_triggers=OFF")

        for internal_id in (-1, 0):
            with pytest.raises(sqlite3.IntegrityError, match="positive"):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conversations
                        (rowid, id, agent_id, status, created_by,
                         created_by_username, recommendation_json, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        internal_id,
                        "conv_" + ("a" if internal_id == -1 else "b") * 32,
                        "guide_agent",
                        "active",
                        "Poison",
                        "poison",
                        None,
                        "2026-07-19T00:00:00+00:00",
                        "2026-07-19T00:00:00+00:00",
                    ),
                )
            with pytest.raises(sqlite3.IntegrityError, match="positive"):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conversation_messages
                        (id, message_id, conversation_id, role, content,
                         recommendation_json, file_ids, created_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        internal_id,
                        "msg_" + ("a" if internal_id == -1 else "b") * 32,
                        conversation_id,
                        "assistant",
                        "poison",
                        None,
                        "[]",
                        "2026-07-19T00:00:00+00:00",
                    ),
                )
            with pytest.raises(sqlite3.IntegrityError, match="positive"):
                _direct_insert_question(
                    conn,
                    question_id="q_" + ("a" if internal_id == -1 else "b") * 32,
                    conversation_id=conversation_id,
                    prompt_message_id=prompt_message_id,
                    owner="alice",
                    rowid=internal_id,
                )

        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM conversation_questions").fetchone()[0] == 0

        # Normal inserts still receive positive allocated identities after both
        # sentinel attempts; NEW.rowid=-1 is never compared as a real conflict.
        next_conversation_id, _ = _seed_question_context(
            conn, conversation_hex="3", owner="bob"
        )
        normal_message = repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="assistant",
            content="normal",
        )
        normal_question = repos.create_question(
            conn,
            question_id="q_" + "c" * 32,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "正常问题"},
            created_at="2026-07-19T00:00:00+00:00",
            expires_at="2026-07-20T00:00:00+00:00",
        )
        assert next_conversation_id == "conv_" + "3" * 32
        assert conn.execute(
            "SELECT id FROM conversation_messages WHERE message_id = ?",
            (normal_message["message_id"],),
        ).fetchone()[0] > 0
        assert conn.execute(
            "SELECT rowid FROM conversation_questions WHERE id = ?",
            (normal_question["id"],),
        ).fetchone()[0] > 0
    finally:
        conn.close()


def test_repository_rejects_casefold_duplicate_question_option_labels(
    tmp_path: Path,
) -> None:
    """Storage must preserve the workflow's case-insensitive option identity."""
    db_path = tmp_path / "question-option-label-casefold.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    question_id = "q_" + "6" * 32
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        with pytest.raises(ValueError, match="labels must be unique"):
            repos.create_question(
                conn,
                question_id=question_id,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message_id,
                asked_to_username="alice",
                question_spec={
                    "kind": "single_choice",
                    "prompt": "Choose one",
                    "options": [
                        {"id": "option_1", "label": "Option A"},
                        {"id": "option_2", "label": "option a"},
                    ],
                },
                created_at="2026-07-19T00:00:00+00:00",
                expires_at="2026-07-20T00:00:00+00:00",
            )
        assert repos.get_question(conn, question_id) is None
    finally:
        conn.close()


def test_question_owner_must_exactly_match_stable_conversation_owner(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "question-owner.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        with pytest.raises(sqlite3.IntegrityError, match="owner"):
            _direct_insert_question(
                conn,
                question_id="q_" + "6" * 32,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message_id,
                owner="bob",
            )
        assert conn.execute("SELECT COUNT(*) FROM conversation_questions").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("created_at", "expires_at"),
    [
        ("not-a-time", "2026-07-20T00:00:00.000000+00:00"),
        ("2026-07-19T00:00:00+00:00", "2026-07-20T00:00:00+00:00"),
        ("0000-07-19T00:00:00.000000+00:00", "0000-07-20T00:00:00.000000+00:00"),
        ("2026-00-19T00:00:00.000000+00:00", "2026-00-20T00:00:00.000000+00:00"),
        ("2026-13-19T00:00:00.000000+00:00", "2026-13-20T00:00:00.000000+00:00"),
        ("2026-07-00T00:00:00.000000+00:00", "2026-07-01T00:00:00.000000+00:00"),
        ("2026-04-31T00:00:00.000000+00:00", "2026-05-01T00:00:00.000000+00:00"),
        ("2026-02-29T00:00:00.000000+00:00", "2026-03-01T00:00:00.000000+00:00"),
        ("2026-02-30T00:00:00.000000+00:00", "2026-03-03T00:00:00.000000+00:00"),
        ("2026-07-19T24:00:00.000000+00:00", "2026-07-20T24:00:00.000000+00:00"),
        ("2026-07-19T12:60:00.000000+00:00", "2026-07-20T12:60:00.000000+00:00"),
        ("2026-07-19T12:00:60.000000+00:00", "2026-07-20T12:00:60.000000+00:00"),
        ("2026-07-19T00:00:00.000000+00:00", "2026-07-20T00:00:00.000001+00:00"),
    ],
)
def test_sqlite_rejects_noncanonical_or_non_24h_question_timestamps(
    tmp_path: Path, created_at: str, expires_at: str
) -> None:
    db_path = tmp_path / "question-time.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        with pytest.raises(sqlite3.IntegrityError, match="timestamp|TTL"):
            _direct_insert_question(
                conn,
                question_id="q_" + "7" * 32,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message_id,
                owner="alice",
                created_at=created_at,
                expires_at=expires_at,
            )
    finally:
        conn.close()


def test_sqlite_accepts_real_leap_day_with_fixed_microseconds_and_exact_ttl(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "question-valid-leap-time.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        question_id = "q_" + "c" * 32
        _direct_insert_question(
            conn,
            question_id=question_id,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            owner="alice",
            created_at="2028-02-29T23:59:59.999999+00:00",
            expires_at="2028-03-01T23:59:59.999999+00:00",
        )
        projected = repos.get_question(
            conn, question_id, now="2028-03-01T00:00:00.000000+00:00"
        )
        assert projected is not None
        assert projected["status"] == "pending"
        assert projected["created_at"] == "2028-02-29T23:59:59.999999+00:00"
        assert projected["expires_at"] == "2028-03-01T23:59:59.999999+00:00"
    finally:
        conn.close()


@pytest.mark.parametrize(
    "invalid_closed_at",
    [
        "0000-07-19T12:00:00.000000+00:00",
        "2026-00-19T12:00:00.000000+00:00",
        "2026-13-19T12:00:00.000000+00:00",
        "2026-07-00T12:00:00.000000+00:00",
        "2026-04-31T12:00:00.000000+00:00",
        "2026-02-29T12:00:00.000000+00:00",
        "2026-07-19T24:00:00.000000+00:00",
        "2026-07-19T12:60:00.000000+00:00",
        "2026-07-19T12:00:60.000000+00:00",
    ],
)
def test_sqlite_rejects_out_of_range_question_resolution_timestamp(
    tmp_path: Path, invalid_closed_at: str
) -> None:
    db_path = tmp_path / "question-invalid-resolution-time.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        question_id = "q_" + "d" * 32
        _direct_insert_question(
            conn,
            question_id=question_id,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            owner="alice",
        )
        with pytest.raises(sqlite3.IntegrityError, match="timestamp"):
            conn.execute(
                "UPDATE conversation_questions "
                "SET closed_reason = 'superseded', closed_at = ? WHERE id = ?",
                (invalid_closed_at, question_id),
            )
        row = conn.execute(
            "SELECT closed_reason, closed_at FROM conversation_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        assert tuple(row) == (None, None)
    finally:
        conn.close()


def test_concurrent_idempotent_init_converges_all_p23_managed_schema_objects(
    tmp_path: Path,
) -> None:
    import threading

    db_path = tmp_path / "p23-managed-schema-convergence.db"
    db_mod.init_db(db_path)

    def schema_sql(
        conn: sqlite3.Connection, object_type: str, names: tuple[str, ...]
    ) -> dict[str, str]:
        placeholders = ",".join("?" for _ in names)
        rows = conn.execute(
            f"SELECT name, sql FROM sqlite_master WHERE type = ? "
            f"AND name IN ({placeholders}) ORDER BY name",
            (object_type, *names),
        ).fetchall()
        result = {row["name"]: row["sql"] for row in rows}
        assert set(result) == set(names)
        return result

    conn = db_mod.get_conn(db_path)
    try:
        canonical_triggers = schema_sql(
            conn, "trigger", db_mod._P23_MANAGED_TRIGGERS
        )
        canonical_indexes = schema_sql(conn, "index", db_mod._P23_MANAGED_INDEXES)

        for trigger_name in db_mod._P23_MANAGED_TRIGGERS:
            if trigger_name.startswith("trg_conversation_messages_"):
                table = "conversation_messages"
            elif trigger_name.startswith("trg_conversation_questions_"):
                table = "conversation_questions"
            else:
                table = "conversations"
            conn.execute(f"DROP TRIGGER {trigger_name}")
            conn.execute(
                f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON {table} "
                "WHEN 0 BEGIN SELECT 1; END"
            )

        for index_name in db_mod._P23_MANAGED_INDEXES:
            conn.execute(f"DROP INDEX {index_name}")
            if index_name.startswith("idx_conversation_messages_"):
                table, column = "conversation_messages", "content"
            elif index_name.startswith("idx_conversation_questions_"):
                table, column = "conversation_questions", "prompt"
            else:
                table, column = "conversations", "created_by"
            conn.execute(f"CREATE INDEX {index_name} ON {table}({column})")
    finally:
        conn.close()

    barrier = threading.Barrier(3)
    errors: list[Exception] = []

    def initialize() -> None:
        barrier.wait()
        try:
            db_mod.init_db(db_path)
        except Exception as exc:  # noqa: BLE001 - concurrent witness captures all
            errors.append(exc)

    threads = [threading.Thread(target=initialize) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    conn = db_mod.get_conn(db_path)
    try:
        assert schema_sql(conn, "trigger", db_mod._P23_MANAGED_TRIGGERS) == canonical_triggers
        assert schema_sql(conn, "index", db_mod._P23_MANAGED_INDEXES) == canonical_indexes
    finally:
        conn.close()

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        assert schema_sql(conn, "trigger", db_mod._P23_MANAGED_TRIGGERS) == canonical_triggers
        assert schema_sql(conn, "index", db_mod._P23_MANAGED_INDEXES) == canonical_indexes
    finally:
        conn.close()


@pytest.mark.parametrize(
    "poison",
    [
        "question_id",
        "nonpositive_rowid",
        "owner_link",
        "prompt_link",
        "timestamp",
        "ttl",
        "options_json",
        "duplicate_option_label_casefold",
        "revision",
        "kind",
        "partial_unresolved",
        "late_answer",
        "answer_json",
        "answer_link",
    ],
)
def test_init_fails_closed_without_rewriting_historical_question_poison(
    tmp_path: Path, poison: str
) -> None:
    """Managed triggers are prospective; restart must audit pre-existing facts."""
    db_path = tmp_path / f"historical-question-poison-{poison}.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        question_id = "q_" + "e" * 32
        repos.create_question(
            conn,
            question_id=question_id,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "历史事实是否可信？"},
            created_at="2026-07-19T00:00:00+00:00",
            expires_at="2026-07-20T00:00:00+00:00",
        )
        answer_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="user", content="回答"
        )["message_id"]
        response_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="收到"
        )["message_id"]

        # Simulate a prior generation that had no effective write guards.  Table
        # CHECK constraints are also bypassed so every historical branch is
        # exercised by the restart audit itself, not by current write-time DDL.
        for trigger_name in db_mod._P23_MANAGED_TRIGGERS:
            if trigger_name.startswith("trg_conversation_questions_"):
                conn.execute(f"DROP TRIGGER {trigger_name}")
        conn.execute("PRAGMA ignore_check_constraints=ON")

        answered_tuple = (
            "answered",
            "2026-07-19T01:00:00.000000+00:00",
            "submission-historical-poison",
            '{"kind":"text","text":"回答"}',
            "alice",
            answer_message_id,
            response_message_id,
            question_id,
        )
        if poison == "question_id":
            conn.execute(
                "UPDATE conversation_questions SET id = 'q_BAD' WHERE id = ?",
                (question_id,),
            )
        elif poison == "nonpositive_rowid":
            conn.execute(
                "UPDATE conversation_questions SET rowid = 0 WHERE id = ?",
                (question_id,),
            )
        elif poison == "owner_link":
            conn.execute(
                "UPDATE conversation_questions SET asked_to_username = 'bob' WHERE id = ?",
                (question_id,),
            )
        elif poison == "prompt_link":
            conn.execute(
                "UPDATE conversation_questions SET prompt_message_id = ? WHERE id = ?",
                ("msg_" + "f" * 32, question_id),
            )
        elif poison == "timestamp":
            conn.execute(
                "UPDATE conversation_questions "
                "SET created_at = '0000-07-19T00:00:00.000000+00:00', "
                "expires_at = '0000-07-20T00:00:00.000000+00:00' WHERE id = ?",
                (question_id,),
            )
        elif poison == "ttl":
            conn.execute(
                "UPDATE conversation_questions "
                "SET expires_at = '2026-07-19T23:59:59.999999+00:00' WHERE id = ?",
                (question_id,),
            )
        elif poison == "options_json":
            conn.execute(
                "UPDATE conversation_questions SET options_json = '[ ]' WHERE id = ?",
                (question_id,),
            )
        elif poison == "duplicate_option_label_casefold":
            conn.execute(
                "UPDATE conversation_questions SET kind = 'single_choice', "
                "options_json = ? WHERE id = ?",
                (
                    '[{"description":null,"id":"option_1","label":"Option A"},'
                    '{"description":null,"id":"option_2","label":"option a"}]',
                    question_id,
                ),
            )
        elif poison == "revision":
            conn.execute(
                "UPDATE conversation_questions SET revision = 2 WHERE id = ?",
                (question_id,),
            )
        elif poison == "kind":
            conn.execute(
                "UPDATE conversation_questions SET kind = 'bogus' WHERE id = ?",
                (question_id,),
            )
        elif poison == "partial_unresolved":
            conn.execute(
                "UPDATE conversation_questions "
                "SET submission_id = 'submission-without-resolution' WHERE id = ?",
                (question_id,),
            )
        elif poison == "late_answer":
            conn.execute(
                "UPDATE conversation_questions SET closed_reason = ?, "
                "closed_at = '2026-07-20T00:00:00.000000+00:00', "
                "submission_id = ?, answer_json = ?, answered_by_username = ?, "
                "answer_message_id = ?, response_message_id = ? WHERE id = ?",
                (
                    answered_tuple[0],
                    answered_tuple[2],
                    answered_tuple[3],
                    answered_tuple[4],
                    answered_tuple[5],
                    answered_tuple[6],
                    answered_tuple[7],
                ),
            )
        elif poison == "answer_json":
            values = list(answered_tuple)
            values[3] = "{}"
            conn.execute(
                "UPDATE conversation_questions SET closed_reason = ?, closed_at = ?, "
                "submission_id = ?, answer_json = ?, answered_by_username = ?, "
                "answer_message_id = ?, response_message_id = ? WHERE id = ?",
                values,
            )
        elif poison == "answer_link":
            values = list(answered_tuple)
            values[5] = "msg_" + "d" * 32
            conn.execute(
                "UPDATE conversation_questions SET closed_reason = ?, closed_at = ?, "
                "submission_id = ?, answer_json = ?, answered_by_username = ?, "
                "answer_message_id = ?, response_message_id = ? WHERE id = ?",
                values,
            )
        else:  # pragma: no cover - parametrization is intentionally exhaustive
            raise AssertionError(poison)

        before = tuple(conn.execute("SELECT * FROM conversation_questions").fetchone())
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="historical row is invalid"):
        db_mod.init_db(db_path)

    # A rejected startup may repair neither the poison nor immutable facts around
    # it.  This also witnesses rollback of the managed-object refresh transaction.
    raw = sqlite3.connect(db_path)
    try:
        after = tuple(raw.execute("SELECT * FROM conversation_questions").fetchone())
        assert after == before
    finally:
        raw.close()


def test_restart_accepts_naturally_expired_but_still_unresolved_question(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "historical-natural-expiry.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        question_id = "q_" + "f" * 32
        repos.create_question(
            conn,
            question_id=question_id,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "自然过期"},
            created_at="2020-01-01T00:00:00+00:00",
            expires_at="2020-01-02T00:00:00+00:00",
        )
        before = tuple(
            conn.execute(
                "SELECT closed_reason, closed_at, submission_id, answer_json "
                "FROM conversation_questions WHERE id = ?",
                (question_id,),
            ).fetchone()
        )
        assert before == (None, None, None, None)
    finally:
        conn.close()

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        projected = repos.get_question(
            conn, question_id, now="2026-07-19T00:00:00+00:00"
        )
        assert projected is not None
        assert projected["status"] == "expired"
        assert tuple(
            conn.execute(
                "SELECT closed_reason, closed_at, submission_id, answer_json "
                "FROM conversation_questions WHERE id = ?",
                (question_id,),
            ).fetchone()
        ) == before
    finally:
        conn.close()


def test_repository_normalizes_question_times_and_requires_exact_24h_ttl(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "question-time-normalization.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        question = repos.create_question(
            conn,
            question_id="q_" + "8" * 32,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "边界是什么？"},
            created_at="2026-07-19T08:00:00.123456+08:00",
            expires_at=datetime(
                2026, 7, 20, 8, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8))
            ),
        )
        assert question["created_at"] == "2026-07-19T00:00:00.123456+00:00"
        assert question["expires_at"] == "2026-07-20T00:00:00.123456+00:00"

        next_prompt = repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="assistant",
            content="不会被写入的非法 TTL。",
        )["message_id"]
        with pytest.raises(ValueError, match="24 hours"):
            repos.create_question(
                conn,
                question_id="q_" + "9" * 32,
                conversation_id=conversation_id,
                prompt_message_id=next_prompt,
                asked_to_username="alice",
                question_spec={"kind": "free_text", "prompt": "非法 TTL"},
                created_at="2026-07-19T00:00:00+00:00",
                expires_at="2026-07-19T23:59:59.999999+00:00",
            )
        assert repos.get_question(
            conn,
            question["id"],
            now="2026-07-19T12:00:00+00:00",
        )["status"] == "pending"
    finally:
        conn.close()


def test_answer_expiry_boundary_is_exact_to_one_microsecond(tmp_path: Path) -> None:
    db_path = tmp_path / "question-expiry-microsecond.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_message_id = _seed_question_context(conn)
        question_id = "q_" + "a" * 32
        repos.create_question(
            conn,
            question_id=question_id,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "写出边界"},
            created_at="2026-07-19T00:00:00.000500Z",
            expires_at="2026-07-20T00:00:00.000500Z",
        )
        answer_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="user", content="回答"
        )["message_id"]
        response_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="收到"
        )["message_id"]
        resolved = repos.resolve_question(
            conn,
            question_id=question_id,
            conversation_id=conversation_id,
            asked_to_username="alice",
            submission_id="submission-one-microsecond",
            answer={"kind": "text", "text": "回答"},
            answered_at="2026-07-20T00:00:00.000499+00:00",
            answer_message_id=answer_message_id,
            response_message_id=response_message_id,
        )
        assert resolved is not None
        assert resolved["answer"]["answered_at"] == "2026-07-20T00:00:00.000499+00:00"

        next_prompt = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="第二问"
        )["message_id"]
        next_question_id = "q_" + "b" * 32
        repos.create_question(
            conn,
            question_id=next_question_id,
            conversation_id=conversation_id,
            prompt_message_id=next_prompt,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "第二个边界"},
            created_at="2026-07-20T00:00:00.000500+00:00",
            expires_at="2026-07-21T00:00:00.000500+00:00",
        )
        equality_answer = repos.append_message(
            conn, conversation_id=conversation_id, role="user", content="太迟了"
        )["message_id"]
        equality_response = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="不会关联"
        )["message_id"]
        assert repos.resolve_question(
            conn,
            question_id=next_question_id,
            conversation_id=conversation_id,
            asked_to_username="alice",
            submission_id="submission-at-equality",
            answer={"kind": "text", "text": "太迟了"},
            answered_at="2026-07-21T00:00:00.000500+00:00",
            answer_message_id=equality_answer,
            response_message_id=equality_response,
        ) is None
        expired = repos.get_question(
            conn, next_question_id, now="2026-07-21T00:00:00.000500+00:00"
        )
        assert expired is not None
        assert expired["status"] == "expired"
        assert expired["answer"] is None
    finally:
        conn.close()


def test_answer_message_pair_is_unique_across_questions_even_when_order_matches(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "question-answer-pair-unique.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id, prompt_1 = _seed_question_context(conn)
        question_1 = repos.create_question(
            conn,
            question_id="q_" + "1" * 32,
            conversation_id=conversation_id,
            prompt_message_id=prompt_1,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "第一问"},
            created_at="2026-07-19T00:00:00+00:00",
            expires_at="2026-07-20T00:00:00+00:00",
        )
        # Seed Q2's assistant prompt before Q1's answer pair.  The reused pair
        # would therefore satisfy prompt<answer<response for both Questions; only
        # the cross-Question uniqueness contract can reject it.
        prompt_2 = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="第二问"
        )["message_id"]
        answer_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="user", content="第一答"
        )["message_id"]
        response_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="收到第一答"
        )["message_id"]
        assert repos.resolve_question(
            conn,
            question_id=question_1["id"],
            conversation_id=conversation_id,
            asked_to_username="alice",
            submission_id="submission-question-one",
            answer={"kind": "text", "text": "第一答"},
            answered_at="2026-07-19T01:00:00+00:00",
            answer_message_id=answer_message_id,
            response_message_id=response_message_id,
        ) is not None
        question_2 = repos.create_question(
            conn,
            question_id="q_" + "2" * 32,
            conversation_id=conversation_id,
            prompt_message_id=prompt_2,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "第二问"},
            created_at="2026-07-19T02:00:00+00:00",
            expires_at="2026-07-20T02:00:00+00:00",
        )
        conn.execute("PRAGMA recursive_triggers=OFF")
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            repos.resolve_question(
                conn,
                question_id=question_2["id"],
                conversation_id=conversation_id,
                asked_to_username="alice",
                submission_id="submission-question-two",
                answer={"kind": "text", "text": "复用"},
                answered_at="2026-07-19T03:00:00+00:00",
                answer_message_id=answer_message_id,
                response_message_id=response_message_id,
            )
        assert repos.get_question(
            conn,
            question_2["id"],
            now="2026-07-19T03:00:00+00:00",
        )["status"] == "pending"
    finally:
        conn.close()


def test_answer_messages_must_follow_prompt_in_strict_internal_order(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "question-answer-message-order.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        conversation_id = "conv_" + "4" * 32
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by="Alice",
            created_by_username="alice",
        )
        early_answer = repos.append_message(
            conn, conversation_id=conversation_id, role="user", content="过早回答"
        )["message_id"]
        early_response = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="过早响应"
        )["message_id"]
        prompt_message_id = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="现在提问"
        )["message_id"]
        question = repos.create_question(
            conn,
            question_id="q_" + "3" * 32,
            conversation_id=conversation_id,
            prompt_message_id=prompt_message_id,
            asked_to_username="alice",
            question_spec={"kind": "free_text", "prompt": "现在回答"},
            created_at="2026-07-19T00:00:00+00:00",
            expires_at="2026-07-20T00:00:00+00:00",
        )
        conn.execute("PRAGMA recursive_triggers=OFF")
        with pytest.raises(sqlite3.IntegrityError, match="mismatch"):
            repos.resolve_question(
                conn,
                question_id=question["id"],
                conversation_id=conversation_id,
                asked_to_username="alice",
                submission_id="submission-early-pair",
                answer={"kind": "text", "text": "过早回答"},
                answered_at="2026-07-19T01:00:00+00:00",
                answer_message_id=early_answer,
                response_message_id=early_response,
            )
        assert repos.get_question(
            conn,
            question["id"],
            now="2026-07-19T01:00:00+00:00",
        )["status"] == "pending"

        # A legal prompt→answer→response sequence remains atomic inside an outer
        # write transaction and resolves normally.
        conn.execute("BEGIN IMMEDIATE")
        legal_answer = repos.append_message(
            conn, conversation_id=conversation_id, role="user", content="合法回答"
        )["message_id"]
        legal_response = repos.append_message(
            conn, conversation_id=conversation_id, role="assistant", content="合法响应"
        )["message_id"]
        resolved = repos.resolve_question(
            conn,
            question_id=question["id"],
            conversation_id=conversation_id,
            asked_to_username="alice",
            submission_id="submission-legal-pair",
            answer={"kind": "text", "text": "合法回答"},
            answered_at="2026-07-19T01:00:00+00:00",
            answer_message_id=legal_answer,
            response_message_id=legal_response,
        )
        conn.execute("COMMIT")
        assert resolved is not None
        assert resolved["status"] == "answered"
    finally:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.close()
