"""P2.3 会话稳定 owner 与 conversation_id 全引用封口。

安全缝：
- 会话 owner 只认登录 principal 的唯一 username；display_name 仅展示、允许撞名。
- 存量 ``created_by_username IS NULL`` 不猜、不认领，普通用户统一视为 404。
- 所有显式 conversation_id 引用先过 owner 门；越权请求零消息、零 LLM、零任务、零团队。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import login, seed_pre_p23_legacy_conversation, seed_user

from backend.app.core.errors import ConversationNotFoundError
from backend.app.main import create_app
from backend.app.storage import db as db_mod
from backend.app.storage import repos


REPO_ROOT = Path(__file__).resolve().parents[2]
_DISPLAY_NAME = "同名工程师"
_ALICE = {"username": "alice", "display_name": _DISPLAY_NAME}
_BOB = {"username": "bob", "display_name": _DISPLAY_NAME}


class _CountingGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        return {
            "content": "请继续说明需求。",
            "token_usage": None,
            "model_name": "ownership-test-stub",
            "finish_reason": "stop",
        }


@pytest.fixture()
def two_user_env(tmp_path: Path):
    """同 display_name、不同 username 的两个真实登录会话（独立 cookie jar）。"""
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as alice:
        seed_user(
            db_path,
            username=_ALICE["username"],
            display_name=_ALICE["display_name"],
            password="alice-pass-123",
        )
        seed_user(
            db_path,
            username=_BOB["username"],
            display_name=_BOB["display_name"],
            password="bob-pass-123",
        )
        login(alice, username=_ALICE["username"], password="alice-pass-123")
        bob = TestClient(app)
        login(bob, username=_BOB["username"], password="bob-pass-123")
        try:
            yield alice, bob, app, db_path
        finally:
            bob.close()


def _open_conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert response.status_code == 200, response.text
    return response.json()


def _count(app: Any, table: str) -> int:
    assert table in {"conversation_messages", "model_calls", "tasks", "teams"}
    conn = app.state.conn_factory()
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def _seed_plan(app: Any, conversation_id: str) -> None:
    conn = app.state.conn_factory()
    try:
        repos.set_conversation_recommendation(
            conn,
            conversation_id,
            {
                "decision": "orchestrate",
                "goal": "只属于会话 owner 的协作目标",
                "agents": [{"agent_id": "hello_agent", "role": "执行"}],
            },
        )
    finally:
        conn.close()


def _seed_legacy_conversation(app: Any, conversation_id: str = "conv_legacy") -> str:
    conn = app.state.conn_factory()
    try:
        seed_pre_p23_legacy_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by=_DISPLAY_NAME,
        )
        return conversation_id
    finally:
        conn.close()


def _conversation_columns(db_path: Path) -> dict[str, sqlite3.Row]:
    conn = db_mod.get_conn(db_path)
    try:
        return {row[1]: row for row in conn.execute("PRAGMA table_info(conversations)")}
    finally:
        conn.close()


def _strip_conversation_owner_column(db_path: Path) -> None:
    """把现势库重建成 migration #14 之前的 conversations 形状。"""
    conn = db_mod.get_conn(db_path)
    try:
        legacy_cols = (
            "id, agent_id, status, created_by, recommendation_json, "
            "created_at, updated_at"
        )
        conn.execute("BEGIN IMMEDIATE")
        # This helper deliberately tears down the referenced owner table to
        # recreate a pre-migration shape.  Production never drops conversations;
        # remove the cross-table hardening trigger for the fixture window and let
        # init_db recreate it after the legacy table is renamed back.
        conn.execute("DROP TRIGGER IF EXISTS trg_conversation_questions_owner_exact")
        # P2.6 event triggers also reference conversations.  This fixture has an
        # empty lifecycle ledger and deliberately reconstructs a pre-P2.6 table;
        # remove those forward guards for the fixture window so SQLite can rename
        # the legacy table, then let init_db recreate the canonical set.
        for trigger_name in db_mod._CONVERSATION_LIFECYCLE_EVENT_MANAGED_TRIGGERS:
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
        conn.execute(
            """
            CREATE TABLE conversations_legacy (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                recommendation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"INSERT INTO conversations_legacy ({legacy_cols}) "
            f"SELECT {legacy_cols} FROM conversations"
        )
        conn.execute("DROP TABLE conversations")
        conn.execute("ALTER TABLE conversations_legacy RENAME TO conversations")
        conn.execute("COMMIT")
    finally:
        conn.close()


@pytest.mark.parametrize("invalid_owner", [None, "", " \t\n"])
def test_repository_create_conversation_rejects_ownerless_runtime_rows(
    tmp_path: Path, invalid_owner: str | None
) -> None:
    """Only pre-existing migration facts may lack a stable username owner."""
    db_path = tmp_path / "ownerless-runtime-create.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    conversation_id = "conv_" + "0" * 32
    try:
        with pytest.raises(ValueError, match="created_by_username"):
            repos.create_conversation(
                conn,
                conversation_id=conversation_id,
                agent_id="guide_agent",
                created_by=_DISPLAY_NAME,
                created_by_username=invalid_owner,  # type: ignore[arg-type]
            )
        assert repos.get_conversation(conn, conversation_id) is None
    finally:
        conn.close()


def test_migration_14_adds_nullable_conversation_owner_and_is_idempotent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "migration-14.db"
    db_mod.init_db(db_path)
    fresh = _conversation_columns(db_path)
    assert "created_by_username" in fresh
    assert fresh["created_by_username"][3] == 0, "owner 列必须 nullable，legacy 行不冒充"

    conn = db_mod.get_conn(db_path)
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_pre_owner_migration",
            agent_id="guide_agent",
            created_by=_DISPLAY_NAME,
            created_by_username="alice",
        )
    finally:
        conn.close()

    _strip_conversation_owner_column(db_path)
    assert "created_by_username" not in _conversation_columns(db_path)
    db_mod.init_db(db_path)
    db_mod.init_db(db_path)
    migrated = _conversation_columns(db_path)
    assert "created_by_username" in migrated
    assert migrated["created_by_username"][3] == 0
    conn = db_mod.get_conn(db_path)
    try:
        legacy = repos.get_conversation(conn, "conv_pre_owner_migration")
        assert legacy is not None
        assert legacy["created_by_username"] is None, "不得从 display_name 猜测 legacy owner"
        with pytest.raises(sqlite3.IntegrityError, match="conversation id is required"):
            conn.execute(
                """
                INSERT INTO conversations
                    (id, agent_id, status, created_by, created_by_username,
                     recommendation_json, created_at, updated_at)
                VALUES (NULL, 'guide_agent', 'active', 'Legacy', NULL, NULL,
                        '2026-07-19T00:00:00+00:00',
                        '2026-07-19T00:00:00+00:00')
                """
            )
    finally:
        conn.close()


def test_oldest_m6_tables_converge_through_file_owner_and_message_id_alters(
    tmp_path: Path,
) -> None:
    """Accept the real M6 shape, including file_ids appended before message_id."""
    db_path = tmp_path / "oldest-m6-conversation-tables.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
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
                created_at TEXT NOT NULL
            );
            INSERT INTO conversations VALUES
                ('conv_oldest_m6', 'guide_agent', 'active', 'Legacy', NULL,
                 '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00');
            INSERT INTO conversation_messages
                (conversation_id, role, content, recommendation_json, created_at)
            VALUES
                ('conv_oldest_m6', 'user', 'legacy message', NULL,
                 '2025-01-01T00:00:01+00:00');
            """
        )
    finally:
        raw.close()

    db_mod.init_db(db_path)
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        assert db_mod._p23_identity_table_shape_witnesses(conn) == {
            "conversation_table_shape": True,
            "message_table_shape": True,
        }
        assert [
            row[1] for row in conn.execute("PRAGMA table_info(conversation_messages)")
        ][-2:] == ["file_ids", "message_id"]
        row = conn.execute(
            "SELECT content, file_ids, message_id FROM conversation_messages"
        ).fetchone()
        assert row[0:2] == ("legacy message", "[]")
        assert row[2].startswith("msg_") and len(row[2]) == 36
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("owner_clause", "table_constraint"),
    [
        ("TEXT UNIQUE", ""),
        ("TEXT CHECK (length(created_by_username) >= 3)", ""),
        ("TEXT REFERENCES users(username)", ""),
        ("TEXT COLLATE NOCASE", ""),
        ("TEXT", ", CHECK (created_by_username = lower(created_by_username))"),
        (
            "TEXT",
            ", FOREIGN KEY (created_by_username) REFERENCES users(username)",
        ),
    ],
)
def test_startup_rejects_hidden_constraints_on_conversation_owner(
    tmp_path: Path, owner_clause: str, table_constraint: str
) -> None:
    """One principal may own many conversations; owner is not a unique axis."""
    db_path = tmp_path / "owner-hidden-constraint-poison.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
            f"""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_by_username {owner_clause},
                recommendation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
                {table_constraint}
            );
            """
        )
    finally:
        raw.close()

    # PRAGMA table_xinfo alone cannot see the inline UNIQUE autoindex.  The
    # startup witness must inspect index semantics and fail before serving a DB
    # that would cap each authenticated owner at one conversation.
    with pytest.raises(sqlite3.IntegrityError, match="conversation_table_shape"):
        db_mod.init_db(db_path)

    canonical_path = tmp_path / "owner-many-conversations-canonical.db"
    db_mod.init_db(canonical_path)
    conn = db_mod.get_conn(canonical_path)
    try:
        for suffix in ("a", "b"):
            repos.create_conversation(
                conn,
                conversation_id="conv_" + suffix * 32,
                agent_id="guide_agent",
                created_by=_DISPLAY_NAME,
                created_by_username="alice",
            )
        assert conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE created_by_username = 'alice'"
        ).fetchone()[0] == 2
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("message_id_clause", "table_constraint"),
    [
        ("TEXT NOT NULL UNIQUE REFERENCES users(username)", ""),
        ("TEXT NOT NULL UNIQUE CHECK (length(message_id) = 36)", ""),
        ("TEXT NOT NULL UNIQUE COLLATE NOCASE", ""),
        ("TEXT NOT NULL UNIQUE", ", CHECK (substr(message_id, 1, 4) = 'msg_')"),
        (
            "TEXT NOT NULL UNIQUE",
            ", FOREIGN KEY (message_id) REFERENCES users(username)",
        ),
    ],
)
def test_startup_rejects_hidden_constraints_on_message_public_id(
    tmp_path: Path, message_id_clause: str, table_constraint: str
) -> None:
    db_path = tmp_path / "message-id-hidden-constraint-poison.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
            f"""
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id {message_id_clause},
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                recommendation_json TEXT,
                file_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
                {table_constraint}
            );
            """
        )
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match="message_table_shape"):
        db_mod.init_db(db_path)


def test_startup_rejects_duplicate_non_primary_conversation_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "duplicate-plain-conversation-id.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
            """
            CREATE TABLE conversations (
                id TEXT,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_by_username TEXT,
                recommendation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO conversations VALUES
                ('conv_shared', 'guide_agent', 'active', 'Alice', 'alice', NULL,
                 '2026-07-19T00:00:00+00:00', '2026-07-19T00:00:00+00:00'),
                ('conv_shared', 'guide_agent', 'active', 'Bob', 'bob', NULL,
                 '2026-07-19T00:00:00+00:00', '2026-07-19T00:00:00+00:00');
            """
        )
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match="conversation_table_shape"):
        db_mod.init_db(db_path)

    raw = sqlite3.connect(db_path)
    try:
        assert raw.execute(
            "SELECT COUNT(*) FROM conversations WHERE id = 'conv_shared'"
        ).fetchone()[0] == 2
    finally:
        raw.close()


@pytest.mark.parametrize(
    ("table", "create_sql", "witness"),
    [
        (
            "conversations",
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_by_username TEXT,
                recommendation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            ) STRICT
            """,
            "conversation_table_shape",
        ),
        (
            "conversation_messages",
            """
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                recommendation_json TEXT,
                file_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            ) STRICT
            """,
            "message_table_shape",
        ),
    ],
)
def test_startup_rejects_identity_table_suffixes(
    tmp_path: Path, table: str, create_sql: str, witness: str
) -> None:
    db_path = tmp_path / f"{table}-strict-suffix.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(create_sql)
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match=witness):
        db_mod.init_db(db_path)


@pytest.mark.parametrize(
    ("id_clause", "conversation_clause", "created_at_clause"),
    [
        ("INTEGER PRIMARY KEY", "TEXT NOT NULL", "TEXT NOT NULL"),
        ("INTEGER PRIMARY KEY AUTOINCREMENT", "TEXT", "TEXT NOT NULL"),
        (
            "INTEGER PRIMARY KEY AUTOINCREMENT",
            "TEXT NOT NULL",
            "TEXT NOT NULL COLLATE NOCASE",
        ),
    ],
)
def test_startup_rejects_noncanonical_message_identity_core(
    tmp_path: Path,
    id_clause: str,
    conversation_clause: str,
    created_at_clause: str,
) -> None:
    db_path = tmp_path / "message-core-shape-poison.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
            f"""
            CREATE TABLE conversation_messages (
                id {id_clause},
                message_id TEXT NOT NULL UNIQUE,
                conversation_id {conversation_clause},
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                recommendation_json TEXT,
                file_ids TEXT NOT NULL DEFAULT '[]',
                created_at {created_at_clause}
            );
            """
        )
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match="message_table_shape"):
        db_mod.init_db(db_path)


@pytest.mark.parametrize(
    ("table", "extra_definition", "witness"),
    [
        ("conversations", "future_required TEXT NOT NULL", "conversation_table_shape"),
        ("conversations", "future_nullable TEXT", "conversation_table_shape"),
        (
            "conversations",
            "future_generated TEXT GENERATED ALWAYS AS (created_by_username) VIRTUAL",
            "conversation_table_shape",
        ),
        (
            "conversation_messages",
            "future_default TEXT DEFAULT 'implicit'",
            "message_table_shape",
        ),
        (
            "conversation_messages",
            "CHECK (role IN ('user', 'assistant'))",
            "message_table_shape",
        ),
    ],
)
def test_startup_rejects_unregistered_identity_table_definition(
    tmp_path: Path, table: str, extra_definition: str, witness: str
) -> None:
    db_path = tmp_path / f"unregistered-definition-{table}.db"
    if table == "conversations":
        core = """
            id TEXT PRIMARY KEY NOT NULL,
            agent_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_by_username TEXT,
            recommendation_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        """
    else:
        core = """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL UNIQUE,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            recommendation_json TEXT,
            file_ids TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        """
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(f"CREATE TABLE {table} ({core}, {extra_definition})")
        if extra_definition == "future_required TEXT NOT NULL":
            with pytest.raises(sqlite3.IntegrityError, match="future_required"):
                raw.execute(
                    """
                    INSERT INTO conversations
                        (id, agent_id, status, created_by, created_by_username,
                         recommendation_json, created_at, updated_at)
                    VALUES ('conv_runtime_blocked', 'guide_agent', 'active',
                            'Alice', 'alice', NULL,
                            '2026-07-19T00:00:00+00:00',
                            '2026-07-19T00:00:00+00:00')
                    """
                )
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match=witness):
        db_mod.init_db(db_path)


@pytest.mark.parametrize(
    ("table", "create_sql", "witness"),
    [
        (
            "conversations",
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                recommendation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by_username TEXT
            )
            """,
            "conversation_table_shape",
        ),
        (
            "conversation_messages",
            """
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                recommendation_json TEXT,
                file_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE
            )
            """,
            "message_table_shape",
        ),
    ],
)
def test_startup_rejects_mixed_fresh_and_legacy_table_variant(
    tmp_path: Path, table: str, create_sql: str, witness: str
) -> None:
    """Known clauses in an unknown order/history are not a supported migration."""
    db_path = tmp_path / f"mixed-table-history-{table}.db"
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(create_sql)
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match=witness):
        db_mod.init_db(db_path)


@pytest.mark.parametrize(
    "table",
    ["conversations", "conversation_messages", "conversation_questions"],
)
def test_startup_rejects_unmanaged_trigger_on_p23_table(
    tmp_path: Path, table: str
) -> None:
    db_path = tmp_path / f"unmanaged-trigger-{table}.db"
    db_mod.init_db(db_path)
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(
            f"CREATE TRIGGER rogue_{table}_blocker BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'rogue trigger'); END"
        )
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match="required_triggers"):
        db_mod.init_db(db_path)


@pytest.mark.parametrize(
    ("table", "index_sql"),
    [
        (
            "conversations",
            "CREATE INDEX rogue_owner_expression ON conversations("
            "json_extract(created_by_username, '$'))",
        ),
        (
            "conversation_messages",
            "CREATE INDEX rogue_message_partial ON conversation_messages(content) "
            "WHERE role = 'user'",
        ),
        (
            "conversation_questions",
            "CREATE UNIQUE INDEX rogue_question_prompt ON "
            "conversation_questions(prompt)",
        ),
    ],
)
def test_startup_rejects_unmanaged_index_on_p23_table(
    tmp_path: Path, table: str, index_sql: str
) -> None:
    db_path = tmp_path / f"unmanaged-index-{table}.db"
    db_mod.init_db(db_path)
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(index_sql)
    finally:
        raw.close()

    with pytest.raises(sqlite3.IntegrityError, match="required_indexes"):
        db_mod.init_db(db_path)


def test_non_null_conversation_owner_is_immutable(tmp_path: Path) -> None:
    db_path = tmp_path / "immutable-owner.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_owned",
            agent_id="guide_agent",
            created_by=_DISPLAY_NAME,
            created_by_username="alice",
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE conversations SET created_by_username = ? WHERE id = ?",
                ("bob", "conv_owned"),
            )
        row = dict(conn.execute(
            "SELECT * FROM conversations WHERE id = ?", ("conv_owned",)
        ).fetchone())
        row["created_by_username"] = "bob"
        columns = list(row)
        with pytest.raises(sqlite3.IntegrityError, match="immutable|conflicting"):
            conn.execute(
                f"INSERT OR REPLACE INTO conversations ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
        assert repos.get_conversation(conn, "conv_owned")["created_by_username"] == "alice"
    finally:
        conn.close()


def test_conversation_identity_and_rows_survive_all_replace_delete_paths(
    tmp_path: Path,
) -> None:
    """DB truth must not depend on recursive delete-trigger behavior.

    ``UPDATE OR REPLACE`` can otherwise delete the conflicting target row before
    moving the source row onto its id.  Explicit ``rowid`` conflicts provide the
    same replacement surface even when the public id is new.
    """
    db_path = tmp_path / "immutable-conversation-identity.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        for suffix, owner in (("a", "alice"), ("b", "bob")):
            repos.create_conversation(
                conn,
                conversation_id=f"conv_{suffix * 32}",
                agent_id="guide_agent",
                created_by=_DISPLAY_NAME,
                created_by_username=owner,
            )
        before = [
            tuple(row)
            for row in conn.execute(
                "SELECT rowid, id, created_by_username FROM conversations ORDER BY id"
            )
        ]
        target_rowid = before[1][0]

        # Implicit REPLACE deletes do not run ordinary delete triggers when this
        # pragma is off.  The BEFORE UPDATE/INSERT guards must therefore catch the
        # conflict before SQLite can delete either durable row.
        conn.execute("PRAGMA recursive_triggers=OFF")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE OR REPLACE conversations SET id = ? WHERE id = ?",
                ("conv_" + "b" * 32, "conv_" + "a" * 32),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE conversations SET rowid = ? WHERE id = ?",
                (target_rowid + 100, "conv_" + "a" * 32),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                """
                INSERT OR REPLACE INTO conversations
                    (rowid, id, agent_id, status, created_by,
                     created_by_username, recommendation_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    target_rowid,
                    "conv_" + "c" * 32,
                    "guide_agent",
                    "active",
                    _DISPLAY_NAME,
                    "carol",
                    None,
                    "2026-07-19T00:00:00+00:00",
                    "2026-07-19T00:00:00+00:00",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "DELETE FROM conversations WHERE id = ?", ("conv_" + "a" * 32,)
            )

        after = [
            tuple(row)
            for row in conn.execute(
                "SELECT rowid, id, created_by_username FROM conversations ORDER BY id"
            )
        ]
        assert after == before
    finally:
        conn.close()


def test_create_and_list_use_exact_username_despite_same_display_name(two_user_env) -> None:
    alice, bob, _, _ = two_user_env
    alice_conv = _open_conversation(alice)
    bob_conv = _open_conversation(bob)

    assert alice_conv["created_by"] == bob_conv["created_by"] == _DISPLAY_NAME
    assert alice_conv["created_by_username"] == "alice"
    assert bob_conv["created_by_username"] == "bob"

    # 旧的 created_by 查询参数不可信：即使伪造/撞名，结果仍只能由 session username 决定。
    alice_rows = alice.get(
        "/api/conversations", params={"created_by": _DISPLAY_NAME}
    ).json()
    bob_rows = bob.get(
        "/api/conversations", params={"created_by": _DISPLAY_NAME}
    ).json()
    assert [row["id"] for row in alice_rows] == [alice_conv["id"]]
    assert [row["id"] for row in bob_rows] == [bob_conv["id"]]


def test_foreign_conversation_surfaces_are_uniform_404(two_user_env) -> None:
    alice, bob, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    _seed_plan(app, conversation_id)

    conn = app.state.conn_factory()
    try:
        repos.record_model_call(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            model_profile="reasoning",
            model_name="seed",
            status="success",
        )
        repos.create_task(
            conn,
            task_id="task_private_member",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name=None,
            created_by=_DISPLAY_NAME,
            created_by_username="alice",
            conversation_id=conversation_id,
        )
    finally:
        conn.close()

    assert bob.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert bob.get(f"/api/conversations/{conversation_id}/model_calls").status_code == 404
    assert bob.get(f"/api/conversations/{conversation_id}/tasks").status_code == 404
    assert bob.post(
        f"/api/conversations/{conversation_id}/conclude",
        json={"lifecycle_revision": 0},
    ).status_code == 404


def test_foreign_post_is_404_before_llm_and_has_zero_side_effects(two_user_env) -> None:
    alice, bob, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    gateway = _CountingGateway()
    app.state.conversation_service.model_gateway = gateway
    before_messages = _count(app, "conversation_messages")
    before_calls = _count(app, "model_calls")

    response = bob.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "试图越权触发模型"},
    )

    assert response.status_code == 404
    assert gateway.calls == []
    assert _count(app, "conversation_messages") == before_messages
    assert _count(app, "model_calls") == before_calls


def test_service_layer_rejects_foreign_principal_before_llm(two_user_env) -> None:
    alice, _, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    gateway = _CountingGateway()
    app.state.conversation_service.model_gateway = gateway

    with pytest.raises(ConversationNotFoundError):
        app.state.conversation_service.get(conversation_id, principal=_BOB)
    with pytest.raises(ConversationNotFoundError):
        app.state.conversation_service.post_message(
            conversation_id=conversation_id,
            content="绕过 API 直调 service",
            principal=_BOB,
        )
    assert gateway.calls == []


def test_legacy_null_owner_is_invisible_and_unusable(two_user_env) -> None:
    alice, _, app, _ = two_user_env
    conversation_id = _seed_legacy_conversation(app)
    _seed_plan(app, conversation_id)
    gateway = _CountingGateway()
    app.state.conversation_service.model_gateway = gateway

    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert conversation_id not in {
        row["id"] for row in alice.get("/api/conversations").json()
    }
    assert (
        alice.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "legacy 不得猜 owner"},
        ).status_code
        == 404
    )
    assert gateway.calls == []

    before_tasks = _count(app, "tasks")
    task = alice.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": "legacy"},
            "conversation_id": conversation_id,
        },
    )
    assert task.status_code == 404
    assert _count(app, "tasks") == before_tasks

    before_teams = _count(app, "teams")
    team = alice.post(
        "/api/teams", json={"name": "legacy", "conversation_id": conversation_id}
    )
    assert team.status_code == 404
    assert _count(app, "teams") == before_teams


def test_foreign_single_task_conversation_reference_is_404_and_zero_write(
    two_user_env,
) -> None:
    alice, bob, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    before = _count(app, "tasks")
    response = bob.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": "foreign-single"},
            "conversation_id": conversation_id,
        },
    )
    assert response.status_code == 404
    assert _count(app, "tasks") == before


def test_foreign_batch_conversation_reference_is_404_and_zero_write(
    two_user_env,
) -> None:
    alice, bob, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    before = _count(app, "tasks")
    response = bob.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [{"agent_id": "hello_agent", "inputs": {"name": "foreign-batch"}}],
        },
    )
    assert response.status_code == 404
    assert _count(app, "tasks") == before


def test_foreign_task_list_conversation_filter_is_404(two_user_env) -> None:
    alice, bob, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id="task_foreign_list",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name=None,
            created_by=_DISPLAY_NAME,
            created_by_username="alice",
            conversation_id=conversation_id,
        )
    finally:
        conn.close()

    own = alice.get("/api/tasks", params={"conversation_id": conversation_id})
    assert own.status_code == 200
    assert [row["id"] for row in own.json()] == ["task_foreign_list"]
    assert (
        bob.get("/api/tasks", params={"conversation_id": conversation_id}).status_code
        == 404
    )


def test_foreign_team_source_conversation_is_404_and_zero_write(two_user_env) -> None:
    alice, bob, app, _ = two_user_env
    conversation_id = _open_conversation(alice)["id"]
    _seed_plan(app, conversation_id)
    before = _count(app, "teams")

    response = bob.post(
        "/api/teams",
        json={"name": "越权团队", "conversation_id": conversation_id},
    )

    assert response.status_code == 404
    assert _count(app, "teams") == before


def test_team_summon_foreign_target_conversation_is_404_and_zero_write(
    two_user_env,
) -> None:
    alice, bob, app, _ = two_user_env
    alice_conversation_id = _open_conversation(alice)["id"]
    bob_conversation_id = _open_conversation(bob)["id"]
    _seed_plan(app, bob_conversation_id)
    saved = bob.post(
        "/api/teams",
        json={"name": "Bob 自有团队", "conversation_id": bob_conversation_id},
    )
    assert saved.status_code == 200, saved.text
    before = _count(app, "tasks")

    response = bob.post(
        f"/api/teams/{saved.json()['id']}/summon",
        json={
            "conversation_id": alice_conversation_id,
            # 故意让席位也非法：owner 404 必须先于 team/registry/material 422，
            # 否则 foreign conversation 可作为侧信道观察团队现势。
            "items": [{"seq": 999, "inputs": {"name": "foreign-target"}}],
        },
    )

    assert response.status_code == 404
    assert _count(app, "tasks") == before
