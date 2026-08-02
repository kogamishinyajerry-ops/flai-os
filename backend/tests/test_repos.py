"""storage/repos.py 仓储函数测试：全部用 tmp_path 的 db，绝不碰真实 data/。

覆盖：建任务、非法转移抛错、claim 原子性（两次 claim 拿不到同一任务）、
append_event 对非法 event_type/level 必抛（反例 witness）、文件 CRUD、
tool_run/model_call/sample 落库回读、九表全建成（sqlite_master 对账）。
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

import pytest

from backend.app.auth.service import AuthenticatedSessionContext
from backend.app.core.errors import IllegalTransitionError, TaskNotFoundError
from backend.app.governance.signer_provenance import SignerContext
from backend.app.storage import db as db_mod
from backend.app.storage import repos


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "flai_os_test.db"
    db_mod.init_db(db_path)
    c = db_mod.get_conn(db_path)
    yield c
    c.close()


def _new_task(conn, **overrides):
    fields = dict(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="测试任务",
        created_by="tester",
        inputs={"name": "张三"},
        input_file_ids=[],
        metadata={},
    )
    fields.update(overrides)
    return repos.create_task(conn, **fields)


# ── init_db 九表全建成 ───────────────────────────────────────────────

def test_init_db_creates_all_nine_tables(conn) -> None:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    names = {r["name"] for r in rows}
    expected = {
        "agents", "agent_versions", "tasks", "task_events", "files",
        "feedback", "tool_runs", "model_calls", "samples",
    }
    assert expected <= names, f"缺表：{expected - names}"


def test_init_db_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "idempotent.db"
    db_mod.init_db(db_path)
    db_mod.init_db(db_path)  # 第二次调用不应报错


def test_init_db_creates_required_indexes(conn) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    names = {row["name"] for row in rows}
    expected = {
        "idx_task_events_task_id",
        "idx_tool_runs_task_id",
        "idx_model_calls_task_id",
        "idx_model_calls_conversation_id",
        "idx_samples_task_id",
        "idx_feedback_task_id",
        "idx_conversation_messages_conversation_id",
        "idx_tasks_conversation_id",
        "idx_tasks_agent_id",
        "idx_tasks_status_created_at",
    }
    assert expected <= names, f"缺索引：{expected - names}"


# ── conversations.created_by_username（持久 owner 证明）───────────────


def test_fresh_conversations_owner_username_is_nullable_without_default(conn) -> None:
    columns = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(conversations)")
    }

    owner = columns["created_by_username"]
    assert owner["notnull"] == 0
    assert owner["dflt_value"] is None


_LEGACY_CONVERSATIONS_DDL_WITHOUT_OWNER = """
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    recommendation_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def test_conversation_owner_migration_keeps_legacy_rows_unproven(tmp_path) -> None:
    db_path = tmp_path / "legacy-conversations.db"
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.execute(_LEGACY_CONVERSATIONS_DDL_WITHOUT_OWNER)
        legacy.execute(
            "INSERT INTO conversations "
            "(id, agent_id, status, created_by, recommendation_json, created_at, updated_at) "
            "VALUES ('conv_legacy', 'guide_agent', 'active', '测试工程师', NULL, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
    finally:
        legacy.close()

    db_mod.init_db(db_path)
    migrated = db_mod.get_conn(db_path)
    try:
        columns = {
            row["name"]: row
            for row in migrated.execute("PRAGMA table_info(conversations)")
        }
        assert columns["created_by_username"]["dflt_value"] is None
        assert repos.get_conversation_owner_username(migrated, "conv_legacy") is None
        public = repos.get_conversation(migrated, "conv_legacy")
        assert public is not None
        assert public["created_by"] == "测试工程师"
        assert "created_by_username" not in public
    finally:
        migrated.close()

    db_mod.init_db(db_path)


def test_conversation_owner_is_internal_but_raw_lookup_is_available(conn) -> None:
    created = repos.create_conversation(
        conn,
        conversation_id="conv_owner_projection",
        agent_id="guide_agent",
        created_by="测试工程师",
        created_by_username="test_engineer",
    )

    assert "created_by_username" not in created
    assert "created_by_username" not in repos.get_conversation(
        conn, "conv_owner_projection"
    )
    assert "created_by_username" not in repos.list_conversations(conn)[0]
    assert (
        repos.get_conversation_owner_username(conn, "conv_owner_projection")
        == "test_engineer"
    )
    assert repos.get_conversation_owner_username(conn, "conv_missing") is None


@pytest.mark.parametrize(
    ("initial_owner", "replacement_owner"),
    [
        (None, "test_engineer"),
        ("test_engineer", None),
        ("test_engineer", "another_engineer"),
    ],
    ids=["null-to-value", "value-to-null", "value-to-other-value"],
)
def test_conversation_owner_username_is_immutable_for_every_transition(
    conn, initial_owner: str | None, replacement_owner: str | None
) -> None:
    conversation_id = f"conv_owner_immutable_{uuid.uuid4().hex}"
    repos.create_conversation(
        conn,
        conversation_id=conversation_id,
        agent_id="guide_agent",
        created_by="测试工程师",
        created_by_username=initial_owner,
    )

    with pytest.raises(sqlite3.IntegrityError, match="created_by_username is immutable"):
        conn.execute(
            "UPDATE conversations SET created_by_username = ? WHERE id = ?",
            (replacement_owner, conversation_id),
        )

    assert (
        repos.get_conversation_owner_username(conn, conversation_id) == initial_owner
    )


# ── tasks ──────────────────────────────────────────────────────────────

def test_create_task_defaults_to_created_status(conn) -> None:
    task = _new_task(conn)
    assert task["status"] == "created"
    assert task["input_file_ids"] == []
    assert task["output_file_ids"] == []
    assert task["inputs"] == {"name": "张三"}
    assert task["metadata"] == {}
    assert task["started_at"] is None
    assert task["finished_at"] is None


def test_get_task_missing_returns_none(conn) -> None:
    assert repos.get_task(conn, "no_such_task") is None


# ── 迁移 #9：created_by_username（不可变身份轴，批C 个人贡献归因前置）────────


def test_fresh_db_has_created_by_username_column(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    assert "created_by_username" in cols


def test_create_task_stores_and_projects_username(conn) -> None:
    task = _new_task(conn, created_by="张三", created_by_username="zhangsan")
    # 写入即回读；投影自动带出（_decode_task 是 dict(row)）
    assert task["created_by_username"] == "zhangsan"
    assert repos.get_task(conn, task["id"])["created_by_username"] == "zhangsan"
    # display_name 仍走 created_by，两轴并存不互相污染
    assert task["created_by"] == "张三"


def test_create_task_username_defaults_to_none(conn) -> None:
    """省略 created_by_username（如 eval 系统建任务、无人类创建者）→ 留 NULL，
    绝不用 created_by（display_name）冒充 username 身份。"""
    task = _new_task(conn, origin="eval")
    assert task["created_by_username"] is None


# pre-迁移#9 的 tasks 表形态（=迁移 #8 era：有 data_classification，无
# created_by_username）。显式建缺列的 legacy 表来触发迁移路径，**不用
# DROP COLUMN**（那要 SQLite≥3.35，超内网部署下限——ADR-0013 R2 同款教训）。
_LEGACY_TASKS_DDL_PRE_9 = """
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    input_file_ids TEXT NOT NULL DEFAULT '[]',
    output_file_ids TEXT NOT NULL DEFAULT '[]',
    inputs_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    conversation_id TEXT,
    origin TEXT NOT NULL DEFAULT 'user',
    data_classification TEXT
)
"""


def test_migration_9_adds_column_to_legacy_db_existing_rows_null(tmp_path) -> None:
    """存量库（无 created_by_username 列）再跑 init_db → 补列，存量行留 NULL
    （username 是自报时代之后才有的追溯，不可从 display_name 反推——同迁移 #6
    uploaded_by 的「不冒充追溯」口径）。补列幂等，重复 init_db 安全。"""
    db_path = tmp_path / "legacy.db"
    # 先手建 pre-#9 的 tasks 表 + 插一行老任务，再让 init_db 走迁移补列。
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.execute(_LEGACY_TASKS_DDL_PRE_9)
        legacy.execute(
            "INSERT INTO tasks (id, agent_id, agent_version, name, status, created_by,"
            " created_at, updated_at) VALUES"
            " ('old-1','hello_agent','0.1.0','老任务','completed','历史用户',"
            " '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
        )
        legacy.commit()
        cols_before = {row[1] for row in legacy.execute("PRAGMA table_info(tasks)")}
        assert "created_by_username" not in cols_before
    finally:
        legacy.close()
    # init_db：CREATE TABLE IF NOT EXISTS 跳过已存在的 tasks，迁移 #9 补列。
    db_mod.init_db(db_path)
    c2 = db_mod.get_conn(db_path)
    try:
        cols_after = {row[1] for row in c2.execute("PRAGMA table_info(tasks)")}
        assert "created_by_username" in cols_after
        old = repos.get_task(c2, "old-1")
        assert old["created_by_username"] is None  # 存量行不冒充追溯
        assert old["created_by"] == "历史用户"      # display_name 原样保留
    finally:
        c2.close()
    # 幂等：再跑 init_db 不炸（列已存在，探测跳过）
    db_mod.init_db(db_path)


# ── 迁移 #14：promotion 签发者来源（ADR-0019）───────────────────────


_LEGACY_PROMOTIONS_DDL_PRE_14 = """
CREATE TABLE promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    from_maturity TEXT NOT NULL,
    to_maturity TEXT NOT NULL,
    eval_run_id TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    confirmations_json TEXT NOT NULL,
    confirmed_by TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def test_migration_14_marks_legacy_promotion_without_identity_inference(
    tmp_path,
) -> None:
    """历史 confirmed_by 只是显示名，迁移不得据此猜 user/session 身份。"""
    db_path = tmp_path / "legacy-promotions.db"
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.execute(_LEGACY_PROMOTIONS_DDL_PRE_14)
        legacy.execute(
            "CREATE TABLE users ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " username TEXT NOT NULL UNIQUE,"
            " display_name TEXT NOT NULL,"
            " password_hash TEXT NOT NULL,"
            " is_active INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL"
            ")"
        )
        legacy.execute(
            "INSERT INTO users"
            " (username, display_name, password_hash, is_active, created_at)"
            " VALUES ('unique-user', '历史签发人', 'not-a-real-hash', 1,"
            " '2026-01-01T00:00:00+00:00')"
        )
        legacy.execute(
            "INSERT INTO promotions"
            " (agent_id, agent_version, from_maturity, to_maturity, eval_run_id,"
            " checks_json, confirmations_json, confirmed_by, created_at)"
            " VALUES ('legacy-agent', '0.1.0', 'L0', 'L1', 'eval-old',"
            " '{}', '{}', '历史签发人', '2026-01-02T00:00:00+00:00')"
        )
        legacy.commit()
        cols_before = {
            row[1] for row in legacy.execute("PRAGMA table_info(promotions)")
        }
        assert "signer_source" not in cols_before
    finally:
        legacy.close()

    db_mod.init_db(db_path)
    migrated = db_mod.get_conn(db_path)
    try:
        rows = repos.list_promotions(migrated, agent_id="legacy-agent")
        assert len(rows) == 1
        row = rows[0]
        assert row["confirmed_by"] == "历史签发人"
        assert row["signer_source"] == "legacy_unverified"
        assert row["signer_user_id"] is None
        assert row["signer_username"] is None
        assert row["signer_session_hash"] is None
    finally:
        migrated.close()

    db_mod.init_db(db_path)


def test_migration_14_survives_rival_alter_mid_flight(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API/worker 并发启动时，来源列迁移必须由同一 BEGIN IMMEDIATE 串行化。"""
    import threading

    db_path = tmp_path / "legacy-promotions-race.db"
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.execute(_LEGACY_PROMOTIONS_DDL_PRE_14)
    finally:
        legacy.close()

    about_to_alter = threading.Event()
    rival_done = threading.Event()
    real_get_conn = db_mod.get_conn

    def instrumented_get_conn(path):
        conn = real_get_conn(path)

        def trace(statement: str) -> None:
            if "ALTER TABLE promotions ADD COLUMN signer_source" in statement:
                about_to_alter.set()
                rival_done.wait(timeout=10)

        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(db_mod, "get_conn", instrumented_get_conn)
    errors: list[Exception] = []

    def migrate() -> None:
        try:
            db_mod.init_db(db_path)
        except Exception as exc:  # 线程边界：主线程断言精确结果
            errors.append(exc)

    thread = threading.Thread(target=migrate)
    thread.start()
    assert about_to_alter.wait(timeout=10), "迁移未走到 signer_source ALTER"

    rival = sqlite3.connect(
        str(db_path),
        isolation_level=None,
        timeout=1.0,
    )
    try:
        rival.execute(
            "ALTER TABLE promotions ADD COLUMN signer_source TEXT"
            " NOT NULL DEFAULT 'legacy_unverified'"
        )
    except sqlite3.OperationalError:
        pass  # 正确实现：loser 已持 BEGIN IMMEDIATE 写锁
    finally:
        rival.close()
        rival_done.set()

    thread.join(timeout=15)
    assert not thread.is_alive()
    assert errors == []
    check = sqlite3.connect(str(db_path))
    check.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in check.execute("PRAGMA table_info(promotions)")}
    finally:
        check.close()
    assert {
        "signer_source",
        "signer_user_id",
        "signer_username",
        "signer_session_hash",
    } <= columns


def test_record_promotion_rejects_fabricated_authenticated_signer(conn) -> None:
    """形状正确的手造身份不能绕过 auth_sessions 精确复核。"""
    fabricated = SignerContext.from_authenticated_session(
        AuthenticatedSessionContext(
            token_hash="0" * 64,
            user_id=4242,
            username="forged",
            display_name="伪造签发人",
            user_created_at="2026-01-01T00:00:00+00:00",
            session_created_at="2026-01-01T00:00:00+00:00",
            expires_at="2999-01-01T00:00:00+00:00",
        )
    )
    result = repos.record_promotion(
        conn,
        agent_id="forged-agent",
        agent_version="0.1.0",
        from_maturity="L0",
        to_maturity="L1",
        eval_run_id="eval-forged",
        checks={},
        confirmations={"exception_paths_handled": True},
        signer=fabricated,
    )
    assert result is None
    assert conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0] == 0


def test_record_promotion_rejects_naive_verification_clock(
    conn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """签发时点必须是带时区 UTC 语义；naive 墙钟不能生成可审计证明。"""
    from backend.app.governance import signer_provenance

    monkeypatch.setattr(
        signer_provenance,
        "current_auth_time",
        lambda: datetime(2026, 7, 27, 12, 0, 0),
    )
    result = repos.record_promotion(
        conn,
        agent_id="naive-clock-agent",
        agent_version="0.1.0",
        from_maturity="L0",
        to_maturity="L1",
        eval_run_id="eval-naive-clock",
        checks={},
        confirmations={"exception_paths_handled": True},
        signer=SignerContext.from_server_cli("服务器运维"),
    )
    assert result is None
    assert conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0] == 0


def test_list_tasks_filters_by_agent_and_status(conn) -> None:
    t1 = _new_task(conn, agent_id="agent_a")
    t2 = _new_task(conn, agent_id="agent_b")
    repos.set_task_status(conn, t1["id"], "queued")

    only_a = repos.list_tasks(conn, agent_id="agent_a")
    assert {t["id"] for t in only_a} == {t1["id"]}

    only_queued = repos.list_tasks(conn, status="queued")
    assert {t["id"] for t in only_queued} == {t1["id"]}

    both = repos.list_tasks(conn)
    assert {t["id"] for t in both} == {t1["id"], t2["id"]}


def test_set_task_status_legal_chain_fills_timestamps(conn) -> None:
    task = _new_task(conn)
    task = repos.set_task_status(conn, task["id"], "queued")
    assert task["started_at"] is None

    task = repos.set_task_status(conn, task["id"], "validating")
    task = repos.set_task_status(conn, task["id"], "running")
    assert task["started_at"] is not None
    assert task["finished_at"] is None

    task = repos.set_task_status(conn, task["id"], "analyzing")
    task = repos.set_task_status(conn, task["id"], "completed", )
    assert task["status"] == "completed"
    assert task["finished_at"] is not None


def test_set_task_status_illegal_transition_raises(conn) -> None:
    task = _new_task(conn)  # created
    with pytest.raises(IllegalTransitionError):
        repos.set_task_status(conn, task["id"], "running")


def test_set_task_status_missing_task_raises(conn) -> None:
    with pytest.raises(TaskNotFoundError):
        repos.set_task_status(conn, "ghost_task", "queued")


def test_set_task_status_records_error_message_on_failure(conn) -> None:
    task = _new_task(conn)
    task = repos.set_task_status(conn, task["id"], "queued")
    task = repos.set_task_status(conn, task["id"], "validating")
    task = repos.set_task_status(conn, task["id"], "failed", error_message="输入校验失败：缺 name 字段")
    assert task["status"] == "failed"
    assert task["error_message"] == "输入校验失败：缺 name 字段"
    assert task["finished_at"] is not None


def test_set_task_outputs(conn) -> None:
    task = _new_task(conn)
    updated = repos.set_task_outputs(conn, task["id"], ["file_001", "file_002"])
    assert updated["output_file_ids"] == ["file_001", "file_002"]


# ── claim_next_queued 原子性 ─────────────────────────────────────────

def test_claim_next_queued_returns_none_when_empty(conn) -> None:
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        assert repos.claim_next_queued(conn) is None
    finally:
        conn.set_trace_callback(None)

    normalized = [" ".join(statement.upper().split()) for statement in statements]
    assert any(
        statement.startswith("SELECT 1 FROM TASKS WHERE STATUS = 'QUEUED' AND ORIGIN = 'USER' LIMIT 1")
        for statement in normalized
    )
    assert not any(statement.startswith("BEGIN IMMEDIATE") for statement in normalized)


def test_claim_next_queued_picks_fifo_and_transitions_to_validating(conn) -> None:
    t1 = _new_task(conn)
    repos.set_task_status(conn, t1["id"], "queued")

    claimed = repos.claim_next_queued(conn)
    assert claimed is not None
    assert claimed["id"] == t1["id"]
    assert claimed["status"] == "validating"


def test_claim_probe_hit_but_rival_claims_before_lock_returns_none(conn) -> None:
    """前置探测只用于避锁；探测后被对手抢先时，锁内复查仍是唯一裁决。"""
    task = _new_task(conn)
    repos.set_task_status(conn, task["id"], "queued")

    db_path = conn.execute("PRAGMA database_list").fetchone()["file"]
    rival = db_mod.get_conn(db_path)
    probe_seen = False
    interposed = False
    callback_errors: list[Exception] = []
    rival_claims: list[dict | None] = []

    def trace(statement: str) -> None:
        nonlocal probe_seen, interposed
        normalized = " ".join(statement.upper().split())
        if normalized.startswith("SELECT 1 FROM TASKS WHERE STATUS = 'QUEUED' AND ORIGIN = 'USER' LIMIT 1"):
            probe_seen = True
        elif normalized.startswith("BEGIN IMMEDIATE") and probe_seen and not interposed:
            # victim 尚未真正执行 BEGIN；此刻让 rival 完整拾取并提交，确定性复现
            # “探测命中、拿锁前已被抢先”的竞态窗口。
            interposed = True
            try:
                rival_claims.append(repos.claim_next_queued(rival))
            except Exception as exc:  # noqa: BLE001 - trace 回调异常会被 sqlite 吞掉，显式留待断言
                callback_errors.append(exc)

    conn.set_trace_callback(trace)
    try:
        claimed = repos.claim_next_queued(conn)
    finally:
        conn.set_trace_callback(None)
        rival.close()

    assert probe_seen is True
    assert interposed is True
    assert callback_errors == []
    assert len(rival_claims) == 1
    assert rival_claims[0] is not None and rival_claims[0]["id"] == task["id"]
    assert claimed is None
    assert repos.get_task(conn, task["id"])["status"] == "validating"


def test_second_claim_does_not_get_same_task(conn) -> None:
    """claim 原子性核心断言：单个 queued 任务被拾取后，第二次 claim 拿不到它。"""
    t1 = _new_task(conn)
    repos.set_task_status(conn, t1["id"], "queued")

    first = repos.claim_next_queued(conn)
    second = repos.claim_next_queued(conn)

    assert first is not None
    assert first["id"] == t1["id"]
    assert second is None  # 没有别的 queued 任务了，且不会重复拾取同一条


def test_two_queued_tasks_claimed_are_distinct(conn) -> None:
    t1 = _new_task(conn)
    t2 = _new_task(conn)
    repos.set_task_status(conn, t1["id"], "queued")
    repos.set_task_status(conn, t2["id"], "queued")

    first = repos.claim_next_queued(conn)
    second = repos.claim_next_queued(conn)
    third = repos.claim_next_queued(conn)

    assert first is not None and second is not None
    assert first["id"] != second["id"]
    assert {first["id"], second["id"]} == {t1["id"], t2["id"]}
    assert third is None


# ── task_events ──────────────────────────────────────────────────────

def test_append_event_and_list_events_roundtrip(conn) -> None:
    task = _new_task(conn)
    e1 = repos.append_event(
        conn, task_id=task["id"], agent_id="hello_agent",
        event_type="task_created", level="info", message="任务已创建",
        payload={"foo": "bar"},
    )
    e2 = repos.append_event(
        conn, task_id=task["id"],
        event_type="task_failed", level="error", message="失败了",
    )
    assert e1["event_type"] == "task_created"
    assert e1["payload"] == {"foo": "bar"}
    assert e1["agent_id"] == "hello_agent"

    events = repos.list_events(conn, task["id"])
    assert [e["event_type"] for e in events] == ["task_created", "task_failed"]
    assert events[1]["payload"] == {}  # 未传 payload 默认为空 dict


def test_append_event_response_does_not_leak_sqlite_autoincrement_id(conn) -> None:
    """P1-2/P1-3：对外唯一键=event_id，sqlite 自增主键 id 是内部实现细节，
    append_event/list_events 的返回 dict 都不应带出 id 键（event.schema.json
    additionalProperties=false 也不认识这个字段）。
    """
    task = _new_task(conn)
    created = repos.append_event(
        conn, task_id=task["id"], event_type="task_created", level="info", message="任务已创建",
    )
    assert "id" not in created
    assert created["event_id"]

    listed = repos.list_events(conn, task["id"])
    assert all("id" not in e for e in listed)


def test_append_event_invalid_event_type_raises_value_error(conn) -> None:
    """反例 witness：event_type 不在 event.schema.json 枚举内必须炸。"""
    task = _new_task(conn)
    with pytest.raises(ValueError):
        repos.append_event(
            conn, task_id=task["id"], event_type="not_a_real_event_type",
            level="info", message="不应该写进去",
        )
    assert repos.list_events(conn, task["id"]) == []  # 校验失败不应留下脏事件


def test_append_event_invalid_level_raises_value_error(conn) -> None:
    """反例 witness：level 不在 info/warning/error 枚举内必须炸。"""
    task = _new_task(conn)
    with pytest.raises(ValueError):
        repos.append_event(
            conn, task_id=task["id"], event_type="task_created",
            level="fatal", message="不合法的 level",
        )
    assert repos.list_events(conn, task["id"]) == []


def test_append_event_empty_message_rejected(conn) -> None:
    """message 是 minLength=1，空字符串必须被契约咬住。"""
    task = _new_task(conn)
    with pytest.raises(ValueError):
        repos.append_event(
            conn, task_id=task["id"], event_type="task_created",
            level="info", message="",
        )


# ── files ──────────────────────────────────────────────────────────────

def test_create_file_and_get_file_roundtrip(conn) -> None:
    task = _new_task(conn)
    file_id = f"file_{uuid.uuid4().hex[:8]}"
    created = repos.create_file(
        conn, file_id=file_id, task_id=task["id"], kind="input",
        filename="a.csv", path="/data/uploads/a.csv", size_bytes=123, sha256="deadbeef",
        classification="internal",
    )
    assert created["id"] == file_id
    fetched = repos.get_file(conn, file_id)
    assert fetched == created


def test_uploaded_file_projects_stable_owner_username_separately_from_display_name(
    conn,
) -> None:
    file_id = f"file_{uuid.uuid4().hex[:8]}"

    created = repos.create_file(
        conn,
        file_id=file_id,
        kind="input",
        filename="owned.csv",
        path="/data/uploads/owned.csv",
        size_bytes=12,
        sha256="a" * 64,
        classification="internal",
        uploaded_by="同名工程师",
        owner_username="bob",
    )

    assert created["owner_username"] == "bob"
    assert created["uploaded_by"] == "同名工程师"
    assert repos.get_file(conn, file_id)["owner_username"] == "bob"
    assert repos.list_files_by_ids(conn, [file_id])[0]["owner_username"] == "bob"


def test_uploaded_file_owner_check_is_exact_and_fails_closed(conn) -> None:
    file_id = f"file_{uuid.uuid4().hex[:8]}"
    repos.create_file(
        conn,
        file_id=file_id,
        kind="input",
        filename="bob.csv",
        path="/data/uploads/bob.csv",
        size_bytes=3,
        sha256="b" * 64,
        classification="internal",
        uploaded_by="Bob",
        owner_username="bob",
    )

    assert repos.file_is_owned_by_username(conn, file_id, "bob") is True
    assert repos.file_is_owned_by_username(conn, file_id, "alice") is False
    assert repos.file_is_owned_by_username(conn, file_id, "") is False
    assert repos.file_is_owned_by_username(conn, "missing-file", "bob") is False


def test_uploaded_file_owner_username_cannot_be_rewritten(conn) -> None:
    file_id = f"file_{uuid.uuid4().hex[:8]}"
    repos.create_file(
        conn,
        file_id=file_id,
        kind="input",
        filename="immutable.csv",
        path="/data/uploads/immutable.csv",
        size_bytes=5,
        sha256="c" * 64,
        classification="internal",
        uploaded_by="Bob",
        owner_username="bob",
    )

    with pytest.raises(sqlite3.IntegrityError, match="owner_username is immutable"):
        conn.execute(
            "UPDATE files SET owner_username = ? WHERE id = ?",
            ("alice", file_id),
        )
    assert repos.get_file(conn, file_id)["owner_username"] == "bob"


def test_file_owner_migration_keeps_legacy_rows_unattributed(tmp_path) -> None:
    db_path = tmp_path / "legacy-files.db"
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.execute(
            """
            CREATE TABLE files (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                kind TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                classification TEXT NOT NULL DEFAULT 'internal',
                uploaded_by TEXT
            )
            """
        )
        legacy.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-file",
                None,
                "input",
                "legacy.txt",
                "/legacy/legacy.txt",
                1,
                "d" * 64,
                "2026-01-01T00:00:00+00:00",
                "internal",
                "历史工程师",
            ),
        )
    finally:
        legacy.close()

    db_mod.init_db(db_path)
    db_mod.init_db(db_path)

    migrated = db_mod.get_conn(db_path)
    try:
        assert "owner_username" in {
            row[1] for row in migrated.execute("PRAGMA table_info(files)")
        }
        assert repos.get_file(migrated, "legacy-file")["owner_username"] is None
        assert (
            repos.file_is_owned_by_username(migrated, "legacy-file", "历史工程师")
            is False
        )
    finally:
        migrated.close()


def test_get_file_missing_returns_none(conn) -> None:
    assert repos.get_file(conn, "no_such_file") is None


# ── tool_runs / model_calls / samples ───────────────────────────────

def test_record_and_list_tool_run(conn) -> None:
    task = _new_task(conn)
    run = repos.record_tool_run(
        conn, task_id=task["id"], tool_id="mock_echo", tool_version="0.1.0",
        mock=True, status="success", input_json={"x": 1}, output_json={"y": 2},
        started_at="2026-07-08T00:00:00+00:00", finished_at="2026-07-08T00:00:01+00:00",
    )
    assert run["mock"] is True
    assert run["input"] == {"x": 1}
    assert run["output"] == {"y": 2}

    runs = repos.list_tool_runs(conn, task["id"])
    assert len(runs) == 1
    assert runs[0]["tool_id"] == "mock_echo"


def test_record_and_list_model_call(conn) -> None:
    task = _new_task(conn)
    call = repos.record_model_call(
        conn, task_id=task["id"], agent_id="hello_agent", model_profile="reasoning",
        status="failed", error_message="缺少 env FLAI_LLM_API_KEY",
    )
    assert call["status"] == "failed"
    assert call["token_usage"] is None

    calls = repos.list_model_calls(conn, task["id"])
    assert len(calls) == 1
    assert calls[0]["model_profile"] == "reasoning"


def test_record_and_list_sample(conn) -> None:
    task = _new_task(conn)
    sample = repos.record_sample(
        conn, task_id=task["id"], agent_id="hello_agent", agent_version="0.1.0",
        input_json={"name": "张三"}, output_json={"greeting": "你好，张三"},
        accepted_by_engineer=True, classification="internal",
    )
    assert sample["input"] == {"name": "张三"}
    assert sample["accepted_by_engineer"] is True

    samples = repos.list_samples(conn, task["id"])
    assert len(samples) == 1


def test_list_tasks_filters_by_created_by_username(conn):
    # 三条：alice 两条（含一条 eval origin）、bob 一条、无归因一条（None）
    from backend.app.storage import repos
    repos.create_task(conn, task_id="t-a1", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Alice", created_by_username="alice")
    repos.create_task(conn, task_id="t-a2", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Alice", created_by_username="alice", origin="eval")
    repos.create_task(conn, task_id="t-b1", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Bob", created_by_username="bob")
    repos.create_task(conn, task_id="t-legacy", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Legacy")  # created_by_username 省略=None

    alice = repos.list_tasks(conn, created_by_username="alice")
    assert {t["id"] for t in alice} == {"t-a1", "t-a2"}  # 精确，不含 bob/legacy

    bob = repos.list_tasks(conn, created_by_username="bob")
    assert {t["id"] for t in bob} == {"t-b1"}

    # None 归因行不被任何 username 误计（NULL != 任何值）
    assert repos.list_tasks(conn, created_by_username="legacy") == []

    # None 参数=不过滤，四条全回
    assert len(repos.list_tasks(conn, created_by_username=None)) == 4
