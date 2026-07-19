"""判断资产化存储合同：机器顾问候选与人工终裁物理隔离、只追加、可精确配对。"""

from __future__ import annotations

import sqlite3

import pytest

from backend.app.storage import repos
from backend.app.storage import db as db_mod
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


def _drop_mutate_restore(
    conn: sqlite3.Connection,
    trigger_name: str,
    mutation_sql: str,
    parameters: tuple = (),
) -> None:
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()[0]
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(mutation_sql, parameters)
    conn.execute(trigger_sql)


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
    assert advice["evidence_file_ids"] == []
    assert advice["schema_version"] == 1
    assert conn.execute("SELECT COUNT(*) FROM task_human_decisions").fetchone()[0] == 0


def test_machine_advice_preserves_same_task_evidence_file_pointers(conn) -> None:
    task = _task(conn)
    evidence_file_id = "file_review_evidence"
    repos.create_file(
        conn,
        file_id=evidence_file_id,
        task_id=task["id"],
        kind="output",
        filename="review-evidence.json",
        path="/non-reading-test/review-evidence.json",
        size_bytes=0,
        sha256="0" * 64,
        classification="internal",
    )
    repos.set_task_outputs(conn, task["id"], [evidence_file_id])
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
        doubts=[{"code": "method_error", "detail": "方法与证据不一致"}],
        evidence_file_ids=[evidence_file_id],
    )

    assert advice["evidence_file_ids"] == [evidence_file_id]


def test_repository_rejects_foreign_or_duplicate_evidence_file_pointers(conn) -> None:
    source = _task(conn, "task_evidence_source")
    target = _task(conn, "task_evidence_target")
    evidence_file_id = "file_foreign_evidence"
    repos.create_file(
        conn,
        file_id=evidence_file_id,
        task_id=source["id"],
        kind="output",
        filename="foreign.json",
        path="/non-reading-test/foreign.json",
        size_bytes=0,
        sha256="0" * 64,
        classification="internal",
    )
    repos.set_task_outputs(conn, source["id"], [evidence_file_id])
    call = _model_call(conn, target["id"])

    for evidence_file_ids in (
        [evidence_file_id],
        [evidence_file_id, evidence_file_id],
    ):
        with pytest.raises(ValueError, match="证据"):
            repos.record_review_advice(
                conn,
                task_id=target["id"],
                model_call_id=call["id"],
                advisor_id="r0_review_advisor",
                advisor_version="0.1.0",
                model_profile="review",
                model_name="model-a",
                advisory_outcome="clear",
                doubts=[],
                evidence_file_ids=evidence_file_ids,
            )

    assert conn.execute("SELECT COUNT(*) FROM task_review_advice").fetchone()[0] == 0


def test_database_rejects_foreign_evidence_file_pointer(conn) -> None:
    source = _task(conn, "task_db_evidence_source")
    target = _task(conn, "task_db_evidence_target")
    evidence_file_id = "file_db_foreign_evidence"
    repos.create_file(
        conn,
        file_id=evidence_file_id,
        task_id=source["id"],
        kind="output",
        filename="foreign.json",
        path="/non-reading-test/foreign.json",
        size_bytes=0,
        sha256="0" * 64,
        classification="internal",
    )
    repos.set_task_outputs(conn, source["id"], [evidence_file_id])
    call = _model_call(conn, target["id"])

    with pytest.raises(sqlite3.IntegrityError, match="evidence references"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 evidence_file_ids_json, schema_version, created_at)
            VALUES ('advice_foreign_evidence', ?, ?, 'r0_review_advisor',
                    '0.1.0', 'review', 'model-a', 'clear', '[]', ?, 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (target["id"], call["id"], f'["{evidence_file_id}"]'),
        )


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


def test_machine_advice_replace_cannot_bypass_via_hidden_rowid(conn) -> None:
    source = _task(conn, "task_rowid_source")
    source_call = _model_call(conn, source["id"])
    advice = repos.record_review_advice(
        conn,
        task_id=source["id"],
        model_call_id=source_call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )
    target = _task(conn, "task_rowid_target")
    target_call = _model_call(conn, target["id"])
    hidden_rowid = conn.execute(
        "SELECT rowid FROM task_review_advice WHERE id = ?", (advice["id"],)
    ).fetchone()[0]
    conn.execute("PRAGMA recursive_triggers=OFF")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            """
            INSERT OR REPLACE INTO task_review_advice
                (rowid, id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 schema_version, created_at)
            VALUES (?, 'advice_rowid_replacement', ?, ?, 'r0_review_advisor',
                    '0.1.0', 'review', 'model-a', 'clear', '[]', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (hidden_rowid, target["id"], target_call["id"]),
        )

    assert conn.execute(
        "SELECT id FROM task_review_advice WHERE rowid = ?", (hidden_rowid,)
    ).fetchone()[0] == advice["id"]


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


def test_human_decision_replace_cannot_bypass_via_hidden_rowid(conn) -> None:
    source = _task(conn, "decision_rowid_source")
    _to_waiting_review(conn, source["id"])
    repos.apply_human_review(
        conn,
        source["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment=None,
    )
    decision = repos.get_human_decision(conn, source["id"])
    assert decision is not None
    hidden_rowid = conn.execute(
        "SELECT rowid FROM task_human_decisions WHERE id = ?", (decision["id"],)
    ).fetchone()[0]
    target = _task(conn, "decision_rowid_target")
    _to_waiting_review(conn, target["id"])
    conn.execute("PRAGMA recursive_triggers=OFF")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            """
            INSERT OR REPLACE INTO task_human_decisions
                (rowid, id, task_id, paired_advice_id, action, reason_code,
                 comment, reviewer_username, reviewer_display_name,
                 schema_version, created_at)
            VALUES (?, 'decision_rowid_replacement', ?, NULL, 'approve', NULL,
                    NULL, 'replacement', '替换者', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (hidden_rowid, target["id"]),
        )

    assert conn.execute(
        "SELECT id FROM task_human_decisions WHERE rowid = ?", (hidden_rowid,)
    ).fetchone()[0] == decision["id"]


def test_nonpositive_judgment_rowids_are_rejected_without_poisoning_new_writes(
    conn,
) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="model call internal rowid"):
        conn.execute(
            "INSERT INTO model_calls "
            "(id, task_id, conversation_id, agent_id, model_profile, model_name, "
            " status, created_at) VALUES (-1, NULL, NULL, 'advisor', 'review', "
            " 'model-a', 'success', '2026-07-19T00:00:00+00:00')"
        )

    task = _task(conn, "judgment-rowid-task")
    call = _model_call(conn, task["id"])
    with pytest.raises(sqlite3.IntegrityError, match="advice internal rowid"):
        conn.execute(
            """
            INSERT INTO task_review_advice
                (rowid, id, task_id, model_call_id, advisor_id, advisor_version,
                 model_profile, model_name, advisory_outcome, doubts_json,
                 evidence_file_ids_json, schema_version, created_at)
            VALUES (-1, 'negative-advice', ?, ?, 'r0_review_advisor', '0.1.0',
                    'review', 'model-a', 'clear', '[]', '[]', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], call["id"]),
        )
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

    decision_task = _task(conn, "decision-rowid-task")
    _to_waiting_review(conn, decision_task["id"])
    with pytest.raises(sqlite3.IntegrityError, match="decision internal rowid"):
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (rowid, id, task_id, paired_advice_id, action, reason_code,
                 comment, reviewer_username, reviewer_display_name,
                 schema_version, created_at)
            VALUES (-1, 'negative-decision', ?, NULL, 'approve', NULL, NULL,
                    'reviewer', '终裁工程师', 1,
                    '2026-07-19T00:00:00+00:00')
            """,
            (decision_task["id"],),
        )
    repos.apply_human_review(
        conn,
        decision_task["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="reviewer",
        reason_code=None,
        comment=None,
    )
    _model_call(conn, task["id"])


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
        ("concerns", '[{"code":"method_error","detail":"\\n\\t\\r"}]'),
        ("concerns", '[{"code":"method_error","detail":"\u2003"}]'),
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
        for status in ("queued", "validating", "running", "analyzing"):
            repos.set_task_status(conn, task["id"], status)
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


@pytest.mark.parametrize(
    ("comment", "reviewer_username", "reviewer_display_name"),
    [
        ("\n\t\r", "reviewer", "终裁工程师"),
        ("\u2003", "reviewer", "终裁工程师"),
        ("具体原因", "\n\t", "终裁工程师"),
        ("具体原因", "reviewer", "\u2003"),
    ],
)
def test_database_rejects_whitespace_only_human_decision_fields(
    conn,
    comment: str,
    reviewer_username: str,
    reviewer_display_name: str,
) -> None:
    task = _task(conn)
    _to_waiting_review(conn, task["id"])

    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (id, task_id, paired_advice_id, action, reason_code, comment,
                 reviewer_username, reviewer_display_name, schema_version, created_at)
            VALUES ('decision_whitespace', ?, NULL, 'reject', 'other', ?, ?, ?,
                    1, '2026-07-19T00:00:00+00:00')
            """,
            (task["id"], comment, reviewer_username, reviewer_display_name),
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


def test_judgment_witness_rejects_persisted_nonpositive_model_call_rowid(
    tmp_path,
) -> None:
    db_path = tmp_path / "negative-model-call-rowid.db"
    init_db(db_path)
    connection = get_conn(db_path)
    trigger_name = "trg_model_calls_positive_rowid"
    try:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()[0]
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(
            "INSERT INTO model_calls "
            "(id, task_id, conversation_id, agent_id, model_profile, model_name, "
            " status, created_at) VALUES (-1, NULL, NULL, 'advisor', 'review', "
            " 'model-a', 'success', '2026-07-19T00:00:00+00:00')"
        )
        connection.execute(trigger_sql)
        witnesses = judgment_schema_witnesses(connection)
        assert witnesses["required_triggers"] is True
        assert witnesses["rowid_integrity"] is False
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="rowid_integrity"):
        init_db(db_path)


def test_judgment_provenance_detects_witnessed_model_call_rewrite(conn) -> None:
    task = _task(conn, "provenance-model-call")
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
    _drop_mutate_restore(
        conn,
        "trg_witnessed_model_calls_no_update",
        "UPDATE model_calls SET status = 'failed' WHERE id = ?",
        (call["id"],),
    )

    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_witnessed_model_call_rejects_sibling_update_or_replace(conn) -> None:
    task = _task(conn, "provenance-model-call-sibling")
    witnessed = _model_call(conn, task["id"])
    repos.record_review_advice(
        conn,
        task_id=task["id"],
        model_call_id=witnessed["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )
    sibling = repos.record_model_call(
        conn,
        task_id=task["id"],
        agent_id="r0_review_advisor",
        model_profile="review",
        model_name="model-a",
        status="success",
        response_summary="forged sibling payload",
    )
    original = tuple(
        conn.execute(
            "SELECT * FROM model_calls WHERE id = ?", (witnessed["id"],)
        ).fetchone()
    )

    conn.execute("PRAGMA recursive_triggers = OFF")
    with pytest.raises(sqlite3.IntegrityError, match="witnessed model_call"):
        conn.execute(
            "UPDATE OR REPLACE model_calls SET id = ? WHERE id = ?",
            (witnessed["id"], sibling["id"]),
        )

    assert tuple(
        conn.execute(
            "SELECT * FROM model_calls WHERE id = ?", (witnessed["id"],)
        ).fetchone()
    ) == original


def test_judgment_provenance_detects_invalid_advice_content(conn) -> None:
    task = _task(conn, "provenance-advice")
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
        doubts=[{"code": "method_error", "detail": "原始疑点"}],
    )
    _drop_mutate_restore(
        conn,
        "trg_task_review_advice_no_update",
        "UPDATE task_review_advice "
        "SET doubts_json = '[{\"code\":\"bogus\",\"detail\":\"\"}]', "
        "evidence_file_ids_json = '[\"missing-file\"]' WHERE id = ?",
        (advice["id"],),
    )

    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_judgment_provenance_detects_cross_task_decision_pair(conn) -> None:
    source = _task(conn, "provenance-decision-source")
    source_call = _model_call(conn, source["id"])
    source_advice = repos.record_review_advice(
        conn,
        task_id=source["id"],
        model_call_id=source_call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )
    foreign = _task(conn, "provenance-decision-foreign")
    foreign_call = _model_call(conn, foreign["id"])
    foreign_advice = repos.record_review_advice(
        conn,
        task_id=foreign["id"],
        model_call_id=foreign_call["id"],
        advisor_id="r0_review_advisor",
        advisor_version="0.1.0",
        model_profile="review",
        model_name="model-a",
        advisory_outcome="clear",
        doubts=[],
    )
    _to_waiting_review(conn, source["id"])
    repos.apply_human_review(
        conn,
        source["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment="同意",
        paired_advice_id=source_advice["id"],
    )
    _drop_mutate_restore(
        conn,
        "trg_task_human_decisions_no_update",
        "UPDATE task_human_decisions SET paired_advice_id = ? WHERE task_id = ?",
        (foreign_advice["id"], source["id"]),
    )

    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_structured_review_event_is_unique_per_human_decision(conn) -> None:
    task = _task(conn, "provenance-unique-review-event")
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="reject",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code="method_error",
        comment="方法不成立",
    )
    decision = repos.get_human_decision(conn, task["id"])
    assert decision is not None

    with pytest.raises(sqlite3.IntegrityError, match="structured review event"):
        repos.append_event(
            conn,
            task_id=task["id"],
            agent_id=task["agent_id"],
            event_type="review_rejected",
            level="warning",
            message="duplicate signer event",
            payload={
                "reviewer": decision["reviewer_display_name"],
                "reviewer_username": decision["reviewer_username"],
                "comment": decision["comment"],
                "decision_id": decision["id"],
                "reason_code": decision["reason_code"],
                "paired_advice_id": decision["paired_advice_id"],
            },
        )


def test_post_cutover_review_event_without_decision_is_rejected(conn) -> None:
    task = _task(conn, "post-cutover-legacy-review")
    with pytest.raises(sqlite3.IntegrityError, match="structured review event"):
        repos.append_event(
            conn,
            task_id=task["id"],
            agent_id=task["agent_id"],
            event_type="review_approved",
            level="info",
            message="forged legacy signer",
            payload={},
        )

    assert conn.execute(
        "SELECT COUNT(*) FROM task_events WHERE task_id = ?",
        (task["id"],),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM task_review_event_witnesses WHERE task_id = ?",
        (task["id"],),
    ).fetchone()[0] == 0


def test_review_event_snapshot_detects_time_message_and_internal_id_rewrite(
    conn,
) -> None:
    task = _task(conn, "provenance-review-event-snapshot")
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment=None,
    )
    _drop_mutate_restore(
        conn,
        "trg_task_events_no_update",
        "UPDATE task_events SET id = id + 10000, message = 'forged signer', "
        "created_at = '2999-01-01T00:00:00+00:00' "
        "WHERE task_id = ? AND event_type = 'review_approved'",
        (task["id"],),
    )

    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_review_event_witness_is_append_only(conn) -> None:
    task = _task(conn, "review-event-witness-append-only")
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment=None,
    )
    witness = conn.execute(
        "SELECT * FROM task_review_event_witnesses WHERE task_id = ?",
        (task["id"],),
    ).fetchone()
    assert witness is not None

    for sql in (
        "UPDATE task_review_event_witnesses SET message = 'forged' WHERE event_id = ?",
        "DELETE FROM task_review_event_witnesses WHERE event_id = ?",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(sql, (witness["event_id"],))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            "INSERT OR REPLACE INTO task_review_event_witnesses "
            "(event_id, event_internal_id, task_id, agent_id, event_type, level, "
            "message, payload_json, created_at, decision_id, witness_kind, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, 'forged', ?, ?, ?, ?, 1)",
            (
                witness["event_id"],
                witness["event_internal_id"],
                witness["task_id"],
                witness["agent_id"],
                witness["event_type"],
                witness["level"],
                witness["payload_json"],
                witness["created_at"],
                witness["decision_id"],
                witness["witness_kind"],
            ),
        )


def test_decision_storage_rejects_blob_timestamp_and_deep_witnesses_bypass(
    conn,
) -> None:
    task = _task(conn, "decision-blob-time")
    _to_waiting_review(conn, task["id"])
    values = (
        "decision_blob_time",
        task["id"],
        sqlite3.Binary(b"2026-07-19T00:00:00+00:00"),
    )
    insert_sql = (
        "INSERT INTO task_human_decisions "
        "(id, task_id, paired_advice_id, action, reason_code, comment, "
        " reviewer_username, reviewer_display_name, schema_version, created_at) "
        "VALUES (?, ?, NULL, 'reject', 'method_error', NULL, "
        "'reviewer', '终裁工程师', 1, ?)"
    )
    with pytest.raises(sqlite3.IntegrityError, match="decision storage"):
        conn.execute(insert_sql, values)

    trigger_name = "trg_task_human_decisions_validate_storage"
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()[0]
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(insert_sql, values)
    conn.execute(trigger_sql)

    assert conn.execute(
        "SELECT typeof(created_at) FROM task_human_decisions WHERE id = ?",
        (values[0],),
    ).fetchone()[0] == "blob"
    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_decision_storage_rejects_noncanonical_text_timestamp_and_deep_bypass(
    conn,
) -> None:
    task = _task(conn, "decision-noncanonical-time")
    _to_waiting_review(conn, task["id"])
    decision_id = "decision_noncanonical_time"
    noncanonical = "2026-07-19 00:00:00+00:00"
    insert_sql = (
        "INSERT INTO task_human_decisions "
        "(id, task_id, paired_advice_id, action, reason_code, comment, "
        " reviewer_username, reviewer_display_name, schema_version, created_at) "
        "VALUES (?, ?, NULL, 'approve', NULL, NULL, "
        "'reviewer', '终裁工程师', 1, ?)"
    )
    values = (decision_id, task["id"], noncanonical)

    with pytest.raises(sqlite3.IntegrityError, match="decision storage"):
        conn.execute(insert_sql, values)

    trigger_name = "trg_task_human_decisions_validate_storage"
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()[0]
    conn.execute(f'DROP TRIGGER "{trigger_name}"')
    conn.execute(insert_sql, values)
    conn.execute(trigger_sql)
    repos.append_event(
        conn,
        task_id=task["id"],
        agent_id=task["agent_id"],
        event_type="review_approved",
        level="info",
        message="exact approval with poisoned decision time",
        payload={
            "reviewer": "终裁工程师",
            "reviewer_username": "reviewer",
            "comment": None,
            "decision_id": decision_id,
            "reason_code": None,
            "paired_advice_id": None,
        },
    )
    conn.execute(
        "UPDATE tasks SET status = 'completed', updated_at = ?, finished_at = ?, "
        "error_message = NULL WHERE id = ?",
        (noncanonical, noncanonical, task["id"]),
    )

    assert conn.execute(
        "SELECT status FROM tasks WHERE id = ?", (task["id"],)
    ).fetchone()[0] == "completed"
    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_judgment_provenance_detects_missing_structured_event_witness(conn) -> None:
    task = _task(conn, "provenance-orphaned-review-event")
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment=None,
    )
    _drop_mutate_restore(
        conn,
        "trg_task_review_event_witnesses_no_delete",
        "DELETE FROM task_review_event_witnesses WHERE task_id = ?",
        (task["id"],),
    )

    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_judgment_provenance_rejects_duplicate_review_payload_keys(conn) -> None:
    task = _task(conn, "provenance-duplicate-review-json")
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="approve",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code=None,
        comment=None,
    )
    decision = repos.get_human_decision(conn, task["id"])
    assert decision is not None
    duplicate_payload = (
        '{"decision_id":"' + decision["id"] + '",'
        '"reviewer":"终裁工程师",'
        '"reviewer_username":"final_reviewer",'
        '"comment":null,"reason_code":null,"paired_advice_id":null,'
        '"decision_id":"forged-decision","reviewer":"Mallory"}'
    )
    _drop_mutate_restore(
        conn,
        "trg_task_events_no_update",
        "UPDATE task_events SET payload_json = ? "
        "WHERE task_id = ? AND event_type = 'review_approved'",
        (duplicate_payload, task["id"]),
    )

    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["required_triggers"] is True
    assert witnesses["provenance_integrity"] is False


def test_reviewed_terminal_fields_are_frozen_and_deep_witnessed(conn) -> None:
    task = _task(conn, "provenance-reviewed-terminal")
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="reject",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code="method_error",
        comment="方法不成立",
    )
    with pytest.raises(sqlite3.IntegrityError, match="review task provenance"):
        conn.execute(
            "UPDATE tasks SET updated_at = '2999-01-01T00:00:00+00:00', "
            "finished_at = '2999-01-01T00:00:00+00:00', "
            "error_message = 'forged display' WHERE id = ?",
            (task["id"],),
        )

    _drop_mutate_restore(
        conn,
        "trg_review_package_tasks_provenance_immutable",
        "UPDATE tasks SET updated_at = '2999-01-01T00:00:00+00:00', "
        "finished_at = '2999-01-01T00:00:00+00:00', "
        "error_message = 'forged display' WHERE id = ?",
        (task["id"],),
    )
    witnesses = judgment_schema_witnesses(conn)
    assert witnesses["provenance_integrity"] is False


def test_judgment_provenance_accepts_normal_review_and_manifest_evolution(
    conn,
) -> None:
    task = _task(conn, "provenance-normal-reject")
    evidence_id = "provenance-evidence"
    repos.create_file(
        conn,
        file_id=evidence_id,
        task_id=task["id"],
        kind="output",
        filename="evidence.txt",
        path="/tmp/evidence.txt",
        size_bytes=1,
        sha256="a" * 64,
        classification="internal",
    )
    repos.set_task_outputs(conn, task["id"], [evidence_id])
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
        doubts=[{"code": "source_doubt", "detail": "需人工确认"}],
        evidence_file_ids=[evidence_id],
    )
    repos.set_task_outputs(conn, task["id"], [])
    _to_waiting_review(conn, task["id"])
    repos.apply_human_review(
        conn,
        task["id"],
        action="reject",
        reviewer="终裁工程师",
        reviewer_username="final_reviewer",
        reason_code="source_doubt",
        comment="证据不足",
        paired_advice_id=advice["id"],
    )

    approved = _task(conn, "provenance-normal-approve")
    _to_waiting_review(conn, approved["id"])
    repos.apply_human_review(
        conn,
        approved["id"],
        action="approve",
        reviewer="另一终裁工程师",
        reviewer_username="second_reviewer",
        reason_code=None,
        comment=None,
    )

    assert judgment_schema_witnesses(conn)["provenance_integrity"] is True


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


def test_init_refuses_to_recreate_dropped_populated_advice_table(
    tmp_path,
) -> None:
    """被删的是唯一有数据的表时，空的另一表不能让启动误判为从未启用。"""
    db_path = tmp_path / "dropped-populated-advice.db"
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
        connection.execute("DROP TABLE task_review_advice")
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="schema residue"):
        init_db(db_path)

    connection = get_conn(db_path)
    try:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'task_review_advice'"
        ).fetchone() is None
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
        for status in ("queued", "validating", "running", "analyzing"):
            repos.set_task_status(connection, task["id"], status)
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


def test_init_seals_pre_judgment_review_event_without_inventing_decision(
    tmp_path,
) -> None:
    db_path = tmp_path / "pre-judgment-review-event.db"
    init_db(db_path)
    connection = get_conn(db_path)
    task = _task(connection, "legacy-signer-task")
    for status in ("queued", "validating", "running", "analyzing", "completed"):
        repos.set_task_status(connection, task["id"], status)

    for trigger_name in (
        "trg_structured_review_events_decision_witness",
        "trg_structured_review_events_capture_witness",
    ):
        connection.execute(f'DROP TRIGGER "{trigger_name}"')
    legacy_row = (
        "legacy-signer-event",
        task["id"],
        task["agent_id"],
        "review_approved",
        "info",
        "historical signer record",
        "{}",
        "2026-07-18T00:00:00+00:00",
    )
    connection.execute(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        legacy_row,
    )
    for trigger_name in db_mod._JUDGMENT_MANAGED_TRIGGERS:
        connection.execute(f'DROP TRIGGER IF EXISTS "{trigger_name}"')
    for index_name in db_mod._JUDGMENT_MANAGED_INDEXES:
        connection.execute(f'DROP INDEX IF EXISTS "{index_name}"')
    connection.execute("DROP TABLE task_review_event_witnesses")
    connection.execute("DROP TABLE task_human_decisions")
    connection.execute("DROP TABLE task_review_advice")
    connection.close()

    init_db(db_path)
    connection = get_conn(db_path)
    try:
        persisted = connection.execute(
            "SELECT event_id, task_id, agent_id, event_type, level, message, "
            "payload_json, created_at FROM task_events WHERE event_id = ?",
            (legacy_row[0],),
        ).fetchone()
        assert tuple(persisted) == legacy_row
        witness = connection.execute(
            "SELECT witness_kind, decision_id, event_internal_id "
            "FROM task_review_event_witnesses WHERE event_id = ?",
            (legacy_row[0],),
        ).fetchone()
        assert tuple(witness[:2]) == ("legacy_pre_instrumentation", None)
        assert witness[2] > 0
        assert connection.execute(
            "SELECT COUNT(*) FROM task_human_decisions"
        ).fetchone()[0] == 0
        assert all(judgment_schema_witnesses(connection).values()) is True
    finally:
        connection.close()

    init_db(db_path)
    connection = get_conn(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM task_review_event_witnesses "
            "WHERE event_id = 'legacy-signer-event'"
        ).fetchone()[0] == 1
        assert all(judgment_schema_witnesses(connection).values()) is True
    finally:
        connection.close()
