"""M4 前置产物结果遥测：只记可证明的签发产物流转，不把交付冒充采用。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import anyio
import pytest
from starlette.requests import Request

from backend.app.api import files as files_api
from backend.app.api.files import _VerifiedFileResponse, download_file
from backend.app.core.errors import IllegalTransitionError
from backend.app.jobs.runner import resolve_dependencies_once
from backend.app.storage import db as db_mod
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.storage.outcome_schema import outcome_schema_witnesses

TEST_USERNAME = "test_engineer"


def _create_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    origin: str = "user",
    depends_on: list[str] | None = None,
    input_file_ids: list[str] | None = None,
) -> dict:
    return repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name=task_id,
        created_by="测试工程师",
        created_by_username=TEST_USERNAME,
        inputs={},
        input_file_ids=input_file_ids,
        metadata={},
        origin=origin,
        depends_on=depends_on,
    )


def _attach_output(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    file_id: str | None = None,
    path: Path | None = None,
    content: bytes = b"signed-output",
) -> str:
    file_id = file_id or f"file_{uuid.uuid4().hex}"
    if path is None:
        path = Path(f"/tmp/{file_id}.txt")
    repos.create_file(
        conn,
        file_id=file_id,
        task_id=task_id,
        kind="output",
        filename=path.name,
        path=str(path),
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        classification="internal",
    )
    task = repos.get_task(conn, task_id)
    repos.set_task_outputs(conn, task_id, [*task["output_file_ids"], file_id])
    return file_id


def _approve(conn: sqlite3.Connection, task_id: str) -> str:
    for status in ("queued", "validating", "running", "waiting_review"):
        repos.set_task_status(conn, task_id, status)
    repos.apply_human_review(
        conn,
        task_id,
        action="approve",
        reviewer="测试工程师",
        reviewer_username=TEST_USERNAME,
        reason_code=None,
        comment="已核对",
    )
    row = conn.execute(
        "SELECT event_id FROM task_events "
        "WHERE task_id = ? AND event_type = 'review_approved'",
        (task_id,),
    ).fetchone()
    assert row is not None
    return str(row["event_id"])


def _capture_snapshots(
    conn: sqlite3.Connection, source_file_id: str
) -> tuple[str, str]:
    row = conn.execute(
        "SELECT source_task_witness_json, source_file_witness_json "
        "FROM artifact_outcome_events "
        "WHERE event_type = 'capture_started' AND source_file_id = ?",
        (source_file_id,),
    ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1])


def _replace_with_empty_pre_snapshot_outcome_table(
    conn: sqlite3.Connection,
) -> None:
    artifact_trigger_names = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'trigger' AND tbl_name = 'artifact_outcome_events'"
        )
    ]
    for trigger_name in artifact_trigger_names:
        conn.execute(f"DROP TRIGGER {trigger_name}")
    for index_name in db_mod._OUTCOME_MANAGED_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {index_name}")
    conn.execute("DROP TABLE artifact_outcome_events")
    conn.execute(
        """
        CREATE TABLE artifact_outcome_events (
            id TEXT PRIMARY KEY NOT NULL,
            event_type TEXT NOT NULL,
            source_task_id TEXT NOT NULL REFERENCES tasks(id),
            source_file_id TEXT NOT NULL REFERENCES files(id),
            review_event_id TEXT NOT NULL REFERENCES task_events(event_id),
            actor_username TEXT,
            downstream_task_id TEXT REFERENCES tasks(id),
            delivered_bytes INTEGER,
            schema_version INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


@pytest.fixture()
def outcome_db(tmp_path: Path):
    db_path = tmp_path / "outcomes.db"
    init_db(db_path)
    return db_path


def test_capture_is_created_only_for_new_user_approval_and_not_backfilled(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM artifact_outcome_events").fetchone()[0] == 0
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")

        row = conn.execute("SELECT * FROM artifact_outcome_events").fetchone()
        assert row is not None
        assert row["event_type"] == "capture_started"
        assert row["source_task_id"] == "source"
        assert row["source_file_id"] == file_id
        assert row["review_event_id"] == review_event_id
        assert row["actor_username"] is None
        assert row["downstream_task_id"] is None
        assert row["delivered_bytes"] is None
    finally:
        conn.close()


def test_invalid_foreign_non_user_unsigned_and_bad_download_rows_are_rejected(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "signed")
        signed_file = _attach_output(conn, "signed")
        review_event_id = _approve(conn, "signed")

        _create_task(conn, "unsigned")
        unsigned_file = _attach_output(conn, "unsigned")
        _create_task(conn, "eval-source", origin="eval")
        eval_file = _attach_output(conn, "eval-source")
        eval_review = _approve(conn, "eval-source")

        invalid_rows = [
            dict(
                event_type="capture_started",
                source_task_id="missing",
                source_file_id=signed_file,
                review_event_id=review_event_id,
            ),
            dict(
                event_type="capture_started",
                source_task_id="signed",
                source_file_id=unsigned_file,
                review_event_id=review_event_id,
            ),
            dict(
                event_type="capture_started",
                source_task_id="eval-source",
                source_file_id=eval_file,
                review_event_id=eval_review,
            ),
            dict(
                event_type="capture_started",
                source_task_id="unsigned",
                source_file_id=unsigned_file,
                review_event_id=review_event_id,
            ),
            dict(
                event_type="full_download",
                source_task_id="signed",
                source_file_id=signed_file,
                review_event_id=review_event_id,
                actor_username="\n\t",
                delivered_bytes=len(b"signed-output"),
            ),
            dict(
                event_type="full_download",
                source_task_id="signed",
                source_file_id=signed_file,
                review_event_id=review_event_id,
                actor_username=TEST_USERNAME,
                delivered_bytes=1,
            ),
        ]
        before = conn.execute("SELECT COUNT(*) FROM artifact_outcome_events").fetchone()[0]
        for row in invalid_rows:
            with pytest.raises((sqlite3.IntegrityError, ValueError)):
                repos.append_artifact_outcome_event(conn, **row)
        assert conn.execute("SELECT COUNT(*) FROM artifact_outcome_events").fetchone()[0] == before
    finally:
        conn.close()


def test_capture_requires_exact_approve_decision_bound_by_event_payload(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        for status in ("queued", "validating", "running", "waiting_review"):
            repos.set_task_status(conn, "source", status)
        conn.execute(
            "INSERT INTO task_human_decisions "
            "(id, task_id, paired_advice_id, action, reason_code, comment, "
            " reviewer_username, reviewer_display_name, schema_version, created_at) "
            "VALUES ('decision_exact', 'source', NULL, 'approve', NULL, NULL, "
            " 'reviewer', '评审员', 1, '2026-07-19T00:00:00+00:00')"
        )
        repos.append_event(
            conn,
            task_id="source",
            agent_id="hello_agent",
            event_type="review_approved",
            level="info",
            message="exact exit witness",
            payload={
                "reviewer": "评审员",
                "reviewer_username": "reviewer",
                "comment": None,
                "decision_id": "decision_exact",
                "reason_code": None,
                "paired_advice_id": None,
            },
        )
        conn.execute(
            "UPDATE tasks SET status = 'completed', "
            "updated_at = '2026-07-19T00:00:00+00:00', "
            "finished_at = '2026-07-19T00:00:00+00:00', "
            "error_message = NULL WHERE id = 'source'"
        )
        non_review_event = repos.append_event(
            conn,
            task_id="source",
            agent_id="hello_agent",
            event_type="task_completed",
            level="info",
            message="not a signer witness",
            payload={},
        )

        with pytest.raises(sqlite3.IntegrityError, match="exact approval"):
            repos.append_artifact_outcome_event(
                conn,
                event_type="capture_started",
                source_task_id="source",
                source_file_id=file_id,
                review_event_id=non_review_event["event_id"],
            )
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_outcome_ledger_blocks_update_delete_replace_and_explicit_rowid_replace(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        repos.append_artifact_outcome_event(
            conn,
            event_type="full_download",
            source_task_id="source",
            source_file_id=file_id,
            review_event_id=review_event_id,
            actor_username=TEST_USERNAME,
            delivered_bytes=len(b"signed-output"),
        )
        row = conn.execute(
            "SELECT rowid, * FROM artifact_outcome_events "
            "WHERE event_type = 'full_download'"
        ).fetchone()
        assert row is not None
        columns = (
            "id, event_type, source_task_id, source_file_id, review_event_id, "
            "source_task_witness_json, source_file_witness_json, "
            "actor_username, downstream_task_id, delivered_bytes, schema_version, created_at"
        )
        task_snapshot, file_snapshot = _capture_snapshots(conn, file_id)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE artifact_outcome_events SET created_at = created_at WHERE id = ?",
                (row["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM artifact_outcome_events WHERE id = ?", (row["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT OR REPLACE INTO artifact_outcome_events ({columns}) "
                f"SELECT {columns} FROM artifact_outcome_events WHERE id = ?",
                (row["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT OR REPLACE INTO artifact_outcome_events "
                "(rowid, id, event_type, source_task_id, source_file_id, review_event_id, "
                " source_task_witness_json, source_file_witness_json, "
                " actor_username, downstream_task_id, delivered_bytes, schema_version, created_at) "
                "VALUES (?, ?, 'full_download', 'source', ?, ?, ?, ?, ?, NULL, ?, 1, ?)",
                (
                    row["rowid"],
                    f"outcome_{uuid.uuid4().hex}",
                    file_id,
                    review_event_id,
                    task_snapshot,
                    file_snapshot,
                    TEST_USERNAME,
                    len(b"signed-output"),
                    row["created_at"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO artifact_outcome_events "
                "(rowid, id, event_type, source_task_id, source_file_id, review_event_id, "
                " source_task_witness_json, source_file_witness_json, "
                " actor_username, downstream_task_id, delivered_bytes, schema_version, created_at) "
                "VALUES (-1, ?, 'full_download', 'source', ?, ?, ?, ?, ?, NULL, ?, 1, ?)",
                (
                    f"outcome_{uuid.uuid4().hex}",
                    file_id,
                    review_event_id,
                    task_snapshot,
                    file_snapshot,
                    TEST_USERNAME,
                    len(b"signed-output"),
                    row["created_at"],
                ),
            )
    finally:
        conn.close()


def _raw_row(conn: sqlite3.Connection, table: str, row_id: str) -> tuple:
    row = conn.execute(
        f'SELECT rowid, * FROM "{table}" WHERE id = ?', (row_id,)
    ).fetchone()
    assert row is not None
    return tuple(row)


def _replace_row(
    conn: sqlite3.Connection,
    table: str,
    row_id: str,
    *,
    changes: dict[str, object],
) -> None:
    columns = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]
    current = conn.execute(
        f'SELECT {", ".join(columns)} FROM "{table}" WHERE id = ?', (row_id,)
    ).fetchone()
    assert current is not None
    values = dict(zip(columns, tuple(current), strict=True))
    values.update(changes)
    conn.execute(
        f'INSERT OR REPLACE INTO "{table}" ({", ".join(columns)}) '
        f'VALUES ({", ".join("?" for _ in columns)})',
        tuple(values[column] for column in columns),
    )


def test_witnessed_parent_rows_block_delete_and_replace_with_recursive_triggers_off(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        _approve(conn, "source")
        _create_task(conn, "downstream", depends_on=["source"])
        repos.enqueue_dependent_task(conn, "downstream", [file_id])

        originals = {
            ("files", file_id): _raw_row(conn, "files", file_id),
            ("tasks", "source"): _raw_row(conn, "tasks", "source"),
            ("tasks", "downstream"): _raw_row(conn, "tasks", "downstream"),
        }
        conn.execute("PRAGMA recursive_triggers = OFF")
        attacks = (
            ("files", file_id, {"kind": "input", "size_bytes": 1}),
            ("tasks", "source", {"origin": "eval", "output_file_ids": "[]"}),
            ("tasks", "downstream", {"origin": "eval", "depends_on": "[]"}),
        )
        for table, row_id, changes in attacks:
            with pytest.raises(sqlite3.IntegrityError):
                _replace_row(conn, table, row_id, changes=changes)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f'DELETE FROM "{table}" WHERE id = ?', (row_id,))
            assert _raw_row(conn, table, row_id) == originals[(table, row_id)]
    finally:
        conn.close()


def test_unwitnessed_sibling_update_or_replace_cannot_evict_witnessed_parent(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        _approve(conn, "source")
        _create_task(conn, "downstream", depends_on=["source"])
        repos.enqueue_dependent_task(conn, "downstream", [file_id])

        repos.create_file(
            conn,
            file_id="sibling-file",
            task_id=None,
            kind="input",
            filename="sibling.txt",
            path="/tmp/sibling.txt",
            size_bytes=1,
            sha256="0" * 64,
            classification="internal",
        )
        _create_task(conn, "sibling-terminal")
        _create_task(conn, "sibling-handoff")
        originals = {
            ("files", file_id): _raw_row(conn, "files", file_id),
            ("files", "sibling-file"): _raw_row(conn, "files", "sibling-file"),
            ("tasks", "source"): _raw_row(conn, "tasks", "source"),
            ("tasks", "downstream"): _raw_row(conn, "tasks", "downstream"),
            ("tasks", "sibling-terminal"): _raw_row(conn, "tasks", "sibling-terminal"),
            ("tasks", "sibling-handoff"): _raw_row(conn, "tasks", "sibling-handoff"),
        }
        victim_rowids = {
            (table, row_id): original[0]
            for (table, row_id), original in originals.items()
        }
        conn.execute("PRAGMA recursive_triggers = OFF")

        attacks = (
            ("files", "sibling-file", file_id, "id"),
            ("files", "sibling-file", victim_rowids[("files", file_id)], "rowid"),
            ("tasks", "sibling-terminal", "source", "id"),
            ("tasks", "sibling-terminal", victim_rowids[("tasks", "source")], "rowid"),
            ("tasks", "sibling-handoff", "downstream", "id"),
            ("tasks", "sibling-handoff", victim_rowids[("tasks", "downstream")], "rowid"),
        )
        for table, sibling_id, target, column in attacks:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    f'UPDATE OR REPLACE "{table}" SET {column} = ? WHERE id = ?',
                    (target, sibling_id),
                )
            for key, original in originals.items():
                assert _raw_row(conn, *key) == original
    finally:
        conn.close()


def test_waiting_review_freezes_exact_manifest_and_referenced_file_records(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        reviewed_file = _attach_output(conn, "source", file_id="reviewed-file")
        repos.create_file(
            conn,
            file_id="late-file",
            task_id="source",
            kind="output",
            filename="late.txt",
            path="/tmp/late.txt",
            size_bytes=4,
            sha256=hashlib.sha256(b"late").hexdigest(),
            classification="internal",
        )
        for status in ("queued", "validating", "running", "waiting_review"):
            repos.set_task_status(conn, "source", status)

        task_before = _raw_row(conn, "tasks", "source")
        file_before = _raw_row(conn, "files", reviewed_file)
        conn.execute("PRAGMA recursive_triggers = OFF")
        with pytest.raises(IllegalTransitionError):
            repos.set_task_outputs(conn, "source", [reviewed_file, "late-file"])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE files SET path = '/tmp/rewritten.txt' WHERE id = ?",
                (reviewed_file,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            _replace_row(
                conn,
                "files",
                reviewed_file,
                changes={"sha256": "f" * 64, "classification": "sensitive"},
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM files WHERE id = ?", (reviewed_file,))
        assert _raw_row(conn, "tasks", "source") == task_before
        assert _raw_row(conn, "files", reviewed_file) == file_before

        repos.apply_human_review(
            conn,
            "source",
            action="approve",
            reviewer="测试工程师",
            reviewer_username=TEST_USERNAME,
            reason_code=None,
            comment="只批准冻结包",
        )
        assert repos.get_task(conn, "source")["output_file_ids"] == [reviewed_file]
        captured = conn.execute(
            "SELECT source_file_id FROM artifact_outcome_events "
            "WHERE event_type = 'capture_started' ORDER BY source_file_id"
        ).fetchall()
        assert [row[0] for row in captured] == [reviewed_file]
    finally:
        conn.close()


def test_waiting_review_freezes_task_provenance_before_and_after_decision(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        _attach_output(conn, "source")
        for status in ("queued", "validating", "running"):
            repos.set_task_status(conn, "source", status)
        running = _raw_row(conn, "tasks", "source")
        with pytest.raises(sqlite3.IntegrityError, match="review task provenance"):
            conn.execute(
                "UPDATE tasks SET status = 'waiting_review', origin = 'eval' "
                "WHERE id = 'source'"
            )
        assert _raw_row(conn, "tasks", "source") == running

        repos.set_task_status(conn, "source", "waiting_review")
        original = _raw_row(conn, "tasks", "source")

        for assignment in (
            "origin = 'eval'",
            "agent_id = 'review_swapped_agent'",
            "agent_version = '999.0.0'",
            "inputs_json = '{\"changed\":true}'",
            "input_file_ids = '[\"late-input\"]'",
            "data_classification = 'sensitive'",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="review task provenance"):
                conn.execute(f"UPDATE tasks SET {assignment} WHERE id = 'source'")
            assert _raw_row(conn, "tasks", "source") == original

        repos.apply_human_review(
            conn,
            "source",
            action="reject",
            reviewer="测试工程师",
            reviewer_username=TEST_USERNAME,
            reason_code="method_error",
            comment="冻结任务 provenance",
        )
        with pytest.raises(sqlite3.IntegrityError, match="review task provenance"):
            conn.execute("UPDATE tasks SET origin = 'eval' WHERE id = 'source'")
    finally:
        conn.close()


def test_waiting_review_exit_requires_exact_decision_and_review_event(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        for task_id in ("no-witness", "decision-only", "exact-witness"):
            _create_task(conn, task_id)
            for status in ("queued", "validating", "running", "waiting_review"):
                repos.set_task_status(conn, task_id, status)

        with pytest.raises(IllegalTransitionError, match="apply_human_review"):
            repos.set_task_status(conn, "no-witness", "completed")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE tasks SET status = 'completed' WHERE id = 'no-witness'"
            )

        for task_id in ("decision-only", "exact-witness"):
            conn.execute(
                "INSERT INTO task_human_decisions "
                "(id, task_id, paired_advice_id, action, reason_code, comment, "
                " reviewer_username, reviewer_display_name, schema_version, created_at) "
                "VALUES (?, ?, NULL, 'approve', NULL, NULL, 'reviewer', '评审员', 1, ?)",
                (f"decision-{task_id}", task_id, "2026-07-19T00:00:00+00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE tasks SET status = 'completed' WHERE id = 'decision-only'"
            )

        repos.append_event(
            conn,
            task_id="exact-witness",
            agent_id="hello_agent",
            event_type="review_approved",
            level="info",
            message="exact human witness",
            payload={
                "reviewer": "评审员",
                "reviewer_username": "reviewer",
                "comment": None,
                "decision_id": "decision-exact-witness",
                "reason_code": None,
                "paired_advice_id": None,
            },
        )
        conn.execute(
            "UPDATE tasks SET status = 'completed', "
            "updated_at = '2026-07-19T00:00:00+00:00', "
            "finished_at = '2026-07-19T00:00:00+00:00', "
            "error_message = NULL WHERE id = 'exact-witness'"
        )
        assert repos.get_task(conn, "exact-witness")["status"] == "completed"
    finally:
        conn.close()


def test_terminal_task_freezes_identity_status_and_exact_output_manifest(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "terminal")
        for status in ("queued", "validating", "running", "analyzing"):
            repos.set_task_status(conn, "terminal", status)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE tasks SET status = 'completed', output_file_ids = '[\"late\"]' "
                "WHERE id = 'terminal'"
            )
        assert repos.get_task(conn, "terminal")["status"] == "analyzing"
        repos.set_task_status(conn, "terminal", "completed")

        # Non-provenance maintenance remains legal after terminalization.
        conn.execute(
            "UPDATE tasks SET metadata_json = '{\"note\":\"kept\"}', "
            "data_classification = 'internal' WHERE id = 'terminal'"
        )
        original = _raw_row(conn, "tasks", "terminal")
        conn.execute("PRAGMA recursive_triggers = OFF")
        with pytest.raises(IllegalTransitionError):
            repos.set_task_outputs(conn, "terminal", ["late"])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE tasks SET status = 'failed' WHERE id = 'terminal'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            _replace_row(conn, "tasks", "terminal", changes={"output_file_ids": '["late"]'})
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM tasks WHERE id = 'terminal'")
        assert _raw_row(conn, "tasks", "terminal") == original
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("trigger_name", "trigger_event"),
    (
        ("trg_task_events_no_update", "UPDATE"),
        ("trg_task_events_no_delete", "DELETE"),
        ("trg_task_events_no_conflicting_insert", "INSERT"),
    ),
)
def test_task_event_append_only_triggers_are_exact_outcome_witnesses(
    outcome_db: Path,
    trigger_name: str,
    trigger_event: str,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        _attach_output(conn, "source")
        _approve(conn, "source")
        conn.execute(f"DROP TRIGGER {trigger_name}")
        conn.execute(
            f"CREATE TRIGGER {trigger_name} BEFORE {trigger_event} ON task_events "
            "BEGIN SELECT 1; END"
        )
        assert outcome_schema_witnesses(conn)["required_triggers"] is False
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="required_triggers"):
        init_db(outcome_db)


def test_one_signed_artifact_cannot_join_two_capture_cohorts(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        first_review = _approve(conn, "source")
        decision = repos.get_human_decision(conn, "source")
        assert decision is not None
        with pytest.raises(sqlite3.IntegrityError, match="structured review event"):
            repos.append_event(
                conn,
                task_id="source",
                agent_id="hello_agent",
                event_type="review_approved",
                level="info",
                message="对抗性重复 signer event",
                payload={
                    "reviewer": decision["reviewer_display_name"],
                    "reviewer_username": decision["reviewer_username"],
                    "comment": decision["comment"],
                    "decision_id": decision["id"],
                    "reason_code": decision["reason_code"],
                    "paired_advice_id": decision["paired_advice_id"],
                },
            )
        assert conn.execute(
            "SELECT COUNT(*) FROM task_events "
            "WHERE task_id = 'source' AND event_type = 'review_approved'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'capture_started' AND source_file_id = ? "
            "AND review_event_id = ?",
            (file_id, first_review),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_legacy_task_event_history_without_outcome_generation_can_upgrade(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "legacy-source")
        repos.append_event(
            conn,
            task_id="legacy-source",
            agent_id="hello_agent",
            event_type="task_created",
            level="info",
            message="pre-outcome history",
            payload={},
        )
        for trigger_name in db_mod._OUTCOME_MANAGED_TRIGGERS:
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
        for index_name in db_mod._OUTCOME_MANAGED_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        conn.execute("DROP TABLE artifact_outcome_events")
        for trigger_name in db_mod._OUTCOME_SHARED_PARENT_TRIGGERS:
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    finally:
        conn.close()

    init_db(outcome_db)
    conn = get_conn(outcome_db)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = 'legacy-source'"
        ).fetchone()[0] == 1
        assert all(value is True for value in outcome_schema_witnesses(conn).values())
    finally:
        conn.close()


def test_empty_pre_snapshot_outcome_generation_can_upgrade(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _replace_with_empty_pre_snapshot_outcome_table(conn)
    finally:
        conn.close()

    init_db(outcome_db)
    conn = get_conn(outcome_db)
    try:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_xinfo(artifact_outcome_events)")
        }
        assert {
            "source_task_witness_json",
            "source_file_witness_json",
        }.issubset(columns)
        assert all(value is True for value in outcome_schema_witnesses(conn).values())
    finally:
        conn.close()


def test_empty_pre_snapshot_ledger_with_review_evidence_requires_manual_migration(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "historical-task")
        repos.append_event(
            conn,
            task_id="historical-task",
            agent_id="hello_agent",
            event_type="task_created",
            level="info",
            message="outcome generation already had review-adjacent evidence",
            payload={},
        )
        _replace_with_empty_pre_snapshot_outcome_table(conn)
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="manual migration"):
        init_db(outcome_db)


def test_nonempty_review_seal_cannot_be_repaired_over_noop_guard(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "rejected-source")
        file_id = _attach_output(conn, "rejected-source")
        for status in ("queued", "validating", "running", "waiting_review"):
            repos.set_task_status(conn, "rejected-source", status)
        repos.apply_human_review(
            conn,
            "rejected-source",
            action="reject",
            reviewer="测试工程师",
            reviewer_username=TEST_USERNAME,
            reason_code="insufficient_evidence",
            comment="证据不足",
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events"
        ).fetchone()[0] == 0
        conn.execute("DROP TRIGGER trg_review_package_files_no_update")
        conn.execute(
            "CREATE TRIGGER trg_review_package_files_no_update "
            "BEFORE UPDATE ON files BEGIN SELECT 1; END"
        )
        conn.execute(
            "UPDATE files SET sha256 = ? WHERE id = ?",
            ("f" * 64, file_id),
        )
        noop_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
            "AND name = 'trg_review_package_files_no_update'"
        ).fetchone()[0]
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="review seal"):
        init_db(outcome_db)
    conn = get_conn(outcome_db)
    try:
        assert conn.execute(
            "SELECT sha256 FROM files WHERE id = ?", (file_id,)
        ).fetchone()[0] == "f" * 64
        assert conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
            "AND name = 'trg_review_package_files_no_update'"
        ).fetchone()[0] == noop_sql
    finally:
        conn.close()


def test_outcome_shape_trigger_rechecks_constraints_when_pragma_disables_them(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        task_snapshot, file_snapshot = _capture_snapshots(conn, file_id)
        conn.execute("PRAGMA ignore_check_constraints = ON")
        with pytest.raises(sqlite3.IntegrityError, match="outcome event shape"):
            conn.execute(
                "INSERT INTO artifact_outcome_events "
                "(id, event_type, source_task_id, source_file_id, review_event_id, "
                " source_task_witness_json, source_file_witness_json, "
                " actor_username, downstream_task_id, delivered_bytes, schema_version, created_at) "
                "VALUES (?, 'fabricated', 'source', ?, ?, ?, ?, NULL, NULL, -7, 99, ?)",
                (
                    f"outcome_{uuid.uuid4().hex}",
                    file_id,
                    review_event_id,
                    task_snapshot,
                    file_snapshot,
                    "2026-07-19T00:00:01+00:00",
                ),
            )
    finally:
        conn.close()


def test_deep_witness_rejects_preexisting_invalid_outcome_shape(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        task_snapshot, file_snapshot = _capture_snapshots(conn, file_id)
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
            "AND name = 'trg_artifact_outcomes_validate_shape'"
        ).fetchone()[0]
        conn.execute("DROP TRIGGER trg_artifact_outcomes_validate_shape")
        conn.execute("PRAGMA ignore_check_constraints = ON")
        conn.execute(
            "INSERT INTO artifact_outcome_events "
            "(id, event_type, source_task_id, source_file_id, review_event_id, "
            " source_task_witness_json, source_file_witness_json, "
            " actor_username, downstream_task_id, delivered_bytes, schema_version, created_at) "
            "VALUES (?, 'fabricated', 'source', ?, ?, ?, ?, NULL, NULL, -7, 99, ?)",
            (
                f"outcome_{uuid.uuid4().hex}",
                file_id,
                review_event_id,
                task_snapshot,
                file_snapshot,
                "2026-07-19T00:00:01+00:00",
            ),
        )
        conn.execute(trigger_sql)
        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="provenance_integrity"):
        init_db(outcome_db)


def test_outcome_requires_exact_review_event_witness_for_flow_and_deep_trust(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        trigger_name = "trg_task_review_event_witnesses_no_delete"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            "DELETE FROM task_review_event_witnesses WHERE event_id = ?",
            (review_event_id,),
        )
        conn.execute(trigger_sql)

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
        with pytest.raises(sqlite3.IntegrityError, match="exact approval"):
            repos.append_artifact_outcome_event(
                conn,
                event_type="full_download",
                source_task_id="source",
                source_file_id=file_id,
                review_event_id=review_event_id,
                actor_username=TEST_USERNAME,
                delivered_bytes=len(b"signed-output"),
            )
    finally:
        conn.close()


def test_outcome_trust_composes_review_event_witness_guard_contract(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        _attach_output(conn, "source")
        _approve(conn, "source")
        trigger_name = "trg_task_review_event_witnesses_no_delete"
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            f'CREATE TRIGGER "{trigger_name}" '
            "BEFORE DELETE ON task_review_event_witnesses BEGIN SELECT 1; END"
        )

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()


def test_outcome_rejects_noncanonical_text_timestamp_and_deep_bypass(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        task_snapshot, file_snapshot = _capture_snapshots(conn, file_id)
        noncanonical = "2026-07-19 00:00:01+00:00"
        with pytest.raises(sqlite3.IntegrityError, match="outcome event shape"):
            conn.execute(
                "INSERT INTO artifact_outcome_events "
                "(id, event_type, source_task_id, source_file_id, review_event_id, "
                " source_task_witness_json, source_file_witness_json, "
                " actor_username, downstream_task_id, delivered_bytes, "
                " schema_version, created_at) "
                "VALUES (?, 'full_download', 'source', ?, ?, ?, ?, ?, NULL, ?, 1, ?)",
                (
                    f"outcome_{uuid.uuid4().hex}",
                    file_id,
                    review_event_id,
                    task_snapshot,
                    file_snapshot,
                    TEST_USERNAME,
                    len(b"signed-output"),
                    noncanonical,
                ),
            )

        trigger_name = "trg_artifact_outcomes_no_update"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            "UPDATE artifact_outcome_events SET created_at = ? "
            "WHERE event_type = 'capture_started' AND source_file_id = ?",
            (noncanonical, file_id),
        )
        conn.execute(trigger_sql)

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()


def test_historical_parent_orphan_keeps_provenance_witness_red_after_guard_restore(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        _approve(conn, "source")
        trigger_names = (
            "trg_witnessed_artifact_files_no_delete",
            "trg_review_package_files_no_delete",
        )
        trigger_sql = {
            trigger_name: conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (trigger_name,),
            ).fetchone()[0]
            for trigger_name in trigger_names
        }
        for trigger_name in trigger_names:
            conn.execute(f"DROP TRIGGER {trigger_name}")
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        for trigger_name in trigger_names:
            conn.execute(trigger_sql[trigger_name])

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="provenance_integrity"):
        init_db(outcome_db)


def test_signed_file_snapshot_detects_parent_rewrite_after_guard_restore(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        _approve(conn, "source")
        trigger_names = (
            "trg_witnessed_artifact_files_no_update",
            "trg_review_package_files_no_update",
        )
        trigger_sql = {
            name: conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (name,),
            ).fetchone()[0]
            for name in trigger_names
        }
        for name in trigger_names:
            conn.execute(f"DROP TRIGGER {name}")
        conn.execute(
            "UPDATE files SET sha256 = ?, path = ? WHERE id = ?",
            ("e" * 64, "/tmp/rewritten-after-signoff.txt", file_id),
        )
        for name in trigger_names:
            conn.execute(trigger_sql[name])

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="provenance_integrity"):
        init_db(outcome_db)


def test_signed_parent_snapshot_binds_internal_rowids_and_updated_at(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        _approve(conn, "source")
        task_rowid = conn.execute(
            "SELECT rowid FROM tasks WHERE id = 'source'"
        ).fetchone()[0]
        file_rowid = conn.execute(
            "SELECT rowid FROM files WHERE id = ?", (file_id,)
        ).fetchone()[0]
        task_snapshot, file_snapshot = _capture_snapshots(conn, file_id)
        assert json.loads(task_snapshot)["rowid"] == task_rowid
        assert json.loads(task_snapshot)["updated_at"] == repos.get_task(
            conn, "source"
        )["updated_at"]
        assert json.loads(file_snapshot)["rowid"] == file_rowid
    finally:
        conn.close()


def test_signed_file_snapshot_detects_internal_rowid_rewrite_after_guard_restore(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        _approve(conn, "source")
        trigger_names = (
            "trg_witnessed_artifact_files_no_update",
            "trg_review_package_files_no_update",
        )
        trigger_sql = {
            name: conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (name,),
            ).fetchone()[0]
            for name in trigger_names
        }
        for name in trigger_names:
            conn.execute(f"DROP TRIGGER {name}")
        conn.execute(
            "UPDATE files SET rowid = rowid + 1000 WHERE id = ?", (file_id,)
        )
        for name in trigger_names:
            conn.execute(trigger_sql[name])

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()


def test_outcome_shape_rejects_blob_actor_storage_class(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        task_snapshot, file_snapshot = _capture_snapshots(conn, file_id)
        with pytest.raises(sqlite3.IntegrityError, match="outcome event shape"):
            conn.execute(
                "INSERT INTO artifact_outcome_events "
                "(id, event_type, source_task_id, source_file_id, review_event_id, "
                " source_task_witness_json, source_file_witness_json, "
                " actor_username, downstream_task_id, delivered_bytes, schema_version, created_at) "
                "VALUES (?, 'full_download', 'source', ?, ?, ?, ?, ?, NULL, ?, 1, ?)",
                (
                    f"outcome_{uuid.uuid4().hex}",
                    file_id,
                    review_event_id,
                    task_snapshot,
                    file_snapshot,
                    sqlite3.Binary(b"alice"),
                    len(b"signed-output"),
                    "2026-07-19T00:00:01+00:00",
                ),
            )
    finally:
        conn.close()


def test_nonpositive_parent_rowids_are_rejected_without_poisoning_new_writes(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        with pytest.raises(sqlite3.IntegrityError, match="task event internal rowid"):
            conn.execute(
                "INSERT INTO task_events "
                "(id, event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
                "VALUES (-1, 'negative-event', 'source', NULL, 'agent_log', 'info', "
                "'negative', '{}', '2026-07-19T00:00:00+00:00')"
            )
        repos.append_event(
            conn,
            task_id="source",
            agent_id="hello_agent",
            event_type="agent_log",
            level="info",
            message="normal event remains writable",
            payload={},
        )

        with pytest.raises(sqlite3.IntegrityError, match="file internal rowid"):
            conn.execute(
                "INSERT INTO files "
                "(rowid, id, task_id, kind, filename, path, size_bytes, sha256, "
                " created_at, classification, uploaded_by) "
                "VALUES (-1, 'negative-file', NULL, 'input', 'n.txt', '/tmp/n.txt', "
                "1, ?, '2026-07-19T00:00:00+00:00', 'internal', NULL)",
                ("0" * 64,),
            )
        repos.create_file(
            conn,
            file_id="normal-file",
            task_id=None,
            kind="input",
            filename="normal.txt",
            path="/tmp/normal.txt",
            size_bytes=1,
            sha256="1" * 64,
            classification="internal",
        )

        source_columns = [
            str(row[1]) for row in conn.execute("PRAGMA table_info(tasks)")
        ]
        source = conn.execute(
            f"SELECT {', '.join(source_columns)} FROM tasks WHERE id = 'source'"
        ).fetchone()
        values = dict(zip(source_columns, tuple(source), strict=True))
        values["id"] = "negative-task"
        with pytest.raises(sqlite3.IntegrityError, match="task internal rowid"):
            conn.execute(
                f"INSERT INTO tasks (rowid, {', '.join(source_columns)}) "
                f"VALUES (-1, {', '.join('?' for _ in source_columns)})",
                tuple(values[column] for column in source_columns),
            )
        _create_task(conn, "normal-task")
    finally:
        conn.close()


def test_deep_witness_rejects_nonpositive_parent_rowid_after_guard_restore(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        trigger_name = "trg_files_positive_rowid"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f"DROP TRIGGER {trigger_name}")
        conn.execute(
            "INSERT INTO files "
            "(rowid, id, task_id, kind, filename, path, size_bytes, sha256, "
            " created_at, classification, uploaded_by) "
            "VALUES (-1, 'persisted-negative-file', NULL, 'input', 'n.txt', "
            "'/tmp/n.txt', 1, ?, '2026-07-19T00:00:00+00:00', 'internal', NULL)",
            ("0" * 64,),
        )
        conn.execute(trigger_sql)

        witnesses = outcome_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["provenance_integrity"] is False
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="provenance_integrity"):
        init_db(outcome_db)


def test_missing_outcome_table_with_managed_trigger_residue_fails_startup(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        # DROP TABLE removes its own triggers/indexes, but guards attached to
        # files/tasks remain as detectable residue. Startup must not silently
        # create a fresh empty ledger and erase the tamper signal.
        conn.execute("DROP TABLE artifact_outcome_events")
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' "
            "AND name LIKE 'trg_witnessed_artifact_%'"
        ).fetchone()[0] > 0
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="residue"):
        init_db(outcome_db)


def test_full_download_records_only_after_complete_200_body(app_env) -> None:
    client, app = app_env
    task_id = f"task_{uuid.uuid4().hex}"
    content = b"authoritative signed artifact"
    path = app.state.task_runs_dir / task_id / "artifact.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    conn = app.state.conn_factory()
    try:
        _create_task(conn, task_id)
        file_id = _attach_output(conn, task_id, path=path, content=content)
        _approve(conn, task_id)
    finally:
        conn.close()

    assert client.get(f"/api/files/{file_id}/preview").status_code == 200
    assert client.get(
        f"/api/files/{file_id}/download", headers={"Range": "bytes=0-3"}
    ).status_code == 206
    # If-Range mismatch makes Starlette send a simple 200 body, but the mere
    # presence of Range keeps this request outside full_download semantics.
    if_range = client.get(
        f"/api/files/{file_id}/download",
        headers={"Range": "bytes=0-3", "If-Range": '"stale-validator"'},
    )
    assert if_range.status_code == 200
    assert if_range.content == content
    # FastAPI/Starlette 版本可能返回 200 空正文或 405；任一都不得记完整交付。
    assert client.head(f"/api/files/{file_id}/download").status_code in {200, 405}
    conn = app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events WHERE event_type = 'full_download'"
        ).fetchone()[0] == 0
    finally:
        conn.close()

    response_1 = client.get(f"/api/files/{file_id}/download")
    response_2 = client.get(f"/api/files/{file_id}/download")
    assert response_1.status_code == response_2.status_code == 200
    assert response_1.content == response_2.content == content
    conn = app.state.conn_factory()
    try:
        rows = conn.execute(
            "SELECT * FROM artifact_outcome_events "
            "WHERE event_type = 'full_download' ORDER BY rowid"
        ).fetchall()
        assert len(rows) == 2  # repeated real deliveries are not deduplicated
        assert {row["source_task_id"] for row in rows} == {task_id}
        assert {row["source_file_id"] for row in rows} == {file_id}
        assert {row["actor_username"] for row in rows} == {TEST_USERNAME}
        assert {row["delivered_bytes"] for row in rows} == {len(content)}
    finally:
        conn.close()


def test_download_started_before_approval_is_not_retroactively_added_to_cohort(
    app_env,
) -> None:
    client, app = app_env
    task_id = f"task_{uuid.uuid4().hex}"
    content = b"approval must precede delivery"
    path = app.state.task_runs_dir / task_id / "artifact.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    conn = app.state.conn_factory()
    try:
        _create_task(conn, task_id)
        file_id = _attach_output(conn, task_id, path=path, content=content)
    finally:
        conn.close()

    # Construct the actual endpoint response while the artifact is unsigned.
    # Approval happens only after this request crossed the download boundary,
    # but before its complete body is sent: it must not be admitted
    # retrospectively into the signed-artifact cohort.
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": f"/api/files/{file_id}/download",
            "raw_path": f"/api/files/{file_id}/download".encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "app": app,
        }
    )
    request.state.user = {
        "username": TEST_USERNAME,
        "display_name": "测试工程师",
    }
    response = download_file(file_id, request)

    conn = app.state.conn_factory()
    try:
        review_event_id = _approve(conn, task_id)
    finally:
        conn.close()

    delivered = bytearray()

    async def send(message):
        if message["type"] == "http.response.body":
            delivered.extend(message.get("body", b""))

    try:
        anyio.run(response._handle_simple, send, False, False)
    finally:
        response._verified_handle.close()

    assert bytes(delivered) == content
    conn = app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'capture_started' AND source_file_id = ?",
            (file_id,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'full_download' AND source_file_id = ?",
            (file_id,),
        ).fetchone()[0] == 0
    finally:
        conn.close()

    # A new request that starts after approval remains a legitimate delivery.
    post_approval = client.get(f"/api/files/{file_id}/download")
    assert post_approval.status_code == 200
    assert post_approval.content == content
    conn = app.state.conn_factory()
    try:
        row = conn.execute(
            "SELECT * FROM artifact_outcome_events "
            "WHERE event_type = 'full_download' AND source_file_id = ?",
            (file_id,),
        ).fetchone()
        assert row is not None
        assert row["source_task_id"] == task_id
        assert row["source_file_id"] == file_id
        assert row["review_event_id"] == review_event_id
    finally:
        conn.close()


def test_download_cohort_is_snapshotted_before_integrity_gate(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _client, app = app_env
    task_id = f"task_{uuid.uuid4().hex}"
    content = b"approval during integrity gate is too late"
    path = app.state.task_runs_dir / task_id / "artifact.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    conn = app.state.conn_factory()
    try:
        _create_task(conn, task_id)
        file_id = _attach_output(conn, task_id, path=path, content=content)
    finally:
        conn.close()

    original_gate = files_api._gated_verified_handle

    def approve_inside_gate(*args, **kwargs):
        approve_conn = app.state.conn_factory()
        try:
            _approve(approve_conn, task_id)
        finally:
            approve_conn.close()
        return original_gate(*args, **kwargs)

    monkeypatch.setattr(files_api, "_gated_verified_handle", approve_inside_gate)
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": f"/api/files/{file_id}/download",
            "raw_path": f"/api/files/{file_id}/download".encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "app": app,
        }
    )
    request.state.user = {
        "username": TEST_USERNAME,
        "display_name": "测试工程师",
    }
    response = download_file(file_id, request)
    delivered = bytearray()

    async def send(message):
        if message["type"] == "http.response.body":
            delivered.extend(message.get("body", b""))

    try:
        anyio.run(response._handle_simple, send, False, False)
    finally:
        response._verified_handle.close()

    assert bytes(delivered) == content
    conn = app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'capture_started' AND source_file_id = ?",
            (file_id,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'full_download' AND source_file_id = ?",
            (file_id,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_download_post_send_capture_failure_does_not_change_delivered_response(
    app_env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client, app = app_env
    task_id = f"task_{uuid.uuid4().hex}"
    content = b"already delivered"
    path = app.state.task_runs_dir / task_id / "artifact.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    conn = app.state.conn_factory()
    try:
        _create_task(conn, task_id)
        file_id = _attach_output(conn, task_id, path=path, content=content)
        _approve(conn, task_id)
    finally:
        conn.close()

    def fail_capture(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repos, "record_full_download_outcome", fail_capture)
    response = client.get(f"/api/files/{file_id}/download")
    assert response.status_code == 200
    assert response.content == content
    assert "artifact_outcome_capture_failed" in caplog.text
    assert "post_send_db_failure" in caplog.text


def test_interrupted_simple_send_never_calls_post_send_capture(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"123456")
    calls: list[int] = []
    handle = path.open("rb")
    response = _VerifiedFileResponse(
        handle,
        path=str(path),
        filename=path.name,
        expected_full_bytes=6,
        on_full_body_sent=calls.append,
    )

    async def send(message):
        if message["type"] == "http.response.body":
            raise ConnectionError("client disconnected")

    async def exercise() -> None:
        with pytest.raises(ConnectionError):
            await response._handle_simple(send, False, False)

    try:
        anyio.run(exercise)
    finally:
        handle.close()
    assert calls == []


def test_exact_chunk_final_empty_terminator_failure_is_not_full_delivery(
    tmp_path: Path,
) -> None:
    path = tmp_path / "exact-chunk.bin"
    path.write_bytes(b"123456")
    calls: list[int] = []
    handle = path.open("rb")
    response = _VerifiedFileResponse(
        handle,
        path=str(path),
        filename=path.name,
        expected_full_bytes=6,
        on_full_body_sent=calls.append,
    )
    response.chunk_size = 6
    body_sends = 0

    async def send(message):
        nonlocal body_sends
        if message["type"] == "http.response.body":
            body_sends += 1
            if body_sends == 2:  # final empty more_body=False terminator
                raise ConnectionError("disconnect before terminator ack")

    async def exercise() -> None:
        with pytest.raises(ConnectionError):
            await response._handle_simple(send, False, False)

    try:
        anyio.run(exercise)
    finally:
        handle.close()
    assert body_sends == 2
    assert calls == []


def test_pipeline_handoff_is_atomic_and_exact_for_captured_piped_files(
    outcome_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "upstream")
        file_id = _attach_output(conn, "upstream")
        review_event_id = _approve(conn, "upstream")
        _create_task(conn, "downstream", depends_on=["upstream"])
    finally:
        conn.close()
    assert resolve_dependencies_once(lambda: get_conn(outcome_db)) == 1
    conn = get_conn(outcome_db)
    try:
        row = conn.execute(
            "SELECT * FROM artifact_outcome_events WHERE event_type = 'pipeline_handoff'"
        ).fetchone()
        assert row is not None
        assert row["source_task_id"] == "upstream"
        assert row["source_file_id"] == file_id
        assert row["review_event_id"] == review_event_id
        assert row["downstream_task_id"] == "downstream"
        assert row["actor_username"] is None
        assert row["delivered_bytes"] is None

        # A file already present before this enqueue call is not transferred by
        # this resolver action, so it must not acquire a new handoff fact.
        _create_task(
            conn,
            "downstream-preexisting",
            depends_on=["upstream"],
            input_file_ids=[file_id],
        )
        repos.enqueue_dependent_task(conn, "downstream-preexisting", [file_id])
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'pipeline_handoff' "
            "AND downstream_task_id = 'downstream-preexisting'"
        ).fetchone()[0] == 0

        _create_task(conn, "downstream-rollback", depends_on=["upstream"])
        original = repos.append_artifact_outcome_event

        def fail_pipeline(*args, **kwargs):
            if kwargs.get("event_type") == "pipeline_handoff":
                raise sqlite3.IntegrityError("injected telemetry failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(repos, "append_artifact_outcome_event", fail_pipeline)
        with pytest.raises(sqlite3.IntegrityError):
            repos.enqueue_dependent_task(conn, "downstream-rollback", [file_id])
        rolled_back = repos.get_task(conn, "downstream-rollback")
        assert rolled_back["status"] == "created"
        assert rolled_back["input_file_ids"] == []
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'pipeline_handoff' AND downstream_task_id = 'downstream-rollback'"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_deterministic_unsigned_legal_pipeline_still_flows_without_fake_outcome(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        manifest = {
            "id": "hello_agent",
            "version": "0.1.0",
            "model": {"profile": "none"},
            "workflow": {"mode": "job", "requires_human_review": False},
        }
        conn.execute(
            "INSERT INTO agent_versions "
            "(agent_id, version, yaml_json, created_at) VALUES (?,?,?,?)",
            (
                "hello_agent",
                "0.1.0",
                json.dumps(manifest),
                "2026-07-19T00:00:00+00:00",
            ),
        )
        _create_task(conn, "deterministic-source")
        file_id = _attach_output(conn, "deterministic-source")
        for status in ("queued", "validating", "running", "analyzing", "completed"):
            repos.set_task_status(conn, "deterministic-source", status)
        _create_task(
            conn,
            "deterministic-downstream",
            depends_on=["deterministic-source"],
        )
    finally:
        conn.close()

    assert resolve_dependencies_once(lambda: get_conn(outcome_db)) == 1
    conn = get_conn(outcome_db)
    try:
        downstream = repos.get_task(conn, "deterministic-downstream")
        assert downstream["status"] == "queued"
        assert downstream["input_file_ids"] == [file_id]
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events"
        ).fetchone()[0] == 0
    finally:
        conn.close()
