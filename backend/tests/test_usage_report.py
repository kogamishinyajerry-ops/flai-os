"""scripts/usage_report.py 测试：夹具 DB 计数正确 + eval 隔离 + 缺列诚实「未知」+ 缺库 fail-closed。

独立可跑（纯 stdlib+pytest，不依赖 fastapi 栈）：
    uv run --no-project --with pytest python -m pytest backend/tests/test_usage_report.py -q
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

from backend.app.storage import repos
from backend.app.storage.db import init_db

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "scripts" / "usage_report.py"

spec = importlib.util.spec_from_file_location("usage_report", SCRIPT)
usage_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage_report)

NOW = dt.datetime(2026, 7, 18, 12, 0, 0, tzinfo=dt.timezone.utc)
RECENT = "2026-07-17T10:00:00+00:00"
DECISION_AT = "2026-07-17T10:05:00+00:00"
FUTURE = "2026-07-19T10:00:00+00:00"
OLD = "2026-05-01T10:00:00+00:00"


def _insert_outcome(
    conn: sqlite3.Connection,
    *,
    outcome_id: str,
    event_type: str,
    source_file_id: str,
    created_at: str,
    actor_username: str | None = None,
    downstream_task_id: str | None = None,
    delivered_bytes: int | None = None,
) -> None:
    task_snapshot, file_snapshot = repos._artifact_outcome_parent_snapshots(
        conn,
        event_type=event_type,
        source_task_id="t1",
        source_file_id=source_file_id,
        review_event_id="e1",
    )
    conn.execute(
        "INSERT INTO artifact_outcome_events "
        "(id, event_type, source_task_id, source_file_id, review_event_id, "
        " source_task_witness_json, source_file_witness_json, actor_username, "
        " downstream_task_id, delivered_bytes, schema_version, created_at) "
        "VALUES (?, ?, 't1', ?, 'e1', ?, ?, ?, ?, ?, 1, ?)",
        (
            outcome_id,
            event_type,
            source_file_id,
            task_snapshot,
            file_snapshot,
            actor_username,
            downstream_task_id,
            delivered_bytes,
            created_at,
        ),
    )


def _insert_pre_cutover_review_events(
    conn: sqlite3.Connection,
    rows: list[tuple[str, str, str, str, str, str, str, str]],
) -> None:
    """Seed exact historical review rows as if strict instrumentation migrated them.

    Runtime must never gain a legacy write path.  The fixture therefore removes
    the three current-generation insert guards only around the historical rows,
    writes their byte-exact immutable witnesses, then restores the canonical SQL.
    """
    trigger_names = (
        "trg_structured_review_events_decision_witness",
        "trg_structured_review_events_capture_witness",
        "trg_task_review_event_witnesses_validate_insert",
    )
    trigger_sql = {
        name: conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (name,),
        ).fetchone()[0]
        for name in trigger_names
    }
    for name in trigger_names:
        conn.execute(f'DROP TRIGGER "{name}"')
    conn.executemany(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    event_ids = [row[0] for row in rows]
    placeholders = ",".join("?" for _ in event_ids)
    conn.execute(
        "INSERT INTO task_review_event_witnesses "
        "(event_id, event_internal_id, task_id, agent_id, event_type, level, "
        " message, payload_json, created_at, decision_id, witness_kind, schema_version) "
        "SELECT event_id, id, task_id, agent_id, event_type, level, message, "
        "payload_json, created_at, NULL, 'legacy_pre_instrumentation', 1 "
        f"FROM task_events WHERE event_id IN ({placeholders})",
        event_ids,
    )
    for name in trigger_names:
        conn.execute(trigger_sql[name])


def make_db(tmp_path: Path, *, include_outcomes: bool = True) -> Path:
    db = tmp_path / "fixture.db"
    init_db(db)
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO users (username, display_name, password_hash, is_active, created_at) VALUES (?,?,?,?,?)",
        [("u1", "用户一", "x", 1, OLD), ("u2", "用户二", "x", 0, OLD)],
    )
    rows = [
        # t1 is sealed only after its output file rows exist; the canonical
        # human-decision witness then accepts d1 and moves it to completed.
        ("t1", "a1", "0.1.0", "running", "用户一", "u1", RECENT, RECENT,
         None, "c1", "user", "[]", '["f1", "f2"]', None),
        ("t2", "a1", "0.1.0", "waiting_review", "用户一", "u1", RECENT,
         "2026-07-14T10:00:00", None, None, "user", '["f2"]', "[]", '["t1"]'),
        ("t3", "a2", "0.1.0", "failed", "用户二", "u2", RECENT, RECENT,
         None, None, "user", "[]", "[]", None),
        ("t4", "a1", "0.1.0", "completed", "用户一", "u1", OLD, OLD,
         OLD, None, "user", "[]", "[]", None),
        ("t5", "a1", "0.1.0", "completed", "评测", None, RECENT, RECENT,
         RECENT, None, "eval", "[]", '["ef1"]', None),
    ]
    conn.executemany(
        "INSERT INTO tasks "
        "(id, agent_id, agent_version, status, created_by, created_by_username, "
        " created_at, updated_at, finished_at, conversation_id, origin, "
        " input_file_ids, output_file_ids, depends_on) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.executemany(
        "INSERT INTO files "
        "(id, task_id, kind, filename, path, size_bytes, sha256, created_at, "
        " classification, uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("f1", "t1", "output", "f1.txt", "/tmp/f1", 10, "a" * 64, RECENT, "internal", None),
            ("f2", "t1", "output", "f2.txt", "/tmp/f2", 10, "b" * 64, RECENT, "internal", None),
            ("ef1", "t5", "output", "ef1.txt", "/tmp/ef1", 10, "c" * 64, RECENT, "internal", None),
        ],
    )
    conn.execute("UPDATE tasks SET status = 'waiting_review' WHERE id = 't1'")
    conn.execute(
        "INSERT INTO task_human_decisions "
        "(id, task_id, paired_advice_id, action, reason_code, comment, "
        " reviewer_username, reviewer_display_name, schema_version, created_at) "
        "VALUES ('d1', 't1', NULL, 'approve', NULL, NULL, 'u1', '用户一', 1, ?)",
        (DECISION_AT,),
    )
    conn.execute(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "e1",
            "t1",
            "a1",
            "review_approved",
            "info",
            "approved",
            (
                '{"reviewer":"用户一","reviewer_username":"u1",'
                '"comment":null,"decision_id":"d1","reason_code":null,'
                '"paired_advice_id":null}'
            ),
            RECENT,
        ),
    )
    _insert_pre_cutover_review_events(
        conn,
        [
            ("e3", "t3", "a2", "review_rejected", "warning", "rejected", "{}", RECENT),
            ("e4", "t4", "a1", "review_approved", "info", "approved", "{}", OLD),
            ("ee1", "t5", "a1", "review_approved", "info", "approved", "{}", RECENT),
        ],
    )
    conn.execute(
        "UPDATE tasks SET status = 'completed', updated_at = ?, "
        "finished_at = ?, error_message = NULL WHERE id = 't1'",
        (DECISION_AT, DECISION_AT),
    )
    conn.execute(
        "INSERT INTO conversations "
        "(id, agent_id, status, created_by, created_by_username, created_at, updated_at) "
        "VALUES ('c1', 'a1', 'active', '用户一', 'u1', ?, ?)",
        (RECENT, RECENT),
    )
    conn.executemany(
        "INSERT INTO model_calls (model_profile, status, created_at) VALUES (?,?,?)",
        [("reasoning", "success", RECENT), ("reasoning", "failed", RECENT)],
    )
    conn.execute(
        "INSERT INTO feedback (task_id, created_at) VALUES ('t1', ?)", (RECENT,)
    )
    if include_outcomes:
        _insert_outcome(
            conn,
            outcome_id="o1",
            event_type="capture_started",
            source_file_id="f1",
            created_at=RECENT,
        )
        _insert_outcome(
            conn,
            outcome_id="o2",
            event_type="capture_started",
            source_file_id="f2",
            created_at=RECENT,
        )
        # 同一产物两次真实完整交付必须保留为两个 event，distinct artifact 仍为 1。
        for outcome_id in ("o3", "o4"):
            _insert_outcome(
                conn,
                outcome_id=outcome_id,
                event_type="full_download",
                source_file_id="f1",
                actor_username="u1",
                delivered_bytes=10,
                created_at=RECENT,
            )
        _insert_outcome(
            conn,
            outcome_id="o5",
            event_type="pipeline_handoff",
            source_file_id="f2",
            downstream_task_id="t2",
            created_at=RECENT,
        )
    conn.commit()
    conn.close()
    return db


def test_counts_window_and_eval_isolation(tmp_path):
    report = usage_report.build_report(make_db(tmp_path), days=14, now=NOW)
    tasks = report["tasks"]
    assert tasks["created"] == 3                      # t4 窗口外、t5 eval 均排除
    assert tasks["by_status"] == {"completed": 1, "waiting_review": 1, "failed": 1}
    assert tasks["distinct_creators"] == 2
    assert tasks["by_creator"] == {"u1": 2, "u2": 1}
    assert tasks["completed_median_s"] == 300.0
    assert tasks["stalled_waiting_review"] == 1       # t2 updated 超 48h
    assert report["reviews"]["approved"] == 1
    assert report["reviews"]["rejected"] == 0
    assert report["reviews"]["judgment_coverage"] == {
        "status": "measured",
        "structured": 1,
        "legacy_unstructured": 1,
        "structured_ratio": 0.5,
        "by_reject_reason": {},
        "note": (
            "approved/rejected 仅计 exact decision-bound 终裁；"
            "legacy_unstructured 仅是严格代际切换前封存的 review event "
            "记录，不并入可信人签总数，也不反推 reason"
        ),
    }
    assert report["funnel"]["conversations"] == 1
    assert report["funnel"]["conversations_with_tasks"] == 1
    assert report["funnel"]["completed"] == 1
    assert report["model_calls"]["total"] == 2
    assert report["model_calls"]["failed"] == 1
    assert report["model_calls"]["tokens"] == "未知（model_calls 无总 token 列）"  # 缺列=未知绝不记 0
    assert report["feedback_count"] == 1
    assert report["accounts"] == {"total": 2, "active_flag": 1}
    assert report["artifact_outcomes"] == {
        "status": "measured",
        "schema_witnesses": {
            "outcome_table_shape": True,
            "required_indexes": True,
            "required_triggers": True,
            "provenance_integrity": True,
        },
        "observation_started_at": RECENT,
        "requested_window_start": "2026-07-04T12:00:00+00:00",
        "effective_window_start": RECENT,
        "requested_window_fully_covered": False,
        "capture_started": {
            "events": 2,
            "distinct_artifacts": 2,
            "distinct_source_tasks": 1,
        },
        "full_download": {
            "delivered_events_lower_bound": 2,
            "distinct_artifacts": 1,
            "distinct_source_tasks": 1,
            "distinct_actors": 1,
        },
        "pipeline_handoff": {
            "flowed_events_lower_bound": 1,
            "distinct_artifacts": 1,
            "distinct_source_tasks": 1,
            "distinct_downstream_tasks": 1,
        },
        "note": (
            "仅统计逐权威产物 capture_started 之后的 user-origin 事件；"
            "full_download=完整正文已交付，不代表采用（仅 200 GET）；"
            "pipeline_handoff=产物已流入下游任务，不代表被读取或采用"
        ),
    }


def test_legacy_event_on_structured_task_stays_out_of_trusted_decision_counts(
    tmp_path,
):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert_pre_cutover_review_events(
        conn,
        [
            (
                "e1-legacy-sibling",
                "t1",
                "a1",
                "review_approved",
                "info",
                "historical unstructured sibling",
                "{}",
                RECENT,
            )
        ],
    )
    conn.commit()
    conn.close()

    reviews = usage_report.build_report(db, days=14, now=NOW)["reviews"]
    assert reviews["approved"] == 1
    assert reviews["rejected"] == 0
    assert reviews["judgment_coverage"]["structured"] == 1
    assert reviews["judgment_coverage"]["legacy_unstructured"] == 2
    assert reviews["judgment_coverage"]["structured_ratio"] == 0.3333


def test_unwitnessed_post_cutover_legacy_event_makes_report_unknown(tmp_path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    trigger_names = (
        "trg_structured_review_events_decision_witness",
        "trg_structured_review_events_capture_witness",
    )
    trigger_sql = {
        name: conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (name,),
        ).fetchone()[0]
        for name in trigger_names
    }
    for name in trigger_names:
        conn.execute(f'DROP TRIGGER "{name}"')
    conn.execute(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES ('post-cutover-forged-legacy', 't1', 'a1', 'review_approved', "
        "'info', 'forged', '{}', ?)",
        (RECENT,),
    )
    for name in trigger_names:
        conn.execute(trigger_sql[name])
    conn.commit()
    conn.close()

    reviews = usage_report.build_report(db, days=14, now=NOW)["reviews"]
    assert reviews["status"] == "unknown_untrusted_judgment_ledger"
    assert reviews["schema_witnesses"]["required_triggers"] is True
    assert reviews["schema_witnesses"]["provenance_integrity"] is False
    assert "approved" not in reviews


def test_missing_columns_honest_unknown(tmp_path):
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (id TEXT)")  # 缺关键列
    conn.commit()
    conn.close()
    report = usage_report.build_report(db, days=14, now=NOW)
    assert isinstance(report["tasks"], str) and "未知" in report["tasks"]
    assert isinstance(report["reviews"], str) and "未知" in report["reviews"]
    assert isinstance(report["artifact_outcomes"], str) and "未知" in report["artifact_outcomes"]


def test_outcome_table_without_capture_is_unknown_not_fake_zero(tmp_path):
    db = make_db(tmp_path, include_outcomes=False)

    report = usage_report.build_report(db, days=14, now=NOW)

    assert report["artifact_outcomes"]["status"] == "unknown_no_instrumented_artifacts"
    assert "未知" in report["artifact_outcomes"]["full_download"]
    assert "未知" in report["artifact_outcomes"]["pipeline_handoff"]


def test_untrusted_judgment_ledger_never_emits_measured_review_counts(tmp_path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    trigger_name = "trg_task_human_decisions_no_delete"
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()[0]
    conn.execute(f"DROP TRIGGER {trigger_name}")
    conn.execute("DELETE FROM task_human_decisions WHERE id = 'd1'")
    conn.execute(trigger_sql)
    conn.commit()
    conn.close()

    report = usage_report.build_report(db, days=14, now=NOW)

    reviews = report["reviews"]
    assert reviews["status"] == "unknown_untrusted_judgment_ledger"
    assert reviews["schema_witnesses"]["required_triggers"] is True
    assert reviews["schema_witnesses"]["provenance_integrity"] is False
    assert "approved" not in reviews
    assert "rejected" not in reviews


def test_future_first_capture_is_unknown_not_measured(tmp_path):
    db = make_db(tmp_path, include_outcomes=False)
    conn = sqlite3.connect(db)
    _insert_outcome(
        conn,
        outcome_id="o_future",
        event_type="capture_started",
        source_file_id="f1",
        created_at=FUTURE,
    )
    conn.commit()
    conn.close()

    report = usage_report.build_report(db, days=14, now=NOW)

    outcomes = report["artifact_outcomes"]
    assert outcomes["status"] == "unknown_future_capture_timestamp"
    assert "未知" in outcomes["capture_started"]
    assert "未知" in outcomes["full_download"]
    assert "未知" in outcomes["pipeline_handoff"]


def test_future_outcome_is_excluded_from_point_in_time_counts(tmp_path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert_outcome(
        conn,
        outcome_id="o_future",
        event_type="full_download",
        source_file_id="f1",
        actor_username="u2",
        delivered_bytes=10,
        created_at=FUTURE,
    )
    conn.commit()
    conn.close()

    report = usage_report.build_report(db, days=14, now=NOW)

    assert report["artifact_outcomes"]["status"] == "measured"
    assert report["artifact_outcomes"]["full_download"] == {
        "delivered_events_lower_bound": 2,
        "distinct_artifacts": 1,
        "distinct_source_tasks": 1,
        "distinct_actors": 1,
    }


def test_future_rows_are_excluded_from_every_time_windowed_section(tmp_path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks "
        "(id, agent_id, agent_version, status, created_by, created_by_username, "
        " created_at, updated_at, origin, input_file_ids, output_file_ids) "
        "VALUES ('future-task', 'a1', '0.1.0', 'waiting_review', '未来用户', 'future', "
        " ?, ?, 'user', '[]', '[]')",
        (FUTURE, FUTURE),
    )
    conn.execute(
        "INSERT INTO task_human_decisions "
        "(id, task_id, paired_advice_id, action, reason_code, comment, "
        " reviewer_username, reviewer_display_name, schema_version, created_at) "
        "VALUES ('future-decision', 'future-task', NULL, 'reject', "
        "'insufficient_evidence', NULL, 'future', '未来用户', 1, ?)",
        (FUTURE,),
    )
    conn.execute(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES ('future-review', 'future-task', 'a1', 'review_rejected', "
        "'warning', 'future', ?, ?)",
        (
            '{"reviewer":"未来用户","reviewer_username":"future",'
            '"comment":null,"decision_id":"future-decision",'
            '"reason_code":"insufficient_evidence","paired_advice_id":null}',
            FUTURE,
        ),
    )
    conn.execute(
        "UPDATE tasks SET status = 'failed', updated_at = ?, finished_at = ?, "
        "error_message = '人工拒绝（reviewer=未来用户；reason=insufficient_evidence）' "
        "WHERE id = 'future-task'",
        (FUTURE, FUTURE),
    )
    conn.execute(
        "INSERT INTO conversations "
        "(id, agent_id, status, created_by, created_by_username, created_at, updated_at) "
        "VALUES ('future-conv', 'a1', 'active', '未来用户', 'future', ?, ?)",
        (FUTURE, FUTURE),
    )
    conn.execute(
        "INSERT INTO model_calls (model_profile, status, created_at) "
        "VALUES ('reasoning', 'failed', ?)",
        (FUTURE,),
    )
    conn.execute(
        "INSERT INTO feedback (task_id, created_at) VALUES ('future-task', ?)",
        (FUTURE,),
    )
    conn.commit()
    conn.close()

    report = usage_report.build_report(db, days=14, now=NOW)

    assert report["tasks"]["created"] == 3
    assert report["tasks"]["by_status"] == {
        "completed": 1,
        "waiting_review": 1,
        "failed": 1,
    }
    assert report["reviews"]["approved"] == 1
    assert report["reviews"]["rejected"] == 0
    assert report["reviews"]["judgment_coverage"]["by_reject_reason"] == {}
    assert report["funnel"]["conversations"] == 1
    assert report["funnel"]["conversations_with_tasks"] == 1
    assert report["model_calls"]["total"] == 2
    assert report["model_calls"]["failed"] == 1
    assert report["feedback_count"] == 1


def test_completed_median_excludes_tasks_finished_after_report_snapshot(tmp_path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks "
        "(id, agent_id, agent_version, status, created_by, created_by_username, "
        " created_at, updated_at, finished_at, origin, input_file_ids, output_file_ids) "
        "VALUES ('future-finished-task', 'a1', '0.1.0', 'completed', "
        "'用户一', 'u1', ?, ?, ?, 'user', '[]', '[]')",
        (RECENT, FUTURE, FUTURE),
    )
    conn.commit()
    conn.close()

    report = usage_report.build_report(db, days=14, now=NOW)

    assert report["tasks"]["completed_median_s"] == 300.0


def test_same_second_pre_generation_outcome_is_not_lost_by_display_truncation(
    tmp_path,
):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    _insert_outcome(
        conn,
        outcome_id="o_same_second",
        event_type="full_download",
        source_file_id="f1",
        actor_username="u2",
        delivered_bytes=10,
        created_at="2026-07-18T12:00:00.500000+00:00",
    )
    conn.commit()
    conn.close()

    report = usage_report.build_report(
        db,
        days=14,
        now=dt.datetime(
            2026,
            7,
            18,
            12,
            0,
            0,
            900_000,
            tzinfo=dt.timezone.utc,
        ),
    )

    assert report["generated_at"] == "2026-07-18T12:00:00+00:00"
    assert report["artifact_outcomes"]["full_download"][
        "delivered_events_lower_bound"
    ] == 3


def test_report_reads_one_wal_snapshot_during_concurrent_outcome_write(
    tmp_path, monkeypatch
):
    db = make_db(tmp_path)
    real_connect = sqlite3.connect
    setup = real_connect(db)
    assert setup.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    setup.close()

    reader_reached_outcomes = threading.Event()
    writer_committed = threading.Event()
    writer_errors: list[BaseException] = []

    def writer() -> None:
        try:
            assert reader_reached_outcomes.wait(timeout=5)
            write_conn = real_connect(db, timeout=5)
            try:
                _insert_outcome(
                    write_conn,
                    outcome_id="o_concurrent",
                    event_type="full_download",
                    source_file_id="f1",
                    actor_username="u2",
                    delivered_bytes=10,
                    created_at=RECENT,
                )
                write_conn.commit()
            finally:
                write_conn.close()
        except BaseException as exc:  # pragma: no cover - re-raised in reader thread
            writer_errors.append(exc)
        finally:
            writer_committed.set()

    writer_thread = threading.Thread(target=writer, daemon=True)
    writer_thread.start()

    def instrumented_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        database = str(args[0] if args else kwargs.get("database", ""))
        if "mode=ro" in database:
            paused = False

            def trace(sql: str) -> None:
                nonlocal paused
                if not paused and "MIN(outcome.created_at)" in sql:
                    paused = True
                    reader_reached_outcomes.set()
                    writer_committed.wait(timeout=5)

            conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(usage_report.sqlite3, "connect", instrumented_connect)
    report = usage_report.build_report(db, days=14, now=NOW)
    writer_thread.join(timeout=5)

    assert not writer_thread.is_alive()
    assert writer_errors == []
    assert report["artifact_outcomes"]["full_download"][
        "delivered_events_lower_bound"
    ] == 2
    verify = real_connect(db)
    try:
        assert verify.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'full_download'"
        ).fetchone()[0] == 3
    finally:
        verify.close()


def test_naive_injected_clock_is_interpreted_as_utc_not_local_time(tmp_path):
    naive_now = dt.datetime(2026, 7, 18, 12, 0, 0)
    report = usage_report.build_report(make_db(tmp_path), days=14, now=naive_now)

    assert report["generated_at"] == "2026-07-18T12:00:00+00:00"
    assert report["tasks"]["created"] == 3


def test_missing_db_fails_closed(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(tmp_path / "nope.db")],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "fail-closed" in proc.stderr


def test_cli_markdown_renders(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(make_db(tmp_path)), "--days", "9999"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert "FLAi-OS 使用遥测" in proc.stdout
    assert "绝不以 0 充数" in proc.stdout
    assert "完整正文已交付，不代表采用" in proc.stdout
    assert "已流入下游任务，不代表被读取或采用" in proc.stdout
