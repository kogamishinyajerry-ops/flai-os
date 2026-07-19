"""判断资产化存储合同：机器顾问候选与人工终裁物理隔离、只追加、可精确配对。"""

from __future__ import annotations

import sqlite3

import pytest

from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.storage.review_schema import (
    JUDGMENT_SCHEMA_WITNESS_KEYS,
    judgment_required_index_names,
    judgment_required_trigger_names,
    judgment_schema_witnesses,
)


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "judgment.db"
    init_db(db_path)
    connection = get_conn(db_path)
    yield connection
    connection.close()


def _task(conn: sqlite3.Connection, task_id: str = "task_judgment") -> dict:
    return repos.create_task(
        conn,
        task_id=task_id,
        agent_id="reviewed_agent",
        agent_version="1.0.0",
        name="待判断任务",
        created_by="创建工程师",
        created_by_username="creator",
        inputs={},
        input_file_ids=[],
        metadata={},
    )


def _model_call(conn: sqlite3.Connection, task_id: str) -> dict:
    return repos.record_model_call(
        conn,
        task_id=task_id,
        agent_id="r0_review_advisor",
        model_profile="review",
        model_name="model-a",
        status="success",
        response_summary="发现证据不足",
    )


def _to_waiting_review(conn: sqlite3.Connection, task_id: str) -> None:
    for status in ("queued", "validating", "running", "waiting_review"):
        repos.set_task_status(conn, task_id, status)


def test_machine_advice_is_recorded_as_candidate_not_human_action(conn) -> None:
    """机器输出只使用 clear/concerns/abstain，不借用 approve/reject 人签词汇。"""
    task = _task(conn)
    call = _model_call(conn, task["id"])

    advice = repos.record_review_advice(
        conn,
        task_id=task["id"],
        model_call_id=call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="concerns",
        doubts=[{"code": "insufficient_evidence", "detail": "缺少来源见证"}],
    )

    assert advice["task_id"] == task["id"]
    assert advice["model_call_id"] == call["id"]
    assert advice["advisory_outcome"] == "concerns"
    assert advice["doubts"] == [
        {"code": "insufficient_evidence", "detail": "缺少来源见证"}
    ]
    assert advice["schema_version"] == 1
    assert conn.execute("SELECT COUNT(*) FROM task_human_decisions").fetchone()[0] == 0


@pytest.mark.parametrize("human_word", ["approve", "reject"])
def test_machine_advice_cannot_use_human_decision_vocabulary(
    conn, human_word: str
) -> None:
    task = _task(conn)
    call = _model_call(conn, task["id"])

    with pytest.raises(ValueError, match="未知机器顾问结论"):
        repos.record_review_advice(
            conn,
            task_id=task["id"],
            model_call_id=call["id"],
            advisor_id="r0_review_advisor",
            advisor_version="0.1.0",
            model_profile="review",
            model_name="model-a",
            advisory_outcome=human_word,
            doubts=[],
        )

    assert conn.execute("SELECT COUNT(*) FROM task_review_advice").fetchone()[0] == 0


def test_human_decision_snapshots_exact_identity_and_pairs_same_task_advice(conn) -> None:
    """人终裁保存 exact username/display 快照并显式配对机器候选；机器意见不代签。"""
    task = _task(conn)
    call = _model_call(conn, task["id"])
    advice = repos.record_review_advice(
        conn,
        task_id=task["id"],
        model_call_id=call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="concerns",
        doubts=[{"code": "method_error", "detail": "方法假设不成立"}],
    )
    _to_waiting_review(conn, task["id"])

    reviewed, _ = repos.apply_human_review(
        conn,
        task["id"],
        action="reject",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code="method_error",
        comment="确认该疑点成立",
        paired_advice_id=advice["id"],
    )
    decision = repos.get_human_decision(conn, task["id"])

    assert reviewed["status"] == "failed"
    assert decision == {
        "id": decision["id"],
        "task_id": task["id"],
        "paired_advice_id": advice["id"],
        "action": "reject",
        "reason_code": "method_error",
        "comment": "确认该疑点成立",
        "reviewer_username": "final_reviewer",
        "reviewer_display_name": "终裁工程师",
        "schema_version": 1,
        "created_at": decision["created_at"],
    }


def test_repository_rejects_unknown_human_action_before_transaction(conn) -> None:
    task = _task(conn)
    _to_waiting_review(conn, task["id"])

    with pytest.raises(repos.InvalidReviewError, match="未知人工终裁动作"):
        repos.apply_human_review(
            conn,
            task["id"],
            action="approved",
            reviewer="终裁工程师",
            reviewer_username="final_reviewer",
            reason_code=None,
            comment=None,
        )

    assert repos.get_task(conn, task["id"])["status"] == "waiting_review"
    assert repos.get_human_decision(conn, task["id"]) is None


def test_database_rejects_cross_task_advice_pairing(conn) -> None:
    """即使绕过 repository，paired advice 也必须与人工终裁属于同一任务。"""
    source = _task(conn, "task_source")
    target = _task(conn, "task_target")
    _to_waiting_review(conn, target["id"])
    call = _model_call(conn, source["id"])
    advice = repos.record_review_advice(
        conn,
        task_id=source["id"],
        model_call_id=call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )

    with pytest.raises(sqlite3.IntegrityError, match="same task"):
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (id, task_id, paired_advice_id, action, reason_code, comment,
                 reviewer_username, reviewer_display_name, schema_version, created_at)
            VALUES ('decision_cross', ?, ?, 'approve', NULL, NULL,
                    'reviewer', '终裁工程师', 1, '2026-07-19T00:00:00+00:00')
            """,
            (target["id"], advice["id"]),
        )


@pytest.mark.parametrize("operation", ["update", "delete", "replace"])
def test_machine_advice_is_mechanically_append_only(conn, operation: str) -> None:
    task = _task(conn)
    call = _model_call(conn, task["id"])
    advice = repos.record_review_advice(
        conn,
        task_id=task["id"],
        model_call_id=call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        if operation == "update":
            conn.execute(
                "UPDATE task_review_advice SET advisory_outcome = 'abstain' WHERE id = ?",
                (advice["id"],),
            )
        elif operation == "delete":
            conn.execute("DELETE FROM task_review_advice WHERE id = ?", (advice["id"],))
        else:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_review_advice
                    (id, task_id, model_call_id, advisor_id, advisor_version,
                     model_profile, model_name, advisory_outcome, doubts_json,
                     schema_version, created_at)
                VALUES (?, ?, ?, 'replacement', '1', 'review', 'model-b',
                        'abstain', '[]', 1, '2026-07-19T00:00:00+00:00')
                """,
                (advice["id"], task["id"], call["id"]),
            )


@pytest.mark.parametrize("operation", ["update", "delete", "replace"])
def test_model_call_becomes_append_only_after_advice_witnesses_it(
    conn, operation: str
) -> None:
    """Advice 的真实 provenance 不能在写入后被原地改写或 REPLACE 洗掉。"""
    task = _task(conn)
    call = _model_call(conn, task["id"])
    repos.record_review_advice(
        conn,
        task_id=task["id"],
        model_call_id=call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        if operation == "update":
            conn.execute(
                "UPDATE model_calls SET status = 'failed' WHERE id = ?",
                (call["id"],),
            )
        elif operation == "delete":
            conn.execute("DELETE FROM model_calls WHERE id = ?", (call["id"],))
        else:
            conn.execute(
                """
                INSERT OR REPLACE INTO model_calls
                    (id, task_id, conversation_id, agent_id, model_profile,
                     model_name, status, response_summary, created_at)
                VALUES (?, ?, NULL, 'r0_review_advisor', 'review', 'model-a',
                        'success', 'replacement',
                        '2026-07-19T00:00:00+00:00')
                """,
                (call["id"], task["id"]),
            )


@pytest.mark.parametrize(
    "operation",
    ["update", "delete", "replace_by_id", "replace_by_task_id"],
)
def test_human_decision_is_mechanically_append_only_across_all_unique_keys(
    conn, operation: str
) -> None:
    """人工终裁事实不可改删；REPLACE 也不能借主键或 task_id 唯一键覆写。"""
    task = _task(conn)
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment="原始终裁",
    )
    decision = repos.get_human_decision(conn, task["id"])
    assert decision is not None

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        if operation == "update":
            conn.execute(
                "UPDATE task_human_decisions SET comment = '被修改' WHERE id = ?",
                (decision["id"],),
            )
        elif operation == "delete":
            conn.execute(
                "DELETE FROM task_human_decisions WHERE id = ?", (decision["id"],)
            )
        else:
            replacement_id = (
                decision["id"] if operation == "replace_by_id" else "decision_replacement"
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO task_human_decisions
                    (id, task_id, paired_advice_id, action, reason_code, comment,
                     reviewer_username, reviewer_display_name, schema_version, created_at)
                VALUES (?, ?, NULL, 'approve', NULL, '替换终裁',
                        'replacement', '替换者', 1, '2026-07-19T00:00:00+00:00')
                """,
                (replacement_id, task["id"]),
            )


@pytest.mark.parametrize(
    ("outcome", "doubts_json"),
    [
        (
            "clear",
            '[{"code":"method_error","detail":"不应随 clear 写入"}]',
        ),
        ("concerns", "[]"),
        (
            "concerns",
            '[{"code":"unknown_code","detail":"未知代码"}]',
        ),
        (
            "concerns",
            '[{"code":"method_error","detail":"合法文本","extra":true}]',
        ),
        ("concerns", '[{"code":"method_error","detail":"   "}]'),
    ],
)
def test_database_rejects_invalid_advice_outcome_doubt_contract(
    conn, outcome: str, doubts_json: str
) -> None:
    """绕过 repository 也不能破坏机器结论与固定疑点对象的组合合同。"""
    task = _task(conn)
    call = _model_call(conn, task["id"])

    with pytest.raises(sqlite3.IntegrityError, match="advice doubts contract"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 schema_version, created_at)
            VALUES ('advice_invalid', ?, ?, 'advisor', '1', 'review', 'model-a',
                    ?, ?, 1, '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], call["id"], outcome, doubts_json),
        )


@pytest.mark.parametrize("invalid_witness", ["foreign_task", "failed_call"])
def test_database_requires_same_task_successful_model_call_for_advice(
    conn, invalid_witness: str
) -> None:
    """model_call_id 不是装饰字段：必须见证同任务的一次真实成功调用。"""
    task = _task(conn, "task_target")
    if invalid_witness == "foreign_task":
        source = _task(conn, "task_source")
        call = _model_call(conn, source["id"])
    else:
        call = repos.record_model_call(
            conn,
            task_id=task["id"],
            agent_id="r0_review_advisor",
            model_profile="review",
            model_name="model-a",
            status="failed",
            error_message="provider_error",
        )

    with pytest.raises(sqlite3.IntegrityError, match="successful model call"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 schema_version, created_at)
            VALUES ('advice_bad_witness', ?, ?, 'advisor', '1', 'review',
                    'model-a', 'clear', '[]', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], call["id"]),
        )


@pytest.mark.parametrize(
    ("advisor_id", "model_profile", "model_name"),
    [
        ("forged_advisor", "review", "model-a"),
        ("r0_review_advisor", "forged_profile", "model-a"),
        ("r0_review_advisor", "review", "model-b"),
        ("r0_review_advisor", "review", None),
    ],
)
def test_database_requires_advice_snapshot_to_match_model_call_provenance(
    conn,
    advisor_id: str,
    model_profile: str,
    model_name: str | None,
) -> None:
    """真实 call id 不能替伪造的顾问/模型快照背书，nullable name 也须精确。"""
    task = _task(conn)
    call = _model_call(conn, task["id"])

    with pytest.raises(sqlite3.IntegrityError, match="exact provenance"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 schema_version, created_at)
            VALUES ('advice_forged_snapshot', ?, ?, ?, '1', ?, ?, 'clear',
                    '[]', 1, '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], call["id"], advisor_id, model_profile, model_name),
        )


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("advisor_id", "forged_advisor"),
        ("model_profile", "forged_profile"),
        ("model_name", "model-b"),
    ],
)
def test_repository_rejects_advice_snapshot_provenance_mismatch(
    conn, field: str, forged_value: str
) -> None:
    task = _task(conn)
    call = _model_call(conn, task["id"])
    values = {
        "advisor_id": "r0_review_advisor",
        "model_profile": "review",
        "model_name": "model-a",
    }
    values[field] = forged_value

    with pytest.raises(ValueError, match="exact provenance"):
        repos.record_review_advice(
            conn,
            task_id=task["id"],
            model_call_id=call["id"],
            advisor_id=values["advisor_id"],
            advisor_version="0.1.0",
            model_profile=values["model_profile"],
            model_name=values["model_name"],
            advisory_outcome="clear",
            doubts=[],
        )

    assert conn.execute("SELECT COUNT(*) FROM task_review_advice").fetchone()[0] == 0


def test_advice_model_name_provenance_is_null_safe(conn) -> None:
    task = _task(conn)
    call = repos.record_model_call(
        conn,
        task_id=task["id"],
        agent_id="r0_review_advisor",
        model_profile="review",
        model_name=None,
        status="success",
    )

    advice = repos.record_review_advice(
        conn,
        task_id=task["id"],
        model_call_id=call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name=None,
        advisory_outcome="clear",
        doubts=[],
    )

    assert advice["model_name"] is None

    second_call = repos.record_model_call(
        conn,
        task_id=task["id"],
        agent_id="r0_review_advisor",
        model_profile="review",
        model_name=None,
        status="success",
    )
    with pytest.raises(sqlite3.IntegrityError, match="exact provenance"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 schema_version, created_at)
            VALUES ('advice_null_forgery', ?, ?, 'r0_review_advisor', '0.1.0',
                    'review', 'model-a', 'clear', '[]', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], second_call["id"]),
        )


@pytest.mark.parametrize("task_status", ["created", "completed"])
def test_database_rejects_human_decision_for_non_waiting_review_task(
    conn, task_status: str
) -> None:
    task = _task(conn)
    if task_status == "completed":
        _to_waiting_review(conn, task["id"])
        repos.set_task_status(conn, task["id"], "completed")

    with pytest.raises(sqlite3.IntegrityError, match="waiting_review"):
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (id, task_id, paired_advice_id, action, reason_code, comment,
                 reviewer_username, reviewer_display_name, schema_version, created_at)
            VALUES ('decision_wrong_state', ?, NULL, 'approve', NULL, NULL,
                    'reviewer', '终裁工程师', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (task["id"],),
        )


def test_judgment_ledger_primary_ids_are_never_nullable(conn) -> None:
    task = _task(conn)
    call = _model_call(conn, task["id"])
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 schema_version, created_at)
            VALUES (NULL, ?, ?, 'r0_review_advisor', '0.1.0', 'review',
                    'model-a', 'clear', '[]', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], call["id"]),
        )

    _to_waiting_review(conn, task["id"])
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (id, task_id, paired_advice_id, action, reason_code, comment,
                 reviewer_username, reviewer_display_name, schema_version, created_at)
            VALUES (NULL, ?, NULL, 'approve', NULL, NULL, 'reviewer',
                    '终裁工程师', 1, '2026-07-19T00:00:00+00:00')
            """,
            (task["id"],),
        )


def test_fresh_database_has_exact_judgment_schema_witnesses(conn) -> None:
    witnesses = judgment_schema_witnesses(conn)
    assert tuple(witnesses) == JUDGMENT_SCHEMA_WITNESS_KEYS
    assert all(value is True for value in witnesses.values())


def test_judgment_schema_witness_rejects_same_name_noop_trigger(conn) -> None:
    trigger_name = judgment_required_trigger_names()[0]
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(
        f"""
        CREATE TRIGGER "{trigger_name}"
        BEFORE INSERT ON task_review_advice
        BEGIN
            SELECT 1;
        END
        """
    )

    witnesses = judgment_schema_witnesses(conn)

    assert witnesses["required_triggers"] is False


def test_init_replaces_same_name_noop_judgment_trigger(tmp_path) -> None:
    db_path = tmp_path / "stale-trigger.db"
    init_db(db_path)
    connection = get_conn(db_path)
    trigger_name = judgment_required_trigger_names()[0]
    try:
        connection.execute(f'DROP TRIGGER "{trigger_name}"')
        connection.execute(
            f"""
            CREATE TRIGGER "{trigger_name}"
            BEFORE INSERT ON task_review_advice
            BEGIN
                SELECT 1;
            END
            """
        )
        assert judgment_schema_witnesses(connection)["required_triggers"] is False
    finally:
        connection.close()


def test_init_refuses_to_repair_tampered_nonempty_judgment_ledger(
    tmp_path,
) -> None:
    """非空账本失去只追加保护后历史已不可证；重启必须保留现场并咬红。"""
    db_path = tmp_path / "tampered-populated-ledger.db"
    init_db(db_path)
    connection = get_conn(db_path)
    trigger_name = "trg_task_review_advice_no_update"
    try:
        task = _task(connection)
        call = _model_call(connection, task["id"])
        repos.record_review_advice(
            connection,
            task_id=task["id"],
            model_call_id=call["id"],
            advisor_id="r0_review_advisor",
            advisor_version="0.1.0",
            model_profile="review",
            model_name="model-a",
            advisory_outcome="clear",
            doubts=[],
        )
        connection.execute(f'DROP TRIGGER "{trigger_name}"')
        connection.execute(
            f"""
            CREATE TRIGGER "{trigger_name}"
            BEFORE UPDATE ON task_review_advice
            BEGIN
                SELECT 1;
            END
            """
        )
        assert judgment_schema_witnesses(connection)["required_triggers"] is False
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="judgment schema witness"):
        init_db(db_path)

    connection = get_conn(db_path)
    try:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()[0]
        assert "SELECT 1" in trigger_sql
        assert judgment_schema_witnesses(connection)["required_triggers"] is False
    finally:
        connection.close()


def test_init_refuses_to_recreate_missing_table_beside_nonempty_ledger(
    tmp_path,
) -> None:
    db_path = tmp_path / "missing-table-populated-ledger.db"
    init_db(db_path)
    connection = get_conn(db_path)
    try:
        task = _task(connection)
        call = _model_call(connection, task["id"])
        repos.record_review_advice(
            connection,
            task_id=task["id"],
            model_call_id=call["id"],
            advisor_id="r0_review_advisor",
            advisor_version="0.1.0",
            model_profile="review",
            model_name="model-a",
            advisory_outcome="clear",
            doubts=[],
        )
        connection.execute("DROP TABLE task_human_decisions")
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="missing a required table"):
        init_db(db_path)

    connection = get_conn(db_path)
    try:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'task_human_decisions'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT COUNT(*) FROM task_review_advice"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_init_keeps_canonical_nonempty_judgment_ledger_startable(tmp_path) -> None:
    db_path = tmp_path / "canonical-populated-ledger.db"
    init_db(db_path)
    connection = get_conn(db_path)
    try:
        task = _task(connection)
        call = _model_call(connection, task["id"])
        repos.record_review_advice(
            connection,
            task_id=task["id"],
            model_call_id=call["id"],
            advisor_id="r0_review_advisor",
            advisor_version="0.1.0",
            model_profile="review",
            model_name="model-a",
            advisory_outcome="clear",
            doubts=[],
        )
    finally:
        connection.close()

    init_db(db_path)
    connection = get_conn(db_path)
    try:
        assert all(judgment_schema_witnesses(connection).values()) is True
        assert connection.execute(
            "SELECT COUNT(*) FROM task_review_advice"
        ).fetchone()[0] == 1
    finally:
        connection.close()

    init_db(db_path)
    connection = get_conn(db_path)
    try:
        assert judgment_schema_witnesses(connection)["required_triggers"] is True
    finally:
        connection.close()


def test_judgment_schema_witness_rejects_missing_managed_objects(
    tmp_path,
) -> None:
    db_path = tmp_path / "managed-objects.db"
    init_db(db_path)

    for object_type, names, witness_key in (
        ("TRIGGER", judgment_required_trigger_names(), "required_triggers"),
        ("INDEX", judgment_required_index_names(), "required_indexes"),
    ):
        for name in names:
            connection = get_conn(db_path)
            try:
                connection.execute(f'DROP {object_type} "{name}"')
                assert judgment_schema_witnesses(connection)[witness_key] is False
            finally:
                connection.close()
            # Startup is authoritative convergence: every managed body is replayed.
            init_db(db_path)


def test_judgment_schema_witness_rejects_loose_table_constraints() -> None:
    loose = sqlite3.connect(":memory:")
    try:
        loose.execute("CREATE TABLE task_review_advice (id TEXT PRIMARY KEY)")
        loose.execute("CREATE TABLE task_human_decisions (id TEXT PRIMARY KEY)")

        witnesses = judgment_schema_witnesses(loose)

        assert witnesses["advice_table_shape"] is False
        assert witnesses["human_decision_table_shape"] is False
    finally:
        loose.close()


def test_init_does_not_invent_decisions_for_legacy_completed_tasks(tmp_path) -> None:
    """判断原因为不可回溯事实；启动迁移只建采集口，不伪造历史人签记录。"""
    db_path = tmp_path / "legacy-without-judgment-ledger.db"
    init_db(db_path)
    connection = get_conn(db_path)
    try:
        task = _task(connection, "legacy_reviewed_task")
        _to_waiting_review(connection, task["id"])
        repos.set_task_status(connection, task["id"], "completed")
        assert repos.get_human_decision(connection, task["id"]) is None
    finally:
        connection.close()

    init_db(db_path)
    connection = get_conn(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM task_human_decisions"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM task_review_advice"
        ).fetchone()[0] == 0
    finally:
        connection.close()
